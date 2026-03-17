"""SQLAlchemy database models for metadata service."""
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class SourceSystemType(str, enum.Enum):
    """Supported source system types."""
    MYSQL = "MySQL"
    MSSQL = "MSSQL"
    POSTGRESQL = "PostgreSQL"


class Dataset(Base):
    """Dataset model representing a table/file in a data system."""
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    # Fully qualified name: connection_name.database_name.schema_name.table_name
    fqn = Column(String(500), unique=True, nullable=False, index=True)
    source_system = Column(String(50), nullable=False)  # String for SQLite compatibility
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    columns = relationship("ColumnModel", back_populates="dataset", cascade="all, delete-orphan")
    upstream_lineages = relationship(
        "Lineage",
        foreign_keys="Lineage.downstream_dataset_id",
        back_populates="downstream_dataset"
    )
    downstream_lineages = relationship(
        "Lineage",
        foreign_keys="Lineage.upstream_dataset_id",
        back_populates="upstream_dataset"
    )

    def __repr__(self):
        return f"<Dataset(id={self.id}, fqn={self.fqn})>"


class ColumnModel(Base):
    """Column/field model for datasets."""
    __tablename__ = "columns"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    dataset = relationship("Dataset", back_populates="columns")

    __table_args__ = (
        # Ensure unique column names per dataset
        # In SQLAlchemy, composite unique constraint would be added via UniqueConstraint
    )

    def __repr__(self):
        return f"<Column(id={self.id}, name={self.name}, type={self.type})>"


class Lineage(Base):
    """Lineage model for dataset relationships."""
    __tablename__ = "lineages"

    id = Column(Integer, primary_key=True, index=True)
    upstream_dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    downstream_dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    upstream_dataset = relationship(
        "Dataset",
        foreign_keys=[upstream_dataset_id],
        back_populates="downstream_lineages"
    )
    downstream_dataset = relationship(
        "Dataset",
        foreign_keys=[downstream_dataset_id],
        back_populates="upstream_lineages"
    )

    __table_args__ = (
        # Ensure we don't create duplicate lineages
        # Composite unique constraint on both foreign keys
    )

    def __repr__(self):
        return f"<Lineage(upstream={self.upstream_dataset_id}, downstream={self.downstream_dataset_id})>"
