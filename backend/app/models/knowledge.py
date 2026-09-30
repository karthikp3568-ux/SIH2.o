"""RAG knowledge store.

Chunks carry metadata and provenance, not just text, because the metadata is
what makes structured filtering (and therefore grounded retrieval) possible.

Embeddings are stored as JSON float arrays. On PostgreSQL this column should be
migrated to `vector(dim)` from pgvector with an HNSW index; the retrieval code
in app/services/retrieval.py isolates that choice behind one function.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import RecordStatus
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    #: qualification | opportunity | training | scheme_reference | guidance
    doc_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(240), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_authority: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=RecordStatus.ACTIVE, index=True, nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Back-links to the structured record this document describes, so retrieved
    #: text can always be resolved to a verifiable row.
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    #: Hash of the source text; lets ingestion skip unchanged documents.
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.sequence"
    )


class KnowledgeChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Denormalised filter columns - kept as real columns so retrieval can apply
    #: metadata filters in SQL rather than after loading every chunk.
    sector: Mapped[str | None] = mapped_column(String(80), index=True)
    nsqf_level: Mapped[int | None] = mapped_column(Integer, index=True)
    district: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=RecordStatus.ACTIVE, index=True, nullable=False
    )
    chunk_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    embedding: Mapped[list | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    #: Token count proxy, used by chunking diagnostics.
    token_estimate: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunk_doc_seq", "document_id", "sequence", unique=True),
        Index("ix_chunk_filters", "status", "sector", "nsqf_level"),
    )
