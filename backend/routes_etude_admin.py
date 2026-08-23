"""Vues d'administration de l'etude : le macro et le micro.

Deux besoins distincts, deux routes :

- LE MACRO repond a "ou en est l'etude, et que disent les chiffres ?". Il agrege
  toutes les decisions de tous les praticiens et sort les taux avec leurs
  denominateurs. C'est le tableau qui ira dans la publication.
- LE MICRO repond a "que s'est-il passe sur CE cas ?". Il restitue un dossier
  entier : la transcription, le compte rendu propose, le compte rendu valide,
  chaque proposition avec son empan et sa decision, les pauses, les temps. C'est
  ce qui permet d'aller verifier une anomalie plutot que de la supposer.

Le micro est indispensable : un taux surprenant ne se corrige pas, il
s'explique. Sans la vue cas par cas, une anomalie reste une conjecture.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user
from database import get_db_session
from db_models import User
from etude.analyse import (
    DecisionObservee,
    DossierObserve,
    ReponseObservee,
    calculer_temps,
    moyenne,
    retenir_reponses,
    synthetiser,
    terciles,
)
from etude.service import EtudeRefus
from etude import service
from etude.models import (
    EtudeDossier,
    EtudePause,
    EtudePrelevement,
    EtudeProposition,
    EtudeReponseQuestionnaire,
    EtudeSession,
)

logger = logging.getLogger("anapath.etude.admin")

router = APIRouter(prefix="/admin/etude", tags=["admin-etude"])

Admin = Annotated[User, Depends(get_admin_user)]
Base = Annotated[AsyncSession | None, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Modeles de sortie
# ---------------------------------------------------------------------------


class LigneDossier(BaseModel):
    """Un dossier dans la liste macro."""

    id: str
    praticien_id: str
    #: Le NOM, pas seulement l'identifiant technique.
    #:
    #: Cet ecran est celui de l'administrateur de l'etude : il connait ses
    #: praticiens et doit pouvoir les reconnaitre. La pseudonymisation a sa
    #: place dans l'EXPORT, ou les donnees sortent du systeme — pas ici, ou
    #: elle ne protege personne et rend l'ecran illisible.
    praticien_nom: str
    index_session: int
    organe: str | None
    cree_a: str
    abandonne: bool
    motif_abandon: str | None
    nb_propositions: int
    nb_decidees: int
    caracteres_modifies: int | None
    revision_nette_ms: int | None
    #: Ecarte de tous les taux, mais conserve et re-inclusible.
    exclu: bool
    motif_exclusion: str | None


class PropositionDetaillee(BaseModel):
    """Une proposition telle qu'elle s'est jouee, pour la vue micro."""

    id: str
    type: str
    sous_type: str | None
    valeur_proposee: str
    chemin: str | None
    confiance: float | None
    empan_debut: int | None
    empan_fin: int | None
    #: Faux quand aucun passage de la dictee ne soutient l'assertion :
    #: candidate hallucination, a lire en priorite au depouillement.
    ancree: bool
    #: Le passage exact de la dictee, decoupe cote serveur : l'administrateur
    #: ne doit pas avoir a refaire le calcul d'offsets pour relire un cas.
    empan_extrait: str
    longueur_mots: int | None
    decision: str | None
    valeur_retenue: str | None
    cause_erreur: str | None
    latence_ms: int | None
    hative: bool
    justif_ouverte: bool
    decision_changee_apres_justif: bool
    #: L'ETAT DE PARCOURS, distinct de la decision : un bloc jamais affiche
    #: n'est pas un bloc accepte en silence.
    etat: str | None
    #: TOUTES les decisions prises sur ce bloc, dans l'ordre. Une seule ligne
    #: quand l'avis n'a pas bouge ; plusieurs quand il a change. C'est la seule
    #: facon de distinguer un clic errant d'un vrai revirement.
    revisions: list[dict[str, object]]


class DossierDetaille(BaseModel):
    """Tout ce qui s'est passe sur un cas."""

    id: str
    praticien_id: str
    praticien_nom: str
    organe: str | None
    transcription: str
    cr_propose: str
    cr_valide: str | None
    caracteres_modifies: int | None
    abandonne: bool
    motif_abandon: str | None
    omission_signalee: bool | None
    omission_texte: str | None
    nb_prelevements_detecte: int | None
    nb_prelevements_corrige: int | None
    prelevements: list[dict]
    propositions: list[PropositionDetaillee]
    temps: dict
    pauses: list[dict]


# ---------------------------------------------------------------------------
# Aides
# ---------------------------------------------------------------------------


def _exiger_base(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Base de donnees non disponible."
        )
    return db


async def _lignes(db: AsyncSession, modele, dossier_id: str) -> list:
    """Lit les filles d'un dossier. Requete explicite : pas de lazy-load async."""
    resultat = await db.execute(
        select(modele).where(modele.dossier_id == dossier_id)
    )
    return list(resultat.scalars().all())


def _observee(proposition: EtudeProposition) -> DecisionObservee:
    return DecisionObservee(
        type_proposition=proposition.type,
        decision=proposition.decision,
        hative=proposition.hative,
        latence_ms=proposition.latence_ms,
        decision_changee_apres_justif=proposition.decision_changee_apres_justif,
        nature_correction=proposition.nature_correction,
        # Pas d'empan verifie dans la dictee : rien ne soutient l'assertion.
        # C'est la definition operationnelle de "non soutenue par la dictee",
        # et le critere bloquant du protocole se lit dessus.
        ancree=proposition.empan_debut is not None,
    )


async def _pauses_du_dossier(db: AsyncSession, dossier_id: str) -> tuple[int, int]:
    """Duree totale et nombre de pauses d'un dossier."""
    pauses = await _lignes(db, EtudePause, dossier_id)
    return sum(p.duree_ms or 0 for p in pauses), len(pauses)


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------


@router.get("/synthese")
async def synthese(_admin: Admin, db: Base) -> dict[str, object]:
    """Tous les indicateurs de l'etude, avec leurs denominateurs et effectifs.

    Trois sources, et il en faut trois. Les DECISIONS donnent les taux de
    concordance. Les QUESTIONNAIRES donnent ce que la telemetrie ne peut pas
    produire : l'omission, la comprehension, l'attestation, la preference. Les
    DOSSIERS donnent les temps et la consultation des justifications. Une
    synthese batie sur les seules decisions ne couvrirait que la moitie des
    criteres du protocole.

    Les taux de decision sont calcules deux fois : toutes decisions, puis hors
    decisions hatives. L'ecart mesure combien le verrou d'export a gonfle les
    resultats — c'est un resultat en soi, pas un detail de methode.
    """
    base = _exiger_base(db)
    # Les dossiers exclus (essais, saisies aberrantes) restent en base mais
    # n'entrent dans AUCUN taux : une exclusion qui n'exclut pas serait pire
    # qu'aucune exclusion, parce qu'elle donnerait l'illusion d'un corpus propre.
    couples = await _dossiers_retenus(base)
    dossiers = [dossier for dossier, _ in couples]
    retenus = {dossier.id for dossier in dossiers}
    propositions = [
        proposition
        for proposition in (await base.execute(select(EtudeProposition))).scalars().all()
        if proposition.dossier_id in retenus
    ]

    resultat = synthetiser(
        decisions=[_observee(p) for p in propositions],
        reponses=await _reponses_retenues(base, retenus),
        dossiers=await _dossiers_observes(base, couples, propositions),
    )

    return {
        **resultat.en_dict(),
        "corpus": await _corpus(base, couples),
        "apprentissage": _apprentissage(dossiers),
    }


async def _dossiers_retenus(
    base: AsyncSession,
) -> list[tuple[EtudeDossier, str | None]]:
    """Les dossiers qui entrent dans les taux, avec leur praticien.

    Jointure EXTERNE : un dossier dont la session aurait disparu resterait dans
    le corpus. Le faire tomber ici le retirerait silencieusement de tous les
    denominateurs, ce qui est exactement ce que l'exclusion explicite existe
    pour eviter.
    """
    resultat = await base.execute(
        select(EtudeDossier, EtudeSession.praticien_id)
        .outerjoin(EtudeSession, EtudeDossier.session_id == EtudeSession.id)
        .where(EtudeDossier.exclu.is_(False))
    )
    return [(dossier, praticien_id) for dossier, praticien_id in resultat.all()]


async def _reponses_retenues(
    base: AsyncSession, retenus: set[str]
) -> list[ReponseObservee]:
    """Les reponses de questionnaire qui entrent dans les taux.

    Celles attachees a un dossier exclu sont ecartees : une exclusion qui
    n'exclut pas le questionnaire du meme cas laisserait un essai peser sur le
    taux d'omission, c'est-a-dire sur un critere de securite.
    """
    lignes = (
        await base.execute(select(EtudeReponseQuestionnaire))
    ).scalars().all()
    return retenir_reponses(
        [
            ReponseObservee(
                praticien_id=ligne.praticien_id,
                questionnaire=ligne.questionnaire,
                item=ligne.item,
                valeur=ligne.valeur,
                dossier_id=ligne.dossier_id,
                repondu_a=ligne.repondu_a,
            )
            for ligne in lignes
        ],
        retenus,
    )


async def _dossiers_observes(
    base: AsyncSession,
    couples: list[tuple[EtudeDossier, str | None]],
    propositions: list[EtudeProposition],
) -> list[DossierObserve]:
    """Reduit chaque dossier a ce que les agregats de temps ont besoin de lire."""
    pauses = await _pauses_par_dossier(base)
    consultes = {p.dossier_id for p in propositions if p.justif_ouverte}
    observes: list[DossierObserve] = []
    for dossier, praticien_id in couples:
        duree_pauses, nb_pauses = pauses.get(dossier.id, (0, 0))
        observes.append(
            DossierObserve(
                praticien_id=praticien_id or "",
                session_id=dossier.session_id,
                index_session=dossier.index_session,
                revision_nette_ms=calculer_temps(
                    dossier, duree_pauses, nb_pauses
                ).revision_nette_ms,
                justification_consultee=dossier.id in consultes,
            )
        )
    return observes


async def _pauses_par_dossier(base: AsyncSession) -> dict[str, tuple[int, int]]:
    """Duree cumulee et nombre de pauses de chaque dossier, en une requete.

    Une requete par dossier ferait grandir la synthese avec le corpus, alors
    qu'elle sera consultee d'autant plus souvent que l'etude avance.
    """
    resultat = await base.execute(
        select(
            EtudePause.dossier_id,
            func.coalesce(func.sum(EtudePause.duree_ms), 0),
            func.count(),
        ).group_by(EtudePause.dossier_id)
    )
    return {
        str(dossier_id): (int(duree), int(nombre))
        for dossier_id, duree, nombre in resultat.all()
    }


async def _corpus(
    base: AsyncSession, couples: list[tuple[EtudeDossier, str | None]]
) -> dict[str, object]:
    """Ce que contient l'etude a cet instant."""
    dossiers = [dossier for dossier, _ in couples]
    # L'EFFECTIF D'ANALYSE SE COMPTE SUR LES DOSSIERS RETENUS, pas sur les
    # sessions ouvertes. Compter les sessions faisait entrer dans le
    # denominateur du critere principal ("praticiens souhaitant continuer
    # >= 8/10") un praticien qui a seulement ouvert l'outil, ou dont tous les
    # dossiers ont ete exclus comme essais. Le nombre de praticiens recrutes
    # sans dossier exploitable reste publie a cote : c'est une information de
    # recrutement, a mettre dans le diagramme de flux, pas un effectif.
    sessions = await base.execute(select(func.count(func.distinct(EtudeSession.praticien_id))))
    analysables = {praticien for _, praticien in couples if praticien is not None}
    edites = [d.caracteres_modifies for d in dossiers if d.caracteres_modifies is not None]
    abandons = [d for d in dossiers if d.abandonne]
    return {
        "nb_praticiens": len(analysables),
        "nb_praticiens_sans_dossier": max(
            0, int(sessions.scalar_one()) - len(analysables)
        ),
        "nb_dossiers": len(dossiers),
        # Compte a part et TOUJOURS affiche : une publication doit dire combien
        # de cas ont ete ecartes et pourquoi.
        "nb_exclus": await _compter_exclus(base),
        # Un abandon horodate t5 lui aussi : sans le filtre, il comptait a la
        # fois comme clos et comme abandonne, et "en cours" (nb_dossiers moins
        # nb_dossiers_clos) sous-estimait les dossiers reellement inacheves.
        "nb_dossiers_clos": sum(
            1 for d in dossiers if d.t5_cloture is not None and not d.abandonne
        ),
        "nb_abandons": len(abandons),
        "motifs_abandon": _compter(d.motif_abandon for d in abandons),
        "organes": _compter(d.organe for d in dossiers),
        "caracteres_modifies_moyen": moyenne([float(v) for v in edites]),
    }


async def _compter_exclus(base: AsyncSession) -> int:
    resultat = await base.execute(
        select(func.count())
        .select_from(EtudeDossier)
        .where(EtudeDossier.exclu.is_(True))
    )
    return int(resultat.scalar_one())


def _compter(valeurs) -> dict[str, int]:
    """Effectifs par valeur, en ignorant les absences."""
    compte: dict[str, int] = {}
    for valeur in valeurs:
        if valeur:
            compte[valeur] = compte.get(valeur, 0) + 1
    return dict(sorted(compte.items(), key=lambda paire: -paire[1]))


def _apprentissage(dossiers: list[EtudeDossier]) -> dict[str, object]:
    """Charge d'edition par tercier d'ordre de passage.

    Si elle baisse du premier au dernier tercile, c'est le praticien qui
    s'habitue — pas l'outil qui s'ameliore. Sans ce decoupage, on publierait
    l'un pour l'autre.
    """
    ordonnes = sorted(
        (d for d in dossiers if d.caracteres_modifies is not None),
        key=lambda d: (d.session_id, d.index_session),
    )
    valeurs = [float(d.caracteres_modifies or 0) for d in ordonnes]
    debut, milieu, fin = terciles(valeurs)
    return {
        "caracteres_modifies_par_tercile": [
            moyenne(debut), moyenne(milieu), moyenne(fin)
        ],
        "nb_dossiers_retenus": len(valeurs),
    }


@router.get("/dossiers")
async def lister_dossiers(_admin: Admin, db: Base) -> list[LigneDossier]:
    """Tous les dossiers de l'etude, du plus recent au plus ancien."""
    base = _exiger_base(db)
    resultat = await base.execute(
        select(EtudeDossier, EtudeSession.praticien_id, User.name)
        .join(EtudeSession, EtudeDossier.session_id == EtudeSession.id)
        .outerjoin(User, EtudeSession.praticien_id == User.id)
        .order_by(EtudeDossier.cree_a.desc())
    )
    lignes: list[LigneDossier] = []
    for dossier, praticien_id, praticien_nom in resultat.all():
        propositions = await _lignes(base, EtudeProposition, dossier.id)
        pauses_ms, nb_pauses = await _pauses_du_dossier(base, dossier.id)
        lignes.append(
            LigneDossier(
                id=dossier.id,
                praticien_id=praticien_id,
                praticien_nom=praticien_nom or praticien_id,
                index_session=dossier.index_session,
                organe=dossier.organe,
                cree_a=dossier.cree_a.isoformat(),
                abandonne=dossier.abandonne,
                motif_abandon=dossier.motif_abandon,
                nb_propositions=len(propositions),
                nb_decidees=sum(1 for p in propositions if p.decision is not None),
                caracteres_modifies=dossier.caracteres_modifies,
                exclu=dossier.exclu,
                motif_exclusion=dossier.motif_exclusion,
                revision_nette_ms=calculer_temps(
                    dossier, pauses_ms, nb_pauses
                ).revision_nette_ms,
            )
        )
    return lignes


# ---------------------------------------------------------------------------
# Micro
# ---------------------------------------------------------------------------


@router.get("/dossiers/{dossier_id}")
async def detailler_dossier(
    dossier_id: str, _admin: Admin, db: Base
) -> DossierDetaille:
    """Tout ce qui s'est passe sur un cas.

    Un taux surprenant ne se corrige pas, il s'explique : sans cette vue, une
    anomalie reste une conjecture.
    """
    base = _exiger_base(db)
    dossier = await base.get(EtudeDossier, dossier_id)
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier introuvable.")
    session = await base.get(EtudeSession, dossier.session_id)
    praticien = await base.get(User, session.praticien_id) if session else None

    propositions = await _lignes(base, EtudeProposition, dossier_id)
    prelevements = await _lignes(base, EtudePrelevement, dossier_id)
    pauses = await _lignes(base, EtudePause, dossier_id)
    pauses_ms = sum(p.duree_ms or 0 for p in pauses)

    return DossierDetaille(
        id=dossier.id,
        praticien_id=session.praticien_id if session else "",
        praticien_nom=(praticien.name if praticien else None)
        or (session.praticien_id if session else ""),
        organe=dossier.organe,
        transcription=dossier.transcription,
        cr_propose=dossier.cr_propose,
        cr_valide=dossier.cr_valide,
        caracteres_modifies=dossier.caracteres_modifies,
        abandonne=dossier.abandonne,
        motif_abandon=dossier.motif_abandon,
        omission_signalee=dossier.omission_signalee,
        omission_texte=dossier.omission_texte,
        nb_prelevements_detecte=dossier.nb_prelevements_detecte,
        nb_prelevements_corrige=dossier.nb_prelevements_corrige,
        prelevements=[
            {"rang": p.rang, "libelle": p.libelle, "codes": p.codes}
            for p in sorted(prelevements, key=lambda p: p.rang)
        ],
        propositions=[
            _detailler(p, dossier.transcription) for p in propositions
        ],
        temps=calculer_temps(dossier, pauses_ms, len(pauses)).en_dict(),
        pauses=[
            {
                "debut": p.debut.isoformat(),
                "fin": p.fin.isoformat() if p.fin else None,
                "duree_ms": p.duree_ms,
                "cause": p.cause,
            }
            for p in pauses
        ],
    )


def _detailler(
    proposition: EtudeProposition, transcription: str
) -> PropositionDetaillee:
    """Restitue une proposition avec le passage de dictee qu'elle vise."""
    debut = proposition.empan_debut
    fin = proposition.empan_fin
    extrait = (
        transcription[debut:fin]
        if debut is not None and fin is not None and fin > debut
        else ""
    )
    return PropositionDetaillee(
        id=proposition.id,
        type=proposition.type,
        sous_type=proposition.sous_type,
        valeur_proposee=proposition.valeur_proposee,
        chemin=proposition.chemin,
        confiance=proposition.confiance,
        empan_debut=debut,
        empan_fin=fin,
        ancree=debut is not None,
        empan_extrait=extrait,
        longueur_mots=proposition.longueur_mots,
        decision=proposition.decision,
        valeur_retenue=proposition.valeur_retenue,
        cause_erreur=proposition.cause_erreur,
        latence_ms=proposition.latence_ms,
        hative=proposition.hative,
        justif_ouverte=proposition.justif_ouverte,
        decision_changee_apres_justif=proposition.decision_changee_apres_justif,
        etat=proposition.etat,
        revisions=[
            {
                "rang": revision.rang,
                "decision": revision.decision,
                "etat": revision.etat,
                "valeur_retenue": revision.valeur_retenue,
                "nature_correction": revision.nature_correction,
                "cause_erreur": revision.cause_erreur,
                "justif_ouverte": revision.justif_ouverte,
                "decide_a": revision.decide_a.isoformat(),
            }
            for revision in proposition.revisions
        ],
    )


class Exclusion(BaseModel):
    motif: str
    #: Faux pour REINCLURE un dossier ecarte par erreur.
    exclu: bool = True


@router.post("/dossiers/{dossier_id}/exclusion")
async def exclure(
    dossier_id: str, corps: Exclusion, admin: Admin, db: Base
) -> dict[str, object]:
    """Ecarte n'importe quel dossier de l'etude, sans le detruire.

    L'administrateur teste lui-meme l'outil sans etre pathologiste, et des
    saisies aberrantes arrivent. Ces cas ne doivent entrer dans aucun taux — mais
    les effacer empecherait de rendre compte de l'effectif ecarte, que toute
    publication demande. Reversible.
    """
    base = _exiger_base(db)
    try:
        dossier = await service.exclure_dossier(
            base, dossier_id, corps.motif, admin.id, corps.exclu
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier introuvable.")
    return {
        "exclu": dossier.exclu,
        "motif": dossier.motif_exclusion,
    }


@router.delete("/dossiers/{dossier_id}")
async def supprimer(dossier_id: str, admin: Admin, db: Base) -> dict[str, bool]:
    """Detruit definitivement un dossier d'essai.

    A n'utiliser QUE tant que l'etude n'a pas commence : ces dossiers-la sont
    des mises au point et des demonstrations, ils n'ont jamais fait partie de la
    population etudiee. Une fois l'etude lancee, c'est `exclusion` qu'il faut —
    effacer un cas rendrait l'etude incapable de rendre compte de son effectif.

    Sans retour possible : le frontend doit demander confirmation.
    """
    base = _exiger_base(db)
    supprime = await service.supprimer_dossier(base, dossier_id)
    if not supprime:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier introuvable.")
    logger.warning(
        "Dossier %s supprime definitivement par %s.", dossier_id, admin.id
    )
    return {"supprime": True}
