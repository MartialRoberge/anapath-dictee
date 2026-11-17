"""Circuit UNIQUE de signalement : table ``signalements``, filtre anti-donnees-patient, dedoublonnage.

Ce module porte la logique (pure, testable) ; les routes sont en bas : ``POST /v3/signalements``.
Les routes conformite de non-conformites (conformite/routes.py) s'appuient sur les memes fonctions.
"""
import difflib
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import insert, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db_session
from db_models import ConformiteNonConformite, Signalement, User
from rate_limit import limiter

logger = logging.getLogger("anapath.signalements")

CATEGORIES = ("dysfonctionnement", "erreur_projet", "amelioration", "non_conformite")
STATUTS = ("ouvert", "en_cours", "traite", "rejete")
MAX_MESSAGE = 1000
MAX_NOTE_ADMIN = 1000
FENETRE_DOUBLON = timedelta(minutes=10)
SEUIL_SIMILITUDE = 0.9

# Passerelle avec le vocabulaire ISO historique des non-conformites.
_NC_VERS_STATUT = {"ouverte": "ouvert", "en_analyse": "en_cours", "cloturee": "traite"}
_STATUT_VERS_NC = {"ouvert": "ouverte", "en_cours": "en_analyse", "traite": "cloturee", "rejete": "cloturee"}


def statut_nc(statut: str) -> str:
    return _STATUT_VERS_NC.get(statut, "ouverte")


def statut_depuis_nc(statut: str) -> str:
    return _NC_VERS_STATUT.get(statut, "ouvert")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def en_utc(d: datetime | None) -> datetime | None:
    """SQLite rend des datetimes naifs : on les lit comme UTC."""
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso_z(d: datetime | None) -> str | None:
    d = en_utc(d)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def iso_us(d: datetime | None) -> str | None:
    """Format historique des non-conformites (microsecondes)."""
    d = en_utc(d)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if d else None


# --------------------------------------------------------------------------- donnees patient
_MOIS = r"(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)"
_PATRONS_PATIENT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("un numéro de sécurité sociale (NIR)",
     re.compile(r"(?<!\d)[1-478]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?(?:\d{2}|2[AB])\s?\d{3}\s?\d{3}(?:\s?\d{2})?(?!\d)", re.I)),
    ("une date de naissance",
     re.compile(r"\b(?:n[ée]e?s?\s+(?:le|en)|date\s+de\s+naissance|ddn|dob)\b", re.I)),
    ("une date complète",
     re.compile(r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])\s?[/.\-]\s?(?:0?[1-9]|1[0-2])\s?[/.\-]\s?(?:\d{4}|\d{2})(?!\d)")),
    ("une date complète", re.compile(r"(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)")),
    ("un numéro (téléphone, dossier ou identifiant)",
     re.compile(r"(?<!\d)(?:\d[\s.\-]?){9,}(?!\d)")),
    ("une adresse e-mail", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("un nom de personne",
     re.compile(r"(?i:\b(?:mme|mlle|mr|monsieur|madame|mademoiselle|m)\b\.?)\s+[A-ZÀ-ÝŒ][a-zà-ÿœ'’-]{2,}")),
    ("un nom de patient",
     re.compile(r"(?i:\bpatient(?:e)?\s*(?:nomm[ée]e?|:|s'appelle))\s*[A-ZÀ-ÝŒ]")),
)


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def detecter_donnee_patient(texte: str) -> str | None:
    """Retourne ce qui ressemble a une donnee patient (libelle francais), ou None.

    Volontairement prudent : mieux vaut refuser un message qui n'en est pas un que laisser entrer
    un nom, une date de naissance ou un NIR dans une table lisible par l'administration.
    """
    for libelle, patron in _PATRONS_PATIENT:
        if patron.search(texte):
            return libelle
    sans = _sans_accents(texte).lower()
    if re.search(rf"(?<!\d)\d{{1,2}}(?:er)?\s+{_MOIS}\s+(?:19|20)\d{{2}}", sans):
        return "une date complète"
    return None


def message_refus(libelle: str) -> str:
    return (f"Votre message semble contenir {libelle}. Pour protéger les patients, n'écrivez aucune donnée "
            "identifiante (nom, date, numéro de sécurité sociale, téléphone, e-mail) : décrivez le problème sans elle.")


def normaliser(texte: str) -> str:
    sans = _sans_accents(texte).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sans).split())


def quasi_identiques(a: str, b: str) -> bool:
    na, nb = normaliser(a), normaliser(b)
    if na == nb:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= SEUIL_SIMILITUDE


# --------------------------------------------------------------------------- creation + dedoublonnage
async def trouver_doublon(db: AsyncSession, *, user_id: str, categorie: str, projet_hash: str | None,
                          message: str, categorie_iso: str | None = None, gravite: str | None = None,
                          maintenant_: datetime | None = None) -> Signalement | None:
    """Signalement du MEME utilisateur, MEME categorie, MEME projet, message quasi identique, < 10 min."""
    depuis = (maintenant_ or maintenant()) - FENETRE_DOUBLON
    q = select(Signalement).where(
        Signalement.user_id == user_id, Signalement.categorie == categorie, Signalement.cree_le >= depuis,
        Signalement.doublon_de.is_(None),
    ).order_by(Signalement.cree_le.desc())
    q = q.where(Signalement.projet_hash.is_(None) if projet_hash is None else Signalement.projet_hash == projet_hash)
    for s in (await db.execute(q)).scalars():
        if categorie == "non_conformite" and (s.categorie_iso != categorie_iso or s.gravite != gravite):
            continue
        if quasi_identiques(s.message or "", message):
            return s
    return None


async def creer_signalement(db: AsyncSession, **champs: Any) -> tuple[Signalement, bool]:
    """Cree un signalement, ou renvoie l'existant s'il s'agit d'un doublon. Retourne (ligne, est_nouveau).

    Ne commit pas : l'appelant commit (ou ecrit l'audit, qui commit).
    """
    existant = await trouver_doublon(
        db, user_id=champs["user_id"], categorie=champs["categorie"], projet_hash=champs.get("projet_hash"),
        message=champs.get("message", ""), categorie_iso=champs.get("categorie_iso"), gravite=champs.get("gravite"))
    if existant is not None:
        return existant, False
    ts = maintenant()
    s = Signalement(cree_le=ts, maj_le=ts, statut="ouvert", **champs)
    db.add(s)
    await db.flush()
    return s, True


def vue_signalement(s: Signalement) -> dict[str, Any]:
    return {"id": s.id, "user_id": s.user_id, "categorie": s.categorie, "message": s.message, "projet_hash": s.projet_hash,
            "ecran": s.ecran, "version_app": s.version_app, "statut": s.statut, "note_admin": s.note_admin,
            "cree_le": iso_z(s.cree_le), "maj_le": iso_z(s.maj_le), "doublon_de": s.doublon_de,
            "gravite": s.gravite, "categorie_iso": s.categorie_iso}


# --------------------------------------------------------------------------- recopie idempotente (demarrage)
def _lire_ts(ts: str | None) -> datetime:
    try:
        return en_utc(datetime.fromisoformat((ts or "").replace("Z", "+00:00"))) or maintenant()
    except ValueError:
        return maintenant()


def recopier_non_conformites(connexion: Any) -> int:
    """Recopie vers ``signalements`` les lignes de ``conformite_non_conformites`` pas encore recopiees.

    ADDITIF ET IDEMPOTENT : la table ancienne n'est ni modifiee ni supprimee ; chaque ligne recopiee
    porte ``origine_nc_id`` (index unique), donc un second passage ne recopie rien. Retourne le nombre
    de lignes recopiees.
    """
    insp = sa_inspect(connexion)
    if not (insp.has_table("conformite_non_conformites") and insp.has_table("signalements")):
        return 0
    nc, sg = ConformiteNonConformite.__table__, Signalement.__table__
    deja = {r[0] for r in connexion.execute(select(sg.c.origine_nc_id).where(sg.c.origine_nc_id.is_not(None)))}
    nouvelles = []
    for n in connexion.execute(select(nc)).mappings():
        if n["id"] in deja:
            continue
        ts = _lire_ts(n["ts"])
        nouvelles.append({
            "id": n["id"], "user_id": n["user_id"], "categorie": "non_conformite", "message": "",
            "projet_hash": n["projet_hash"], "statut": statut_depuis_nc(n["statut"] or "ouverte"),
            "cree_le": ts, "maj_le": ts, "categorie_iso": n["categorie"], "gravite": n["gravite"], "etape": n["etape"],
            "organe": n["organe"], "kb_version": n["kb_version"], "version_pipeline": n["version_pipeline"],
            "origine_nc_id": n["id"],
        })
    if nouvelles:
        connexion.execute(insert(sg), nouvelles)
        logger.warning("Recopie des non-conformites vers signalements : %d ligne(s).", len(nouvelles))
    return len(nouvelles)


# --------------------------------------------------------------------------- route POST /v3/signalements
router = APIRouter(prefix="/v3", tags=["signalements"])

Categorie = Literal["dysfonctionnement", "erreur_projet", "amelioration", "non_conformite"]


class SignalementIn(BaseModel):
    categorie: Categorie
    message: str
    projet_id: str | None = None
    ecran: str | None = None
    version_app: str | None = None


_ECRAN = re.compile(r"^[A-Za-z0-9_./:-]{1,60}$")
_VERSION = re.compile(r"^[A-Za-z0-9_.+-]{1,60}$")
_PROJET = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@router.post("/signalements")
@limiter.limit("30/minute")
async def signaler(
    request: Request,
    corps: SignalementIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, Any]:
    """Cree un signalement (ou renvoie l'existant si doublon recent). Reponse : ``{id, doublon_de}``."""
    from conformite import chaine  # import tardif : conformite importe ce module
    from telemetrie.routes import hacher_projet

    if db is None:
        raise HTTPException(status_code=503, detail="Base de données non disponible")
    message = corps.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Le message est vide : décrivez le problème en quelques mots.")
    if len(message) > MAX_MESSAGE:
        raise HTTPException(status_code=422, detail=f"Le message est trop long ({len(message)} caractères) : {MAX_MESSAGE} au maximum.")
    trouve = detecter_donnee_patient(message)
    if trouve:
        raise HTTPException(status_code=422, detail=message_refus(trouve))
    if corps.projet_id is not None and not _PROJET.fullmatch(corps.projet_id):
        raise HTTPException(status_code=422, detail="Identifiant de projet invalide.")
    if corps.ecran is not None and not _ECRAN.fullmatch(corps.ecran):
        raise HTTPException(status_code=422, detail="Nom d'écran invalide.")
    if corps.version_app is not None and not _VERSION.fullmatch(corps.version_app):
        raise HTTPException(status_code=422, detail="Version d'application invalide.")
    ph = hacher_projet(corps.projet_id) if corps.projet_id else None
    s, nouveau = await creer_signalement(
        db, user_id=user.id, categorie=corps.categorie, message=message, projet_hash=ph,
        ecran=corps.ecran, version_app=corps.version_app)
    if nouveau:
        if corps.categorie == "non_conformite":  # le circuit ISO garde sa trace chainee
            await chaine.ajouter(db, "non_conformite", user.id, ph, {"nc_id": s.id, "categorie": "signalement_libre"})
        else:
            await db.commit()
        return {"id": s.id, "doublon_de": None}
    return {"id": s.id, "doublon_de": s.id}
