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
    Integer,
    JSON,
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


class TelemetrieEvenement(Base):
    """Evenement d'usage MARC v3 (telemetrie).

    AUCUNE donnee medicale : le payload ne contient que des nombres bornes, des
    booleens, des enums connus et des ids techniques ([a-z0-9_]). Valide par
    ``telemetrie.whitelist`` avant insertion. Le projet n'est repere que par un
    hash sale irreversible.
    """

    __tablename__ = "telemetrie_evenements"
    __table_args__ = (
        Index("ix_telemetrie_ts", "ts"),
        Index("ix_telemetrie_type_ts", "type", "ts"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid_str
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    projet_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


# ---------------------------------------------------------------------------
# Conformite ISO 15189:2022 (backend/conformite). AUCUN texte medical, aucun
# texte libre : uniquement des identifiants techniques, enums, nombres et
# empreintes SHA-256 (validation par ``conformite.metadonnees``).
# ---------------------------------------------------------------------------


class ConformiteAudit(Base):
    """Journal d'audit append-only, chaine par hash (8.4 maitrise des enregistrements)."""

    __tablename__ = "conformite_audit"
    __table_args__ = (Index("ix_conformite_audit_projet", "projet_hash"),)

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    acteur_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    projet_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    hash_precedent: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class ConformiteHabilitation(Base):
    """Habilitation 'valideur' (6.2) : un pathologiste habilite peut liberer un compte rendu."""

    __tablename__ = "conformite_habilitations"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    habilite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    modifie_par: Mapped[str | None] = mapped_column(String(36), nullable=True)
    modifie_le: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class ConformiteValidation(Base):
    """Validation d'un projet par un pathologiste habilite : qui, quand, versions, empreinte. Jamais le texte."""

    __tablename__ = "conformite_validations"
    __table_args__ = (Index("ix_conformite_validations_projet", "projet_hash", "revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    projet_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ts: Mapped[str] = mapped_column(String(32), nullable=False)
    empreinte_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    precedente_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    nb_alertes_bloquantes_ouvertes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nb_trous_ouverts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derogation: Mapped[str | None] = mapped_column(String(60), nullable=True)
    versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    audit_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConformiteKbVersion(Base):
    """Registre des versions de la base de connaissances (8.3 maitrise documentaire)."""

    __tablename__ = "conformite_kb_versions"

    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    empreinte_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    statut: Mapped[str] = mapped_column(String(20), nullable=False, default="brouillon")
    enregistree_le: Mapped[str] = mapped_column(String(32), nullable=False)
    approuvee_par: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approuvee_le: Mapped[str | None] = mapped_column(String(32), nullable=True)
    en_service_le: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retiree_le: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ConformiteNonConformite(Base):
    """Non-conformite signalee (7.5, 8.7) : categories enum, aucun texte medical ni libre."""

    __tablename__ = "conformite_non_conformites"
    __table_args__ = (Index("ix_conformite_nc_ts", "ts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    ts: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    projet_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    categorie: Mapped[str] = mapped_column(String(40), nullable=False)
    gravite: Mapped[str] = mapped_column(String(20), nullable=False)
    etape: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organe: Mapped[str | None] = mapped_column(String(60), nullable=True)
    statut: Mapped[str] = mapped_column(String(20), nullable=False, default="ouverte")
    kb_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version_pipeline: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Signalement(Base):
    """Signalement unifie (MARC v3) : dysfonctionnement, erreur de projet, amelioration, non-conformite ISO.

    UN seul circuit : la note rapide « Utile / A ameliorer » reste de la telemetrie, tout le reste
    atterrit ici. Le message est un texte libre court (1000 car. max) filtre contre les donnees
    patient ; le projet n'est repere que par son empreinte (``projet_hash``), jamais par son texte.

    Les champs ISO (gravite, etape, organe...) ne servent qu'a la categorie ``non_conformite``.
    ``origine_nc_id`` marque une ligne recopiee depuis l'ancienne table
    ``conformite_non_conformites`` (conservee) pour ne jamais la recopier deux fois.
    """

    __tablename__ = "signalements"
    __table_args__ = (
        Index("ix_signalements_user_cree", "user_id", "cree_le"),
        Index("ix_signalements_statut", "statut"),
        Index("ux_signalements_origine_nc", "origine_nc_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    categorie: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    projet_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ecran: Mapped[str | None] = mapped_column(String(60), nullable=True)
    version_app: Mapped[str | None] = mapped_column(String(60), nullable=True)
    statut: Mapped[str] = mapped_column(String(20), nullable=False, default="ouvert")
    note_admin: Mapped[str | None] = mapped_column(Text, nullable=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    maj_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    doublon_de: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # --- champs ISO 15189 (categorie = non_conformite), tous optionnels
    categorie_iso: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gravite: Mapped[str | None] = mapped_column(String(20), nullable=True)
    etape: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organe: Mapped[str | None] = mapped_column(String(60), nullable=True)
    kb_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version_pipeline: Mapped[str | None] = mapped_column(String(60), nullable=True)
    origine_nc_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
