"""File model for file management."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, Relationship, SQLModel, Text

from leagent.services.database.models.base import BaseModel, SoftDeleteMixin


class FileType(str, Enum):
    """File type classification."""

    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    DATA = "data"
    CODE = "code"
    OTHER = "other"


class FileStatus(str, Enum):
    """File processing status."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class FileBase(SQLModel):
    """Base file fields."""

    name: str = Field(max_length=255)
    original_name: str = Field(max_length=255)
    file_type: FileType = Field(default=FileType.OTHER)
    mime_type: Optional[str] = Field(default=None, max_length=100)
    size: int = Field(default=0)
    status: FileStatus = Field(default=FileStatus.UPLOADED)


class File(FileBase, BaseModel, SoftDeleteMixin, table=True):
    """File database model."""

    __tablename__ = "files"

    # Ownership
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)
    folder_id: Optional[UUID] = Field(default=None, foreign_key="folders.id", index=True)
    # Chat attachments use a non-null ``session_id``. Pet Space library files
    # (and other non-chat assets) use ``session_id is NULL`` and are linked
    # via :class:`PetProjectFile` instead of the session attachment list.
    session_id: Optional[UUID] = Field(
        default=None, foreign_key="chat_sessions.id", index=True, nullable=True
    )

    # Storage
    storage_path: str = Field(max_length=1000)
    storage_bucket: Optional[str] = Field(default=None, max_length=100)
    checksum: Optional[str] = Field(default=None, max_length=64)

    # Processing results
    extracted_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    file_metadata: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON

    # OCR/extraction info
    page_count: Optional[int] = Field(default=None)
    has_ocr: bool = Field(default=False)
    ocr_language: Optional[str] = Field(default=None, max_length=20)

    # Vector embedding reference
    embedding_id: Optional[str] = Field(default=None, max_length=100)
    is_indexed: bool = Field(default=False)

    # Expiration
    expires_at: Optional[datetime] = Field(default=None)

    # Relationships
    folder: Optional["Folder"] = Relationship(back_populates="files")


class FileCreate(SQLModel):
    """Schema for creating a file."""

    name: str
    original_name: str
    file_type: FileType = FileType.OTHER
    mime_type: Optional[str] = None
    size: int
    storage_path: str
    storage_bucket: Optional[str] = None
    folder_id: Optional[UUID] = None


class FileUpdate(SQLModel):
    """Schema for updating a file."""

    name: Optional[str] = None
    status: Optional[FileStatus] = None
    folder_id: Optional[UUID] = None
    extracted_text: Optional[str] = None
    file_metadata: Optional[str] = None
    is_indexed: Optional[bool] = None


class FileRead(FileBase):
    """Schema for reading a file."""

    id: UUID
    user_id: Optional[UUID]
    folder_id: Optional[UUID]
    checksum: Optional[str]
    page_count: Optional[int]
    has_ocr: bool
    is_indexed: bool
    created_at: datetime
    updated_at: datetime
