"""Etat de sante de la base (lecture seule) : volumes par table et controles d'integrite."""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conformite import chaine, tracabilite
from db_models import Base, Report, Signalement, TelemetrieEvenement, User
from etude.models import (
    EtudeDossier, EtudeErgonomie, EtudePause, EtudePrelevement, EtudeProposition, EtudeQuestion,
    EtudeReponseQuestionnaire, EtudeRevisionDecision, EtudeSession,
)

from .signalements import normaliser


async def _n(db: AsyncSession, requete: Any) -> int:
    return int((await db.execute(requete)).scalar_one())


def _orphelins(modele: Any, cle: Any, parent: Any) -> Any:
    return select(func.count()).select_from(modele).where(cle.is_not(None), cle.not_in(select(parent)))


async def _controle_orphelins(db: AsyncSession) -> tuple[bool, str]:
    mesures = {
        "reports sans utilisateur": await _n(db, _orphelins(Report, Report.user_id, User.id)),
        "télémétrie sans utilisateur": await _n(db, _orphelins(TelemetrieEvenement, TelemetrieEvenement.user_id, User.id)),
        "signalements sans utilisateur": await _n(db, _orphelins(Signalement, Signalement.user_id, User.id)),
        "etude_sessions sans utilisateur": await _n(db, _orphelins(EtudeSession, EtudeSession.praticien_id, User.id)),
        "etude_dossiers sans session": await _n(db, _orphelins(EtudeDossier, EtudeDossier.session_id, EtudeSession.id)),
        "etude_prelevements sans dossier": await _n(db, _orphelins(EtudePrelevement, EtudePrelevement.dossier_id, EtudeDossier.id)),
        "etude_propositions sans dossier": await _n(db, _orphelins(EtudeProposition, EtudeProposition.dossier_id, EtudeDossier.id)),
        "etude_questions sans dossier": await _n(db, _orphelins(EtudeQuestion, EtudeQuestion.dossier_id, EtudeDossier.id)),
        "etude_pauses sans dossier": await _n(db, _orphelins(EtudePause, EtudePause.dossier_id, EtudeDossier.id)),
        "etude_ergonomie sans dossier": await _n(db, _orphelins(EtudeErgonomie, EtudeErgonomie.dossier_id, EtudeDossier.id)),
        "etude_reponses_questionnaire sans dossier": await _n(db, _orphelins(EtudeReponseQuestionnaire, EtudeReponseQuestionnaire.dossier_id, EtudeDossier.id)),
        "etude_revisions_decision sans proposition": await _n(db, _orphelins(EtudeRevisionDecision, EtudeRevisionDecision.proposition_id, EtudeProposition.id)),
    }
    trouves = {k: v for k, v in mesures.items() if v}
    if not trouves:
        return True, "Aucun orphelin (reports, télémétrie, signalements, tables etude_*)."
    return False, "; ".join(f"{k} : {v}" for k, v in trouves.items())


async def _controle_doublons_comptes(db: AsyncSession) -> tuple[bool, str]:
    res = await db.execute(select(func.lower(User.email), func.count()).group_by(func.lower(User.email)).having(func.count() > 1))
    doublons = res.all()
    if not doublons:
        return True, "Aucun e-mail en double (casse ignorée)."
    return False, f"{len(doublons)} e-mail(s) en double, par exemple : " + ", ".join(e for e, _ in doublons[:5])


async def _controle_comptes_test(db: AsyncSession) -> tuple[bool, str]:
    n = await _n(db, select(func.count()).select_from(User).where(func.lower(User.email).like("%@example.com")))
    return (n == 0, "Aucun compte de test (@example.com)." if n == 0 else f"{n} compte(s) de test (@example.com) : à passer en revue.")


async def _controle_chaine(db: AsyncSession) -> tuple[bool, str]:
    v = await chaine.verifier(db)
    if v.ok:
        return True, f"Chaîne intègre : {v.nb_entrees} entrée(s) vérifiée(s)."
    return False, f"Rupture à l'entrée {v.rupture_seq} : {v.motif}."


async def _controle_signalements_doubles(db: AsyncSession) -> tuple[bool, str]:
    res = await db.execute(select(Signalement.user_id, Signalement.categorie, Signalement.projet_hash, Signalement.message)
                           .where(Signalement.message != "", Signalement.doublon_de.is_(None)))
    c = Counter((u, cat, ph, normaliser(m)) for u, cat, ph, m in res.all())
    surplus = sum(n - 1 for n in c.values() if n > 1)
    marques = await _n(db, select(func.count()).select_from(Signalement).where(Signalement.doublon_de.is_not(None)))
    if not surplus and not marques:
        return True, "Aucun signalement en double."
    return False, f"{surplus} signalement(s) en double (même utilisateur, catégorie, projet et message), {marques} marqué(s) doublon_de."


async def _controle_recopie(db: AsyncSession) -> tuple[bool, str]:
    from db_models import ConformiteNonConformite as NC
    anciennes = await _n(db, select(func.count()).select_from(NC))
    recopiees = await _n(db, select(func.count()).select_from(Signalement).where(Signalement.origine_nc_id.is_not(None)))
    ok = recopiees >= anciennes
    return ok, f"{recopiees} non-conformité(s) recopiée(s) sur {anciennes} dans l'ancienne table (conservée)."


def _tables_modeles() -> list[Any]:
    return sorted(Base.metadata.sorted_tables, key=lambda t: t.name)


async def calculer(db: AsyncSession) -> dict[str, Any]:
    tables = []
    for t in _tables_modeles():
        try:
            tables.append({"nom": t.name, "lignes": await _n(db, select(func.count()).select_from(t))})
        except Exception as exc:  # noqa: BLE001 - table absente : on le dit, on ne plante pas
            await db.rollback()
            tables.append({"nom": t.name, "lignes": None, "erreur": type(exc).__name__})

    vides = [t["nom"] for t in tables if t["lignes"] == 0]
    controles: list[dict[str, Any]] = []
    for nom, f in (("orphelins", _controle_orphelins), ("doublons_comptes", _controle_doublons_comptes),
                   ("comptes_de_test", _controle_comptes_test), ("chaine_audit", _controle_chaine),
                   ("signalements_en_double", _controle_signalements_doubles),
                   ("recopie_non_conformites", _controle_recopie)):
        try:
            ok, detail = await f(db)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            ok, detail = False, f"Contrôle impossible : {type(exc).__name__}."
        controles.append({"nom": nom, "ok": ok, "detail": detail})
    controles.append({"nom": "tables_jamais_ecrites", "ok": not vides,
                      "detail": ("Aucune table vide." if not vides else
                                 f"{len(vides)} table(s) vide(s) : {', '.join(vides)} (informatif : une table vide n'est pas une erreur).")})
    return {"version": tracabilite.version_pipeline(),
            "base": {"type": db.get_bind().dialect.name, "tables": tables},
            "controles": controles}
