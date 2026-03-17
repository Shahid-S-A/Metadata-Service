"""API routes for metadata service."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Dataset, Lineage, ColumnModel
from app.schemas.schemas import (
    DatasetCreateRequest, DatasetResponse, DatasetLineageResponse,
    LineageCreateRequest, LineageResponse, SearchResponse, SearchResult,
    DatasetUpdateRequest
)
from app.services.services import (
    LineageValidationService, DatasetService, SearchService
)

router = APIRouter(prefix="/api/v1", tags=["metadata"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "metadata-service"}


# ==================== Dataset Endpoints ====================

@router.post("/datasets", response_model=DatasetLineageResponse, status_code=201)
async def create_dataset(
    request: DatasetCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new dataset with metadata.
    
    Args:
        request: Dataset creation request
        db: Database session
        
    Returns:
        Created dataset with lineage information
    """
    dataset = DatasetService.create_dataset(
        db=db,
        fqn=request.fqn,
        source_system=request.source_system.value,
        columns=request.columns
    )
    
    return SearchService._dataset_to_response(db, dataset)


@router.get("/datasets", response_model=list[DatasetLineageResponse])
async def list_datasets(db: Session = Depends(get_db)):
    """List all datasets.
    
    Args:
        db: Database session
        
    Returns:
        List of all datasets with lineage information
    """
    datasets = db.query(Dataset).all()
    return [SearchService._dataset_to_response(db, ds) for ds in datasets]


@router.get("/datasets/{dataset_id}", response_model=DatasetLineageResponse)
async def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """Get a specific dataset by ID.
    
    Args:
        dataset_id: Dataset ID
        db: Database session
        
    Returns:
        Dataset with lineage information
    """
    dataset = DatasetService.get_dataset_by_id(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return SearchService._dataset_to_response(db, dataset)


@router.get("/datasets/by-fqn/{fqn}", response_model=DatasetLineageResponse)
async def get_dataset_by_fqn(fqn: str, db: Session = Depends(get_db)):
    """Get a dataset by its fully qualified name.
    
    Args:
        fqn: Fully qualified name
        db: Database session
        
    Returns:
        Dataset with lineage information
    """
    dataset = DatasetService.get_dataset_by_fqn(db, fqn)
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset with FQN '{fqn}' not found")
    
    return SearchService._dataset_to_response(db, dataset)


@router.put("/datasets/{dataset_id}", response_model=DatasetLineageResponse)
async def update_dataset(
    dataset_id: int,
    request: DatasetUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update a dataset's columns.
    
    Args:
        dataset_id: Dataset ID
        request: Update request
        db: Database session
        
    Returns:
        Updated dataset
    """
    dataset = DatasetService.get_dataset_by_id(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    if request.columns is not None:
        # Delete existing columns
        for col in dataset.columns:
            db.delete(col)
        
        # Add new columns
        for col_data in request.columns:
            column = ColumnModel(
                dataset_id=dataset.id,
                name=col_data.name,
                type=col_data.type
            )
            db.add(column)
    
    db.commit()
    db.refresh(dataset)
    return SearchService._dataset_to_response(db, dataset)


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """Delete a dataset.
    
    Args:
        dataset_id: Dataset ID
        db: Database session
    """
    dataset = DatasetService.get_dataset_by_id(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    db.delete(dataset)
    db.commit()


# ==================== Lineage Endpoints ====================

@router.post("/lineages", response_model=LineageResponse, status_code=201)
async def create_lineage(
    request: LineageCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a lineage relationship between datasets.
    
    Validates that the lineage doesn't create cycles.
    
    Args:
        request: Lineage creation request
        db: Database session
        
    Returns:
        Created lineage relationship
        
    Raises:
        HTTPException: If lineage would create a cycle
    """
    # Get datasets by FQN
    upstream = DatasetService.get_dataset_by_fqn(db, request.upstream_fqn)
    downstream = DatasetService.get_dataset_by_fqn(db, request.downstream_fqn)
    
    if not upstream:
        raise HTTPException(
            status_code=404,
            detail=f"Upstream dataset '{request.upstream_fqn}' not found"
        )
    if not downstream:
        raise HTTPException(
            status_code=404,
            detail=f"Downstream dataset '{request.downstream_fqn}' not found"
        )
    
    # Validate lineage doesn't create a cycle
    LineageValidationService.validate_lineage_creation(
        db, upstream.id, downstream.id
    )
    
    # Check if lineage already exists
    existing = db.query(Lineage).filter(
        Lineage.upstream_dataset_id == upstream.id,
        Lineage.downstream_dataset_id == downstream.id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Lineage relationship already exists"
        )
    
    lineage = Lineage(
        upstream_dataset_id=upstream.id,
        downstream_dataset_id=downstream.id
    )
    db.add(lineage)
    db.commit()
    db.refresh(lineage)
    
    return LineageResponse(
        id=lineage.id,
        upstream_fqn=upstream.fqn,
        downstream_fqn=downstream.fqn,
        created_at=lineage.created_at
    )


@router.get("/lineages", response_model=list[LineageResponse])
async def list_lineages(db: Session = Depends(get_db)):
    """List all lineage relationships.
    
    Args:
        db: Database session
        
    Returns:
        List of all lineage relationships
    """
    lineages = db.query(Lineage).all()
    return [
        LineageResponse(
            id=l.id,
            upstream_fqn=l.upstream_dataset.fqn,
            downstream_fqn=l.downstream_dataset.fqn,
            created_at=l.created_at
        )
        for l in lineages
    ]


@router.delete("/lineages/{lineage_id}", status_code=204)
async def delete_lineage(lineage_id: int, db: Session = Depends(get_db)):
    """Delete a lineage relationship.
    
    Args:
        lineage_id: Lineage ID
        db: Database session
    """
    lineage = db.query(Lineage).filter(Lineage.id == lineage_id).first()
    if not lineage:
        raise HTTPException(status_code=404, detail="Lineage not found")
    
    db.delete(lineage)
    db.commit()


# ==================== Search Endpoint ====================

@router.get("/search", response_model=SearchResponse)
async def search_datasets(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db)
):
    """Search for datasets by name and column names.
    
    Results are sorted by match priority:
    1. Table name matches (highest priority)
    2. Column name matches
    3. Schema name matches
    4. Database name matches (lowest priority)
    
    Args:
        q: Search query
        db: Database session
        
    Returns:
        Search results with datasets and match types
    """
    results = SearchService.search(db, q)
    
    search_results = [
        SearchResult(dataset=response, match_type=match_type)
        for response, match_type, _ in results
    ]
    
    return SearchResponse(
        query=q,
        total_results=len(search_results),
        results=search_results
    )
