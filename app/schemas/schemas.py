"""Pydantic request/response schemas."""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class SourceSystemType(str, Enum):
    """Supported source system types."""
    MYSQL = "MySQL"
    MSSQL = "MSSQL"
    POSTGRESQL = "PostgreSQL"


class ColumnSchema(BaseModel):
    """Column schema."""
    name: str = Field(..., min_length=1, description="Column name")
    type: str = Field(..., min_length=1, description="Column data type")

    class Config:
        from_attributes = True


class ColumnResponse(ColumnSchema):
    """Column response schema."""
    id: int


class DatasetCreateRequest(BaseModel):
    """Request schema for creating a dataset."""
    fqn: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Fully qualified name: connection.database.schema.table"
    )
    source_system: SourceSystemType = Field(..., description="Source system type")
    columns: List[ColumnSchema] = Field(default_factory=list, description="Dataset columns")


class DatasetUpdateRequest(BaseModel):
    """Request schema for updating a dataset."""
    columns: Optional[List[ColumnSchema]] = None


class DatasetResponse(BaseModel):
    """Dataset response schema."""
    id: int
    fqn: str
    source_system: SourceSystemType
    columns: List[ColumnResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DatasetLineageResponse(DatasetResponse):
    """Dataset response with lineage information."""
    upstream_fqns: List[str] = Field(default_factory=list, description="FQNs of upstream datasets")
    downstream_fqns: List[str] = Field(default_factory=list, description="FQNs of downstream datasets")


class LineageCreateRequest(BaseModel):
    """Request schema for creating a lineage relationship."""
    upstream_fqn: str = Field(..., description="FQN of upstream dataset")
    downstream_fqn: str = Field(..., description="FQN of downstream dataset")


class LineageResponse(BaseModel):
    """Lineage response schema."""
    id: int
    upstream_fqn: str
    downstream_fqn: str
    created_at: datetime

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    """Single search result."""
    dataset: DatasetLineageResponse
    match_type: str = Field(
        ...,
        description="Type of match: table_name, database_name, schema_name, or column_name"
    )


class SearchResponse(BaseModel):
    """Search response containing multiple results."""
    query: str
    total_results: int
    results: List[SearchResult] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Error response schema."""
    detail: str
    error_code: Optional[str] = None
