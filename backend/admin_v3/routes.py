"""API d'administration unifiee /v3/admin (admins uniquement). Contrat : docs/v3/11_contrat_admin.md."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user
from conformite import chaine
from conformite.metadonnees import IDENT, valider_payload
from database import get_db_session
from db_models import ConformiteHabilitation, Report, Signalement, TelemetrieEvenement, User
from etude.models import EtudeDossier, EtudeSession

from . import retours, sante, vue_ensemble
from .signalements import MAX_NOTE_ADMIN, en_utc, iso_z, maintenant, vue_signalement

router = APIRouter(prefix="/v3/admin", tags=["admin-v3"])

Admin = Annotated[User, Depends(get_admin_user)]
Db = Annotated[AsyncSession | None, Depends(get_db_session)]


def _db(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(status_code=503, detail="Base de données non disponible")
    return db


@router.get("/vue-ensemble")
async def vue_d_ensemble(_a: Admin, db: Db, periode: Literal["7j", "30j", "90j", "tout"] = "30j") -> dict[str, Any]:
    """KPI et serie quotidienne : v3, ancienne version et etude reunies."""
    return await vue_ensemble.calculer(_db(db), periode)


@router.get("/retours")
async def lister_retours(
    _a: Admin, db: Db,
    origine: Literal["v3", "ancienne_version", "etude"] | None = None,
    categorie: str | None = Query(default=None, max_length=60),
    statut: Literal["ouvert", "en_cours", "traite", "rejete"] | None = None,
    page: int = Query(default=1, ge=1),
    par_page: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    """Flux unifie des retours (signalements, notes, avis), du plus recent au plus ancien."""
    items = retours.filtrer(await retours.collecter(_db(db)), origine, categorie, statut)
    return {"total": len(items), "page": page, "items": retours.page(items, page, par_page)}


class SignalementPatch(BaseModel):
    statut: Literal["ouvert", "en_cours", "traite", "rejete"] | None = None
    note_admin: str | None = None


@router.patch("/signalements/{signalement_id}")
async def traiter_signalement(signalement_id: str, corps: SignalementPatch, admin: Admin, db: Db) -> dict[str, Any]:
    """Change le statut et/ou la note interne ; chaque changement est inscrit dans l'audit chaine."""
    d = _db(db)
    if corps.statut is None and corps.note_admin is None:
        raise HTTPException(status_code=422, detail="Rien à modifier : précisez un statut ou une note.")
    if corps.note_admin is not None and len(corps.note_admin) > MAX_NOTE_ADMIN:
        raise HTTPException(status_code=422, detail=f"La note est trop longue : {MAX_NOTE_ADMIN} caractères au maximum.")
    s = await d.get(Signalement, signalement_id) if IDENT.fullmatch(signalement_id) else None
    if s is None:
        raise HTTPException(status_code=404, detail="Signalement inconnu.")
    note = corps.note_admin.strip() if corps.note_admin is not None else None
    statut_change = corps.statut is not None and corps.statut != s.statut
    note_change = note is not None and note != (s.note_admin or "")
    if not (statut_change or note_change):
        return vue_signalement(s)
    ancien = s.statut
    if statut_change:
        s.statut = corps.statut  # type: ignore[assignment]
    if note_change:
        s.note_admin = note or None
    s.maj_le = maintenant()
    await d.flush()
    # Le texte de la note n'entre JAMAIS dans la chaine (metadonnees seulement).
    await chaine.ajouter(d, "signalement_statut", admin.id, s.projet_hash, valider_payload(
        {"signalement_id": s.id, "statut": s.statut, "statut_precedent": ancien, "note_modifiee": bool(note_change)}))
    return vue_signalement(s)


@router.get("/utilisateurs")
async def lister_utilisateurs(_a: Admin, db: Db) -> list[dict[str, Any]]:
    """Tous les comptes, avec leur activite sur les trois sources."""
    d = _db(db)
    users = (await d.execute(select(User).order_by(User.created_at.desc(), User.email))).scalars().all()
    tele = {u: (n, en_utc(m)) for u, n, m in (await d.execute(
        select(TelemetrieEvenement.user_id,
               func.sum(case((TelemetrieEvenement.type == "projet_genere", 1), else_=0)),
               func.max(TelemetrieEvenement.ts)).group_by(TelemetrieEvenement.user_id))).all()}
    cr = {u: (n, en_utc(m)) for u, n, m in (await d.execute(
        select(Report.user_id, func.count(), func.max(Report.created_at)).group_by(Report.user_id))).all()}
    dos = {u: (n, en_utc(m)) for u, n, m in (await d.execute(
        select(EtudeSession.praticien_id, func.count(EtudeDossier.id), func.max(EtudeDossier.cree_a))
        .join(EtudeDossier, EtudeDossier.session_id == EtudeSession.id).group_by(EtudeSession.praticien_id))).all()}
    hab = {h.user_id: bool(h.habilite) for h in (await d.execute(select(ConformiteHabilitation))).scalars()}
    sortie = []
    for u in users:
        dates = [x for x in (en_utc(u.last_login), tele.get(u.id, (0, None))[1], cr.get(u.id, (0, None))[1],
                             dos.get(u.id, (0, None))[1]) if x]
        sortie.append({
            "id": u.id, "email": u.email, "nom": u.name, "role": u.role, "cree_le": iso_z(u.created_at),
            "derniere_activite": iso_z(max(dates)) if dates else None,
            "projets_v3": int(tele.get(u.id, (0, None))[0] or 0),
            "comptes_rendus_anciens": int(cr.get(u.id, (0, None))[0] or 0),
            "dossiers_etude": int(dos.get(u.id, (0, None))[0] or 0),
            "habilite_valideur": hab.get(u.id, False),
        })
    return sortie


@router.get("/etude")
async def synthese_etude(admin: Admin, db: Db) -> dict[str, object]:
    """Synthese de l'etude MARC-ACP : meme logique et meme reponse que GET /admin/etude/synthese."""
    from routes_etude_admin import synthese

    return await synthese(admin, db)


@router.get("/sante")
async def sante_base(_a: Admin, db: Db) -> dict[str, Any]:
    """Volumes par table et controles d'integrite. Lecture seule."""
    return await sante.calculer(_db(db))
