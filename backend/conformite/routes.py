"""Routes /v3/conformite : validation par pathologiste habilite, audit, registre kb, non-conformites.

AUCUN texte medical ni texte libre n'est accepte ni stocke : enums, nombres, identifiants techniques et
empreintes SHA-256. Le serveur ne voit jamais le texte du compte rendu : l'empreinte est calculee par le
client, le serveur en controle le format et l'enregistre (voir docs/v3/conformite/).
"""
from __future__ import annotations

import csv
import io
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user, get_current_user
from database import get_db_session
from db_models import (
    ConformiteAudit,
    ConformiteHabilitation,
    ConformiteKbVersion,
    ConformiteNonConformite,
    ConformiteValidation,
    User,
)
from telemetrie.routes import hacher_projet

from . import chaine, tracabilite
from .metadonnees import IDENT, SHA256, MetadonneeInvalide, valider_payload

router = APIRouter(prefix="/v3/conformite", tags=["conformite"])

Derogation = Literal[
    "information_indisponible_au_dossier",
    "trou_non_applicable_au_cas",
    "alerte_evaluee_non_pertinente",
    "urgence_clinique_documentee_au_laboratoire",
    "autre_motif_trace_par_le_laboratoire",
]
Categorie = Literal["erreur_transcription", "champ_manquant_non_detecte", "faux_positif", "code_errone", "fabrication", "autre"]
Gravite = Literal["mineure", "majeure", "critique"]
Etape = Literal["transcription", "correcteur", "extracteur", "verificateur", "codeur", "redacteur", "relecteur", "interface"]
StatutNC = Literal["ouverte", "en_analyse", "cloturee"]

PATRON_VERSION = r"^[A-Za-z0-9_.+-]{1,60}$"
PATRON_ID = r"^[A-Za-z0-9_.:-]{1,80}$"

Db = Annotated[AsyncSession | None, Depends(get_db_session)]


def _db(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(status_code=503, detail="Base de données non disponible")
    return db


def _propre(d: dict) -> dict:
    try:
        return valider_payload(d)
    except MetadonneeInvalide as exc:  # pragma: no cover - filet : les modeles pydantic filtrent deja
        raise HTTPException(status_code=422, detail=f"Donnée non conforme : {exc}")


async def _est_habilite(db: AsyncSession, user_id: str) -> bool:
    h = await db.get(ConformiteHabilitation, user_id)
    return bool(h and h.habilite)


# --------------------------------------------------------------------------- moi / habilitations
@router.get("/moi")
async def moi(user: Annotated[User, Depends(get_current_user)], db: Db) -> dict:
    d = _db(db)
    return {"habilite": await _est_habilite(d, user.id), "admin": user.role == "admin"}


class HabilitationIn(BaseModel):
    habilite: bool


@router.get("/habilitations")
async def lister_habilitations(_a: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    users = (await d.execute(select(User).where(User.is_active.is_(True)).order_by(User.email))).scalars().all()
    hab = {h.user_id: h for h in (await d.execute(select(ConformiteHabilitation))).scalars()}
    return {"utilisateurs": [
        {"user_id": u.id, "email": u.email, "nom": u.name, "role": u.role,
         "habilite": bool(hab.get(u.id) and hab[u.id].habilite),
         "modifie_le": hab[u.id].modifie_le if u.id in hab else None} for u in users]}


@router.put("/habilitations/{user_id}")
async def definir_habilitation(user_id: str, corps: HabilitationIn, admin: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    if not IDENT.fullmatch(user_id) or await d.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Utilisateur inconnu.")
    h = await d.get(ConformiteHabilitation, user_id)
    ts = chaine.maintenant_iso()
    if h is None:
        d.add(ConformiteHabilitation(user_id=user_id, habilite=corps.habilite, modifie_par=admin.id, modifie_le=ts))
    else:
        h.habilite, h.modifie_par, h.modifie_le = corps.habilite, admin.id, ts
    await d.flush()
    await chaine.ajouter(d, "habilitation", admin.id, None, _propre({"cible_id": user_id, "habilite": corps.habilite}))
    return {"user_id": user_id, "habilite": corps.habilite}


# --------------------------------------------------------------------------- generation
class VersionsIn(BaseModel):
    pipeline: str = Field(default="", pattern=r"^[A-Za-z0-9_.+-]{0,60}$")
    kb: str = Field(default="", pattern=r"^[A-Za-z0-9_.+-]{0,60}$")
    kb_empreinte_sha256: str = Field(default="", pattern=r"^([0-9a-f]{64})?$")
    modeles: dict[str, Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]] = Field(default_factory=dict, max_length=10)


class GenerationIn(BaseModel):
    projet_id: str = Field(pattern=PATRON_ID)
    versions: VersionsIn = Field(default_factory=VersionsIn)
    empreinte_dictee_corrigee_sha256: str = Field(default="", pattern=r"^([0-9a-f]{64})?$")
    niveau_service: Literal["N0", "N1", "N2", "N3"] = "N0"


def _payload_versions(v: VersionsIn) -> dict:
    return {"pipeline": v.pipeline, "kb": v.kb, "kb_empreinte": v.kb_empreinte_sha256,
            "modeles": {k.replace("-", "_"): m for k, m in v.modeles.items() if k.isidentifier()}}


@router.post("/generations")
async def enregistrer_generation(corps: GenerationIn, user: Annotated[User, Depends(get_current_user)], db: Db) -> dict:
    """Journalise la generation d'un projet (metadonnees seulement). Idempotent par projet."""
    d = _db(db)
    ph = hacher_projet(corps.projet_id)
    deja = (await d.execute(select(ConformiteAudit.seq).where(
        ConformiteAudit.type == "generation", ConformiteAudit.projet_hash == ph).limit(1))).first()
    if deja:
        return {"enregistre": False, "seq": deja[0]}
    p = _propre({"versions": _payload_versions(corps.versions), "empreinte_dictee": corps.empreinte_dictee_corrigee_sha256,
                 "niveau_service": corps.niveau_service})
    e = await chaine.ajouter(d, "generation", user.id, ph, p)
    return {"enregistre": True, "seq": e.seq}


# --------------------------------------------------------------------------- validation
class ValidationIn(BaseModel):
    projet_id: str = Field(pattern=PATRON_ID)
    empreinte_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 du texte final, calculé par le client")
    nb_alertes_bloquantes_ouvertes: int = Field(ge=0, le=10_000)
    nb_trous_ouverts: int = Field(ge=0, le=10_000, description="trous OBLIGATOIRES encore ouverts")
    versions: VersionsIn = Field(default_factory=VersionsIn)
    derogation: Derogation | None = None


def _vue_validation(v: ConformiteValidation) -> dict:
    return {"id": v.id, "ts": v.ts, "user_id": v.user_id, "empreinte_sha256": v.empreinte_sha256, "revision": v.revision,
            "precedente_id": v.precedente_id, "derogation": v.derogation, "versions": v.versions,
            "nb_alertes_bloquantes_ouvertes": v.nb_alertes_bloquantes_ouvertes, "nb_trous_ouverts": v.nb_trous_ouverts}


@router.post("/validations", status_code=201)
async def valider(corps: ValidationIn, user: Annotated[User, Depends(get_current_user)], db: Db) -> dict:
    """Libere un projet : refuse sans habilitation, ou avec blocages sauf derogation motivee (enum)."""
    d = _db(db)
    if not await _est_habilite(d, user.id):
        raise HTTPException(status_code=403, detail="Validation réservée aux pathologistes habilités (valideurs).")
    blocages = {"alertes_bloquantes": corps.nb_alertes_bloquantes_ouvertes, "trous_obligatoires": corps.nb_trous_ouverts}
    if (corps.nb_alertes_bloquantes_ouvertes or corps.nb_trous_ouverts) and corps.derogation is None:
        raise HTTPException(status_code=409, detail={
            "message": "Validation impossible : alerte bloquante ou trou obligatoire ouvert. "
                       "Traitez-les, ou validez avec une dérogation motivée.",
            "blocages": blocages})
    ph = hacher_projet(corps.projet_id)
    precedente = (await d.execute(select(ConformiteValidation).where(ConformiteValidation.projet_hash == ph)
                                  .order_by(ConformiteValidation.revision.desc()).limit(1))).scalar_one_or_none()
    if precedente and precedente.empreinte_sha256 == corps.empreinte_sha256:
        raise HTTPException(status_code=409, detail={"message": "Ce texte est déjà validé (même empreinte).", "blocages": {}})
    versions = _propre(_payload_versions(corps.versions))
    kb = await d.get(ConformiteKbVersion, corps.versions.kb) if corps.versions.kb else None
    versions["kb_statut_registre"] = kb.statut if kb else "non_enregistree"
    v = ConformiteValidation(
        projet_hash=ph, user_id=user.id, ts=chaine.maintenant_iso(), empreinte_sha256=corps.empreinte_sha256,
        revision=(precedente.revision + 1) if precedente else 1, precedente_id=precedente.id if precedente else None,
        nb_alertes_bloquantes_ouvertes=corps.nb_alertes_bloquantes_ouvertes, nb_trous_ouverts=corps.nb_trous_ouverts,
        derogation=corps.derogation, versions=versions)
    d.add(v)
    await d.flush()
    type_ = "revision" if precedente else "validation"
    payload = _propre({"validation_id": v.id, "revision": v.revision, "precedente_id": v.precedente_id,
                       "empreinte": v.empreinte_sha256, "blocages": blocages, "versions": versions})
    e = await chaine.ajouter(d, type_, user.id, ph, payload)
    if corps.derogation:
        await chaine.ajouter(d, "derogation", user.id, ph, _propre({"validation_id": v.id, "motif": corps.derogation, "blocages": blocages}))
    v.audit_seq = e.seq
    await d.commit()
    return _vue_validation(v)


@router.get("/validations/{projet_id}")
async def validations_du_projet(projet_id: str, _u: Annotated[User, Depends(get_current_user)], db: Db) -> dict:
    d = _db(db)
    if not IDENT.fullmatch(projet_id):
        raise HTTPException(status_code=422, detail="Identifiant invalide.")
    res = await d.execute(select(ConformiteValidation).where(ConformiteValidation.projet_hash == hacher_projet(projet_id))
                          .order_by(ConformiteValidation.revision))
    return {"validations": [_vue_validation(v) for v in res.scalars()]}


# --------------------------------------------------------------------------- audit (admin)
def _vue_audit(e: ConformiteAudit) -> dict:
    return {"seq": e.seq, "ts": e.ts, "type": e.type, "acteur_id": e.acteur_id, "projet_hash": e.projet_hash,
            "payload": e.payload, "hash_precedent": e.hash_precedent, "hash": e.hash}


@router.get("/audit")
async def lire_audit(_a: Annotated[User, Depends(get_admin_user)], db: Db,
                     apres: int = Query(default=0, ge=0), limite: int = Query(default=200, ge=1, le=1000)) -> dict:
    d = _db(db)
    res = await d.execute(select(ConformiteAudit).where(ConformiteAudit.seq > apres).order_by(ConformiteAudit.seq).limit(limite))
    total = (await d.execute(select(func.count()).select_from(ConformiteAudit))).scalar_one()
    return {"total": total, "entrees": [_vue_audit(e) for e in res.scalars()]}


@router.get("/audit/verification")
async def verifier_audit(_a: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    v = await chaine.verifier(_db(db))
    return {"ok": v.ok, "nb_entrees": v.nb_entrees, "rupture_seq": v.rupture_seq, "motif": v.motif, "dernier_hash": v.dernier_hash}


def _cellule(x: object) -> str:
    s = "" if x is None else str(x)
    return "'" + s if s[:1] in "=+-@" and not s.lstrip("-").isdigit() else s  # anti injection de formule tableur


@router.get("/audit/export.csv")
async def exporter_audit(_a: Annotated[User, Depends(get_admin_user)], db: Db) -> Response:
    d = _db(db)
    res = await d.execute(select(ConformiteAudit).order_by(ConformiteAudit.seq))
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";")
    w.writerow(["seq", "ts", "type", "acteur_id", "projet_hash", "payload", "hash_precedent", "hash"])
    import json
    for e in res.scalars():
        w.writerow([e.seq, e.ts, e.type, _cellule(e.acteur_id), _cellule(e.projet_hash),
                    json.dumps(e.payload, sort_keys=True, ensure_ascii=True), e.hash_precedent, e.hash])
    return Response(tampon.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=audit-marc.csv"})


# --------------------------------------------------------------------------- registre kb (8.3)
def _vue_kb(k: ConformiteKbVersion) -> dict:
    return {"version": k.version, "empreinte_sha256": k.empreinte_sha256, "statut": k.statut, "enregistree_le": k.enregistree_le,
            "approuvee_par": k.approuvee_par, "approuvee_le": k.approuvee_le, "en_service_le": k.en_service_le, "retiree_le": k.retiree_le}


async def _synchroniser_en_service(d: AsyncSession) -> str | None:
    k = (await d.execute(select(ConformiteKbVersion).where(ConformiteKbVersion.statut == "en_service"))).scalar_one_or_none()
    tracabilite.definir_kb_en_service(k.version if k else "")
    return k.version if k else None


@router.get("/kb/en-service")
async def kb_en_service(_u: Annotated[User, Depends(get_current_user)], db: Db) -> dict:
    d = _db(db)
    return {"version": await _synchroniser_en_service(d), "version_chargee": tracabilite.version_kb(),
            "empreinte_chargee": tracabilite.empreinte_kb()}


@router.get("/kb/versions")
async def lister_kb(_a: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    res = await d.execute(select(ConformiteKbVersion).order_by(ConformiteKbVersion.enregistree_le))
    return {"versions": [_vue_kb(k) for k in res.scalars()], "version_chargee": tracabilite.version_kb(),
            "empreinte_chargee": tracabilite.empreinte_kb()}


@router.post("/kb/versions/enregistrer", status_code=201)
async def enregistrer_kb(admin: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    """Enregistre la base actuellement chargee (version + empreinte) au statut « brouillon »."""
    d = _db(db)
    version, emp = tracabilite.version_kb(), tracabilite.empreinte_kb()
    if not version or not emp:
        raise HTTPException(status_code=409, detail="Base de connaissances absente.")
    k = await d.get(ConformiteKbVersion, version)
    if k is not None:
        if k.empreinte_sha256 != emp:
            raise HTTPException(status_code=409, detail="Cette version est déjà enregistrée avec un contenu différent : incrémentez la version.")
        return _vue_kb(k)
    k = ConformiteKbVersion(version=version, empreinte_sha256=emp, statut="brouillon", enregistree_le=chaine.maintenant_iso())
    d.add(k)
    await d.commit()
    return _vue_kb(k)


async def _kb_ou_404(d: AsyncSession, version: str) -> ConformiteKbVersion:
    k = await d.get(ConformiteKbVersion, version) if IDENT.fullmatch(version) else None
    if k is None:
        raise HTTPException(status_code=404, detail="Version inconnue.")
    return k


@router.post("/kb/versions/{version}/approuver")
async def approuver_kb(version: str, admin: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    k = await _kb_ou_404(d, version)
    if k.statut != "brouillon":
        raise HTTPException(status_code=409, detail="Seule une version au statut brouillon peut être approuvée.")
    k.statut, k.approuvee_par, k.approuvee_le = "approuvee", admin.id, chaine.maintenant_iso()
    await d.flush()
    await chaine.ajouter(d, "kb_approbation", admin.id, None, _propre({"kb": k.version, "empreinte": k.empreinte_sha256}))
    return _vue_kb(k)


@router.post("/kb/versions/{version}/mettre-en-service")
async def mettre_en_service_kb(version: str, admin: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    k = await _kb_ou_404(d, version)
    if k.statut != "approuvee":
        raise HTTPException(status_code=409, detail="Une version doit être approuvée avant sa mise en service.")
    if k.version != tracabilite.version_kb() or k.empreinte_sha256 != tracabilite.empreinte_kb():
        raise HTTPException(status_code=409, detail="La base chargée par le serveur ne correspond pas à cette version approuvée (déployer d'abord la version approuvée).")
    anc = (await d.execute(select(ConformiteKbVersion).where(ConformiteKbVersion.statut == "en_service"))).scalars().all()
    ts = chaine.maintenant_iso()
    for a in anc:
        a.statut, a.retiree_le = "retiree", ts
    k.statut, k.en_service_le = "en_service", ts
    await d.flush()
    await chaine.ajouter(d, "kb_mise_en_service", admin.id, None, _propre(
        {"kb": k.version, "empreinte": k.empreinte_sha256, "remplace": [a.version for a in anc]}))
    tracabilite.definir_kb_en_service(k.version)
    return _vue_kb(k)


@router.post("/kb/versions/{version}/retirer")
async def retirer_kb(version: str, admin: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    k = await _kb_ou_404(d, version)
    if k.statut == "retiree":
        raise HTTPException(status_code=409, detail="Version déjà retirée.")
    k.statut, k.retiree_le = "retiree", chaine.maintenant_iso()
    await d.flush()
    await chaine.ajouter(d, "kb_retrait", admin.id, None, _propre({"kb": k.version}))
    await _synchroniser_en_service(d)
    return _vue_kb(k)


# --------------------------------------------------------------------------- non-conformites (7.5, 8.7)
class NonConformiteIn(BaseModel):
    projet_id: str | None = Field(default=None, pattern=PATRON_ID)
    categorie: Categorie
    gravite: Gravite
    etape: Etape | None = None
    organe: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,60}$", description="id d'organe kb, jamais un libellé libre")
    kb_version: str | None = Field(default=None, pattern=PATRON_VERSION)
    version_pipeline: str | None = Field(default=None, pattern=PATRON_VERSION)


def _vue_nc(n: ConformiteNonConformite) -> dict:
    return {"id": n.id, "ts": n.ts, "user_id": n.user_id, "projet_hash": n.projet_hash, "categorie": n.categorie, "gravite": n.gravite,
            "etape": n.etape, "organe": n.organe, "statut": n.statut, "kb_version": n.kb_version, "version_pipeline": n.version_pipeline}


@router.post("/non-conformites", status_code=201)
async def signaler(corps: NonConformiteIn, user: Annotated[User, Depends(get_current_user)], db: Db) -> dict:
    d = _db(db)
    ph = hacher_projet(corps.projet_id) if corps.projet_id else None
    n = ConformiteNonConformite(ts=chaine.maintenant_iso(), user_id=user.id, projet_hash=ph, categorie=corps.categorie,
                                gravite=corps.gravite, etape=corps.etape, organe=corps.organe, kb_version=corps.kb_version,
                                version_pipeline=corps.version_pipeline)
    d.add(n)
    await d.flush()
    await chaine.ajouter(d, "non_conformite", user.id, ph, _propre(
        {"nc_id": n.id, "categorie": n.categorie, "gravite": n.gravite, "etape": n.etape}))
    return {"id": n.id, "statut": n.statut}


@router.get("/non-conformites")
async def lister_nc(_a: Annotated[User, Depends(get_admin_user)], db: Db,
                    statut: StatutNC | None = None) -> dict:
    d = _db(db)
    q = select(ConformiteNonConformite).order_by(ConformiteNonConformite.ts.desc()).limit(500)
    if statut:
        q = q.where(ConformiteNonConformite.statut == statut)
    lignes = list((await d.execute(q)).scalars())
    par: dict[str, int] = {}
    for n in lignes:
        par[n.categorie] = par.get(n.categorie, 0) + 1
    return {"total": len(lignes), "par_categorie": par, "non_conformites": [_vue_nc(n) for n in lignes]}


class StatutIn(BaseModel):
    statut: StatutNC


@router.patch("/non-conformites/{nc_id}")
async def changer_statut_nc(nc_id: str, corps: StatutIn, admin: Annotated[User, Depends(get_admin_user)], db: Db) -> dict:
    d = _db(db)
    n = await d.get(ConformiteNonConformite, nc_id) if IDENT.fullmatch(nc_id) else None
    if n is None:
        raise HTTPException(status_code=404, detail="Non-conformité inconnue.")
    n.statut = corps.statut
    await d.flush()
    await chaine.ajouter(d, "non_conformite_statut", admin.id, n.projet_hash, _propre({"nc_id": n.id, "statut": n.statut}))
    return _vue_nc(n)
