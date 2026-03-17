"""Services for business logic including cycle detection and search."""
from typing import Set, Dict, List, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.models import Dataset, Lineage, ColumnModel
from app.schemas.schemas import (
    SearchResult, DatasetLineageResponse, ColumnResponse
)


class LineageValidationService:
    """Service for validating lineage relationships and detecting cycles."""

    @staticmethod
    def _build_graph(db: Session, exclude_lineage_id: int = None) -> Dict[int, Set[int]]:
        """Build adjacency list for the current lineage graph.
        
        Args:
            db: Database session
            exclude_lineage_id: Optional lineage ID to exclude (for pre-validation)
            
        Returns:
            Dictionary mapping dataset IDs to set of downstream dataset IDs
        """
        graph: Dict[int, Set[int]] = {}
        all_datasets = db.query(Dataset).all()
        
        # Initialize all datasets in the graph
        for dataset in all_datasets:
            graph[dataset.id] = set()
        
        # Add all lineage relationships
        lineages = db.query(Lineage).all()
        for lineage in lineages:
            if exclude_lineage_id and lineage.id == exclude_lineage_id:
                continue
            if lineage.upstream_dataset_id in graph:
                graph[lineage.upstream_dataset_id].add(lineage.downstream_dataset_id)
        
        return graph

    @staticmethod
    def _has_cycle_dfs(graph: Dict[int, Set[int]], start: int, target: int) -> bool:
        """Check if there's a path from start to target using DFS.
        
        Args:
            graph: Adjacency list representation of the lineage graph
            start: Starting node (upstream dataset ID)
            target: Target node (downstream dataset ID)
            
        Returns:
            True if a path exists, False otherwise
        """
        visited = set()
        
        def dfs(node: int) -> bool:
            if node == target:
                return True
            if node in visited:
                return False
            visited.add(node)
            
            for neighbor in graph.get(node, set()):
                if dfs(neighbor):
                    return True
            return False
        
        return dfs(start)

    @staticmethod
    def validate_lineage_creation(
        db: Session,
        upstream_dataset_id: int,
        downstream_dataset_id: int
    ) -> bool:
        """Validate that creating a lineage won't cause a cycle.
        
        Args:
            db: Database session
            upstream_dataset_id: ID of upstream dataset
            downstream_dataset_id: ID of downstream dataset
            
        Returns:
            True if valid, raises HTTPException if invalid
            
        Raises:
            HTTPException: If the lineage would create a cycle
        """
        if upstream_dataset_id == downstream_dataset_id:
            raise HTTPException(
                status_code=400,
                detail="A dataset cannot be its own upstream or downstream"
            )
        
        # Build current graph
        graph = LineageValidationService._build_graph(db)
        
        # Check if downstream already has a path to upstream
        # If yes, creating upstream -> downstream would create a cycle
        if downstream_dataset_id in graph:
            if LineageValidationService._has_cycle_dfs(
                graph, downstream_dataset_id, upstream_dataset_id
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot create lineage: downstream dataset already has path to upstream. This would create a cycle."
                )
        
        return True


class DatasetService:
    """Service for dataset operations."""

    @staticmethod
    def create_dataset(db: Session, fqn: str, source_system: str, columns: list):
        """Create a new dataset.
        
        Args:
            db: Database session
            fqn: Fully qualified name
            source_system: Source system type
            columns: List of column definitions
            
        Returns:
            Created Dataset instance
        """
        # Check if FQN already exists
        existing = db.query(Dataset).filter(Dataset.fqn == fqn).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset with FQN '{fqn}' already exists"
            )
        
        dataset = Dataset(
            fqn=fqn,
            source_system=source_system  # Store as string
        )
        db.add(dataset)
        db.flush()  # Flush to get the dataset ID
        
        # Add columns
        for col in columns:
            column = ColumnModel(
                dataset_id=dataset.id,
                name=col.name,
                type=col.type
            )
            db.add(column)
        
        db.commit()
        db.refresh(dataset)
        return dataset

    @staticmethod
    def get_dataset_by_fqn(db: Session, fqn: str):
        """Get dataset by FQN.
        
        Args:
            db: Database session
            fqn: Fully qualified name
            
        Returns:
            Dataset instance or None
        """
        return db.query(Dataset).filter(Dataset.fqn == fqn).first()

    @staticmethod
    def get_dataset_by_id(db: Session, dataset_id: int):
        """Get dataset by ID.
        
        Args:
            db: Database session
            dataset_id: Dataset ID
            
        Returns:
            Dataset instance or None
        """
        return db.query(Dataset).filter(Dataset.id == dataset_id).first()


class SearchService:
    """Service for searching datasets."""

    @staticmethod
    def _parse_fqn(fqn: str) -> Dict[str, str]:
        """Parse FQN into components.
        
        Args:
            fqn: Fully qualified name
            
        Returns:
            Dictionary with components
        """
        parts = fqn.split(".")
        if len(parts) != 4:
            return {}
        
        return {
            "connection": parts[0],
            "database": parts[1],
            "schema": parts[2],
            "table": parts[3]
        }

    @staticmethod
    def _dataset_to_response(db: Session, dataset: Dataset) -> DatasetLineageResponse:
        """Convert dataset to response with lineage info.
        
        Args:
            db: Database session
            dataset: Dataset instance
            
        Returns:
            DatasetLineageResponse instance
        """
        upstream_fqns = [
            lineage.upstream_dataset.fqn
            for lineage in dataset.upstream_lineages
        ]
        downstream_fqns = [
            lineage.downstream_dataset.fqn
            for lineage in dataset.downstream_lineages
        ]
        
        return DatasetLineageResponse(
            id=dataset.id,
            fqn=dataset.fqn,
            source_system=dataset.source_system,
            columns=[
                ColumnResponse(id=col.id, name=col.name, type=col.type)
                for col in dataset.columns
            ],
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            upstream_fqns=upstream_fqns,
            downstream_fqns=downstream_fqns
        )

    @staticmethod
    def search(db: Session, query: str) -> List[Tuple[DatasetLineageResponse, str, int]]:
        """Search datasets by name and column names.
        
        Args:
            db: Database session
            query: Search query string
            
        Returns:
            List of tuples: (response, match_type, priority)
            where priority determines sort order (lower is better)
        """
        query_lower = query.lower()
        results: List[Tuple[DatasetLineageResponse, str, int]] = []
        
        # Get all datasets
        datasets = db.query(Dataset).all()
        
        for dataset in datasets:
            fqn_parts = SearchService._parse_fqn(dataset.fqn)
            if not fqn_parts:
                continue
            
            response = SearchService._dataset_to_response(db, dataset)
            
            # Priority 1: Table name match
            if query_lower in fqn_parts["table"].lower():
                results.append((response, "table_name", 1))
            
            # Priority 2: Column name match
            for col in dataset.columns:
                if query_lower in col.name.lower():
                    results.append((response, "column_name", 2))
                    break  # Only add once per dataset for column match
            
            # Priority 3: Schema name match
            if query_lower in fqn_parts["schema"].lower():
                results.append((response, "schema_name", 3))
            
            # Priority 4: Database name match
            if query_lower in fqn_parts["database"].lower():
                results.append((response, "database_name", 4))
        
        # Sort by priority
        results.sort(key=lambda x: x[2])
        
        # Remove duplicates, keeping the highest priority match per dataset
        seen_fqn = {}
        unique_results = []
        for response, match_type, priority in results:
            if response.fqn not in seen_fqn:
                seen_fqn[response.fqn] = True
                unique_results.append((response, match_type, priority))
        
        return unique_results
