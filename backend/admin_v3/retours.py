"""Flux unifie des retours : signalements v3, notes v3, avis de l'ancienne version, retours de l'etude.

Garde-fou : on ne SELECTIONNE jamais ``raw_transcription`` ni ``structured_report``. Pour les avis de
l'ancienne version, on lit uniquement ``reports.completeness_warnings`` et on n'en extrait que la clef
``feedback`` (note + commentaire) ; la clef ``corrections`` du meme JSON (avant/apres, texte medical)
n'est jamais copiee dans la reponse.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Report, Signalement, TelemetrieEvenement, User
from etude.models import EtudeDossier, EtudeReponseQuestionnaire, EtudeSession

from .signalements import en_utc, iso_z, maintenant

ORIGINES = ("v3", "ancienne_version", "etude")
MAX_COMMENTAIRE = 1000

# Items de questionnaire d'etude qui sont de vrais retours d'usage (texte libre). Les autres items
# libres (localisations, « Lequel ? » apres une omission...) peuvent citer la dictee : exclus.
ITEMS_RETOUR_ETUDE = {
    "par_cas_07": "questionnaire_par_cas",
    "intention_02": "questionnaire_fin_etude",
    "intention_04": "questionnaire_fin_etude",
    "intention_05": "questionnaire_fin_etude",
}


def extraire_avis(brut: str | None) -> dict[str, Any] | None:
    """Extrait ``{note, commentaire, ts}`` du JSON ``completeness_warnings`` ; None s'il n'y a pas d'avis valable.

    N'utilise que la clef ``feedback``. Tolere un champ qui n'est pas du JSON (anciennes versions).
    """
    if not brut or '"feedback"' not in brut:
        return None
    try:
        data = json.loads(brut)
    except (json.JSONDecodeError, TypeError):
        return None
    fb = data.get("feedback") if isinstance(data, dict) else None
    if not isinstance(fb, dict):
        return None
    note = fb.get("rating")
    if isinstance(note, bool) or not isinstance(note, (int, float)) or not 1 <= int(note) <= 5:
        note = None
    commentaire = fb.get("comment")
    commentaire = commentaire.strip()[:MAX_COMMENTAIRE] if isinstance(commentaire, str) else ""
    if note is None and not commentaire:
        return None
    ts = None
    if isinstance(fb.get("timestamp"), str):
        try:
            ts = en_utc(datetime.fromisoformat(fb["timestamp"].replace("Z", "+00:00")))
        except ValueError:
            ts = None
    return {"note": int(note) if note is not None else None, "commentaire": commentaire, "ts": ts}


def _sens_depuis_note(note: int | None) -> str | None:
    if note is None:
        return None
    return "positif" if note >= 4 else "negatif" if note <= 2 else "neutre"


async def _utilisateurs(db: AsyncSession) -> dict[str, dict[str, Any]]:
    res = await db.execute(select(User.id, User.email, User.name))
    return {i: {"id": i, "email": e, "nom": n} for i, e, n in res.all()}


def _utilisateur(table: dict[str, dict[str, Any]], user_id: str | None) -> dict[str, Any]:
    return table.get(user_id or "", {"id": user_id, "email": None, "nom": None})


def _item(*, origine: str, nature: str, table: str, ref: str, categorie: str | None, sens: str | None, note: int | None,
          message: str, statut: str | None, utilisateur: dict[str, Any], ts: datetime) -> dict[str, Any]:
    return {"id": f"{table}:{ref}", "origine": origine, "nature": nature, "categorie": categorie, "sens": sens,
            "note_sur_5": note, "message": message, "statut": statut, "utilisateur": utilisateur,
            "cree_le": iso_z(ts), "ref": ref, "_ts": en_utc(ts)}


async def collecter(db: AsyncSession) -> list[dict[str, Any]]:
    """Tous les retours, de toutes origines, du plus recent au plus ancien, sans doublon."""
    users = await _utilisateurs(db)
    items: list[dict[str, Any]] = []

    # --- v3 : signalements (les doublons marques ne sont pas listes)
    for s in (await db.execute(select(Signalement).where(Signalement.doublon_de.is_(None)))).scalars():
        message = s.message or ""
        if not message and s.categorie == "non_conformite":
            message = f"Non-conformité ISO : {s.categorie_iso or 'non précisée'}, gravité {s.gravite or 'non précisée'}."
        items.append(_item(origine="v3", nature="signalement", table="signalement", ref=s.id, categorie=s.categorie,
                           sens=None, note=None, message=message, statut=s.statut,
                           utilisateur=_utilisateur(users, s.user_id), ts=s.cree_le))

    # --- v3 : notes rapides (telemetrie feedback)
    res = await db.execute(select(TelemetrieEvenement.id, TelemetrieEvenement.user_id, TelemetrieEvenement.ts,
                                  TelemetrieEvenement.payload).where(TelemetrieEvenement.type == "feedback"))
    for i, uid, ts, payload in res.all():
        payload = payload or {}
        motifs = payload.get("motifs") or []
        message = "Motifs : " + ", ".join(m for m in motifs if isinstance(m, str)) if motifs else ""
        items.append(_item(origine="v3", nature="note", table="note", ref=i, categorie=None, sens=payload.get("sens"),
                           note=None, message=message, statut=None, utilisateur=_utilisateur(users, uid), ts=ts))

    # --- ancienne version : avis (etoiles + commentaire). Colonnes choisies une a une : jamais le texte medical.
    res = await db.execute(select(Report.id, Report.user_id, Report.completeness_warnings, Report.updated_at, Report.created_at)
                           .where(Report.completeness_warnings.like('%"feedback"%')))
    for rid, uid, brut, maj, cree in res.all():
        avis = extraire_avis(brut)
        if avis is None:
            continue
        items.append(_item(origine="ancienne_version", nature="avis", table="avis", ref=rid, categorie=None,
                           sens=_sens_depuis_note(avis["note"]), note=avis["note"], message=avis["commentaire"], statut=None,
                           utilisateur=_utilisateur(users, uid), ts=avis["ts"] or maj or cree or maintenant()))

    # --- etude : commentaire de validation des dossiers, items libres de questionnaire
    res = await db.execute(
        select(EtudeDossier.id, EtudeSession.praticien_id, EtudeDossier.commentaire_validation, EtudeDossier.cree_a)
        .join(EtudeSession, EtudeDossier.session_id == EtudeSession.id)
        .where(EtudeDossier.commentaire_validation.is_not(None), EtudeDossier.exclu.is_(False)))
    for did, uid, comm, cree in res.all():
        if not (comm or "").strip():
            continue
        items.append(_item(origine="etude", nature="avis", table="etude_dossier", ref=did, categorie="commentaire_validation",
                           sens=None, note=None, message=comm.strip()[:MAX_COMMENTAIRE], statut=None,
                           utilisateur=_utilisateur(users, uid), ts=cree))
    res = await db.execute(
        select(EtudeReponseQuestionnaire.id, EtudeReponseQuestionnaire.praticien_id, EtudeReponseQuestionnaire.item,
               EtudeReponseQuestionnaire.valeur, EtudeReponseQuestionnaire.repondu_a, EtudeDossier.exclu)
        .outerjoin(EtudeDossier, EtudeReponseQuestionnaire.dossier_id == EtudeDossier.id)
        .where(EtudeReponseQuestionnaire.item.in_(list(ITEMS_RETOUR_ETUDE))))
    for rid, uid, item, valeur, ts, exclu in res.all():
        if exclu or not (valeur or "").strip():
            continue
        items.append(_item(origine="etude", nature="avis", table="etude_reponse", ref=rid, categorie=ITEMS_RETOUR_ETUDE[item],
                           sens=None, note=None, message=valeur.strip()[:MAX_COMMENTAIRE], statut=None,
                           utilisateur=_utilisateur(users, uid), ts=ts))

    # Sans doublon (meme table d'origine et meme ref), du plus recent au plus ancien.
    uniques = {it["id"]: it for it in items}
    return sorted(uniques.values(), key=lambda it: (it["_ts"], it["id"]), reverse=True)


def filtrer(items: list[dict[str, Any]], origine: str | None, categorie: str | None, statut: str | None) -> list[dict[str, Any]]:
    return [it for it in items
            if (not origine or it["origine"] == origine)
            and (not categorie or it["categorie"] == categorie)
            and (not statut or it["statut"] == statut)]


def page(items: list[dict[str, Any]], numero: int, par_page: int) -> list[dict[str, Any]]:
    debut = (numero - 1) * par_page
    return [{k: v for k, v in it.items() if k != "_ts"} for it in items[debut:debut + par_page]]
