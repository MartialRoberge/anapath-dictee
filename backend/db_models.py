"""Modeles SQLAlchemy ORM pour la base de donnees Anapath.

Tables :
- users : utilisateurs authentifies
- organizations : cabinets / laboratoires
- reports : comptes-rendus generes (contenu anonyme uniquement)
- report_exports : historique des exports (docx, fhir, apsr)
- audit_log : journal d'audit pour conformite ISO 15189
- business_rules : regles metier personnalisables par organisation
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func


def _uuid_str() -> str:
    """Genere un UUID sous forme de string (compatible SQLite + PostgreSQL)."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Classe de base pour tous les modeles ORM."""

    pass


class Organization(Base):
    """Cabinet, clinique ou laboratoire."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="liberal"
    )
    subscription_plan: Mapped[str] = mapped_column(
        String(50), nullable=False, default="solo"
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    reports: Mapped[list["Report"]] = relationship(back_populates="organization")
    business_rules: Mapped[list["BusinessRule"]] = relationship(
        back_populates="organization"
    )


class User(Base):
    """Utilisateur authentifie."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="user"
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization: Mapped[Organization | None] = relationship(
        back_populates="users"
    )
    reports: Mapped[list["Report"]] = relationship(back_populates="user")


class Report(Base):
    """Compte-rendu anatomopathologique genere (contenu anonyme)."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    raw_transcription: Mapped[str] = mapped_column(Text, nullable=False)
    structured_report: Mapped[str] = mapped_column(Text, nullable=False)
    organe_detecte: Mapped[str] = mapped_column(
        String(100), nullable=False, default="non_determine"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )
    completeness_warnings: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="reports")
    organization: Mapped[Organization | None] = relationship(
        back_populates="reports"
    )
    exports: Mapped[list["ReportExport"]] = relationship(
        back_populates="report"
    )


class ReportExport(Base):
    """Historique des exports d'un compte-rendu."""

    __tablename__ = "report_exports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    report_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reports.id"), nullable=False
    )
    export_format: Mapped[str] = mapped_column(
        String(50), nullable=False, default="docx"
    )
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    report: Mapped[Report] = relationship(back_populates="exports")


class AuditLog(Base):
    """Journal d'audit pour conformite ISO 15189."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BusinessRule(Base):
    """Regle metier personnalisable par organisation."""

    __tablename__ = "business_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    rule_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organization: Mapped[Organization] = relationship(
        back_populates="business_rules"
    )
