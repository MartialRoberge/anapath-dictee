"""Routes de l'instrumentation de l'etude.

Un prefixe a part, un fichier a part : le jour ou l'etude s'arrete, ce routeur
se retire d'une ligne dans main.py sans toucher au moteur.

Les routes sont volontairement minces. Toute la logique — et surtout tous les
invariants de la mesure — vit dans etude/service.py ; ici on authentifie, on
valide la forme, et on traduit un refus d'etude en 400 plutot qu'en 500.
"""

from datetime import datetime
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db_session
from db_models import User
from etude import service
from etude.extraction import extraire, sous_extraction
from etude.models import EtudeDossier, EtudeProposition, EtudeSession
from etude.questionnaires import CATALOGUE, fsus_pret
from etude.service import EtudeRefus

_T = TypeVar("_T")

router = APIRouter(prefix="/etude", tags=["etude"])

Utilisateur = Annotated[User, Depends(get_current_user)]
Base = Annotated[AsyncSession | None, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Modeles d'echange
# ---------------------------------------------------------------------------


class OuvertureDossier(BaseModel):
    """Ouverture d'un dossier instrumente, juste avant l'affichage du CR."""

    session_id: str
    transcription: str
    cr_propose: str
    organe: str | None = None
    t0_debut_dictee: datetime | None = None
    t1_fin_dictee: datetime | None = None
    codes: list[dict] = Field(default_factory=list)
    alertes: list[dict] = Field(default_factory=list)
    prelevements: list[dict] = Field(default_factory=list)


class PropositionAffichee(BaseModel):
    """Une proposition telle qu'elle est presentee au praticien."""

    id: str
    type: str
    sous_type: str | None
    valeur_proposee: str
    empan_debut: int | None
    empan_fin: int | None
    #: Faux quand rien dans la dictee ne soutient l'assertion. L'interface
    #: DOIT le dire au praticien : sans empan a surligner, la question posee
    #: n'est plus "est-ce fidele ?" mais "l'avez-vous dit ?".
    ancree: bool
    chemin: str | None
    confiance: float | None


class DossierOuvert(BaseModel):
    dossier_id: str
    propositions: list[PropositionAffichee]
    #: Vrai quand le dossier produit trop peu a valider pour etre exploitable.
    #: Ce n'est pas une erreur, c'est un signal a remonter a l'administration.
    sous_extraction: bool


class Decision(BaseModel):
    decision: str
    valeur_retenue: str | None = None
    #: Pourquoi la correction : style, precision, ou erreur_fond. Sans elle,
    #: une reformulation de confort compte comme une erreur du systeme.
    nature_correction: str | None = None
    cause_erreur: str | None = None
    justif_ouverte: bool = False
    justif_duree_ms: int | None = None


class Pause(BaseModel):
    debut: datetime
    fin: datetime
    cause: str


class Cloture(BaseModel):
    cr_valide: str
    omission_signalee: bool | None = None
    omission_texte: str | None = None
    nb_prelevements_corrige: int | None = None


class Abandon(BaseModel):
    motif: str


class Exclusion(BaseModel):
    motif: str
    #: Faux pour REINCLURE un dossier ecarte par erreur.
    exclu: bool = True


class Reponses(BaseModel):
    questionnaire: str
    reponses: dict[str, str]
    dossier_id: str | None = None


# ---------------------------------------------------------------------------
# Garde-fous communs
# ---------------------------------------------------------------------------


def _exiger_base(db: AsyncSession | None) -> AsyncSession:
    """Refuse explicitement plutot que de perdre une mesure en silence.

    Cote etude, une ecriture qui echoue sans bruit est pire qu'une erreur : on
    ne s'en apercevrait qu'au depouillement, sans pouvoir la reconstituer.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de donnees non disponible : la mesure ne peut pas etre enregistree.",
        )
    return db


def _ecrit(valeur: _T | None) -> _T:
    """Confirme qu'une ecriture d'etude a bien eu lieu.

    Le service renvoie None quand il n'y a pas de base ; les routes en
    garantissent une. Un None ici est donc un defaut de logique, pas un cas
    normal : mieux vaut une erreur nette qu'une mesure silencieusement perdue.
    """
    if valeur is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La mesure n'a pas ete enregistree.",
        )
    return valeur


async def _dossier_du_praticien(
    db: AsyncSession, dossier_id: str, praticien_id: str
) -> EtudeDossier:
    """Verifie que le dossier appartient bien au praticien authentifie."""
    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier introuvable.")
    session = await db.get(EtudeSession, dossier.session_id)
    if session is None or session.praticien_id != praticien_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dossier d'un autre praticien.")
    return dossier


async def _proposition_du_praticien(
    db: AsyncSession, proposition_id: str, praticien_id: str
) -> EtudeProposition:
    proposition = await db.get(EtudeProposition, proposition_id)
    if proposition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposition introuvable.")
    await _dossier_du_praticien(db, proposition.dossier_id, praticien_id)
    return proposition


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def ouvrir_session(user: Utilisateur, db: Base) -> dict[str, str]:
    """Ouvre une session de travail pour le praticien authentifie."""
    session = _ecrit(await service.ouvrir_session(_exiger_base(db), user.id))
    return {"session_id": session.id}


@router.post("/sessions/{session_id}/cloture")
async def clore_session(session_id: str, user: Utilisateur, db: Base) -> dict[str, str]:
    base = _exiger_base(db)
    session = await base.get(EtudeSession, session_id)
    if session is None or session.praticien_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session introuvable.")
    await service.clore_session(base, session_id)
    return {"statut": "close"}


# ---------------------------------------------------------------------------
# Dossier
# ---------------------------------------------------------------------------


@router.post("/dossiers", status_code=status.HTTP_201_CREATED)
async def ouvrir_dossier(
    corps: OuvertureDossier, user: Utilisateur, db: Base
) -> DossierOuvert:
    """Ouvre le dossier, extrait ses propositions et les fige a l'affichage.

    L'extraction se fait ICI et pas au moment de la generation : `affiche_a` doit
    correspondre au moment ou le praticien voit reellement les propositions,
    sinon les latences mesurent le temps de calcul du serveur.
    """
    base = _exiger_base(db)
    session = await base.get(EtudeSession, corps.session_id)
    if session is None or session.praticien_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session introuvable.")

    extraites = extraire(
        cr=corps.cr_propose,
        verbatim=corps.transcription,
        codes=corps.codes,
        alertes=corps.alertes,
    )
    dossier = _ecrit(await service.ouvrir_dossier(
        base,
        session_id=corps.session_id,
        transcription=corps.transcription,
        cr_propose=corps.cr_propose,
        propositions=extraites,
        organe=corps.organe,
        t0=corps.t0_debut_dictee,
        t1=corps.t1_fin_dictee,
    ))

    if corps.prelevements:
        await service.enregistrer_prelevements(base, dossier.id, corps.prelevements)

    return DossierOuvert(
        dossier_id=dossier.id,
        propositions=await _propositions_affichees(base, dossier.id),
        sous_extraction=sous_extraction(extraites),
    )


async def _propositions_affichees(
    db: AsyncSession, dossier_id: str
) -> list[PropositionAffichee]:
    """Relit les propositions ecrites, avec leurs identifiants de base."""
    resultat = await db.execute(
        select(EtudeProposition)
        .where(EtudeProposition.dossier_id == dossier_id)
        .order_by(EtudeProposition.type, EtudeProposition.id)
    )
    return [
        PropositionAffichee(
            id=p.id,
            type=p.type,
            sous_type=p.sous_type,
            valeur_proposee=p.valeur_proposee,
            empan_debut=p.empan_debut,
            empan_fin=p.empan_fin,
            ancree=p.empan_debut is not None,
            chemin=p.chemin,
            confiance=p.confiance,
        )
        for p in resultat.scalars().all()
    ]


@router.post("/propositions/{proposition_id}/decision")
async def decider(
    proposition_id: str, corps: Decision, user: Utilisateur, db: Base
) -> dict[str, object]:
    """Enregistre la decision du praticien sur une proposition."""
    base = _exiger_base(db)
    await _proposition_du_praticien(base, proposition_id, user.id)
    try:
        decidee = await service.enregistrer_decision(
            base,
            proposition_id,
            decision=corps.decision,
            valeur_retenue=corps.valeur_retenue,
            nature_correction=corps.nature_correction,
            cause_erreur=corps.cause_erreur,
            justif_ouverte=corps.justif_ouverte,
            justif_duree_ms=corps.justif_duree_ms,
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    decidee = _ecrit(decidee)
    return {"latence_ms": decidee.latence_ms, "hative": decidee.hative}


@router.post("/dossiers/{dossier_id}/pauses")
async def journaliser_pause(
    dossier_id: str, corps: Pause, user: Utilisateur, db: Base
) -> dict[str, str]:
    """Journalise une interruption du chronometre."""
    base = _exiger_base(db)
    await _dossier_du_praticien(base, dossier_id, user.id)
    try:
        await service.enregistrer_pause(
            base, dossier_id, corps.debut, corps.fin, corps.cause
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    return {"statut": "enregistree"}


@router.post("/dossiers/{dossier_id}/cloture")
async def clore_dossier(
    dossier_id: str, corps: Cloture, user: Utilisateur, db: Base
) -> dict[str, object]:
    """Fige le compte rendu valide et calcule la charge d'edition."""
    base = _exiger_base(db)
    await _dossier_du_praticien(base, dossier_id, user.id)
    try:
        dossier = await service.clore_dossier(
            base,
            dossier_id,
            cr_valide=corps.cr_valide,
            omission_signalee=corps.omission_signalee,
            omission_texte=corps.omission_texte,
            nb_prelevements_corrige=corps.nb_prelevements_corrige,
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    dossier = _ecrit(dossier)
    return {
        "caracteres_modifies": dossier.caracteres_modifies,
        # Le serveur dit quand le releve periodique tombe : un compteur tenu par
        # le client deriverait d'un poste a l'autre.
        "questionnaire_periodique_du": await service.periodique_est_du(base, user.id),
    }


@router.post("/dossiers/{dossier_id}/export")
async def marquer_export(
    dossier_id: str, user: Utilisateur, db: Base
) -> dict[str, str]:
    """Horodate la sortie du compte rendu (t6)."""
    base = _exiger_base(db)
    await _dossier_du_praticien(base, dossier_id, user.id)
    await service.marquer_export(base, dossier_id)
    return {"statut": "horodate"}


@router.post("/dossiers/{dossier_id}/abandon")
async def abandonner(
    dossier_id: str, corps: Abandon, user: Utilisateur, db: Base
) -> dict[str, str]:
    """Enregistre un abandon motive : la porte de sortie du praticien."""
    base = _exiger_base(db)
    await _dossier_du_praticien(base, dossier_id, user.id)
    try:
        await service.abandonner_dossier(base, dossier_id, corps.motif)
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    return {"statut": "abandonne"}


@router.get("/questionnaires/{nom}")
async def servir_questionnaire(nom: str, _user: Utilisateur) -> dict[str, object]:
    """Sert les items d'un questionnaire.

    Les libelles viennent du backend et pas du frontend : le depouillement doit
    pouvoir associer une reponse a un libelle exact des mois plus tard, et un
    libelle recopie dans un composant derive au premier remaniement.
    """
    questionnaire = CATALOGUE.get(nom)
    if questionnaire is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Questionnaire inconnu : '{nom}'.")
    porte_le_fsus = any(item.id.startswith("fsus_") for item in questionnaire.items)
    if porte_le_fsus and not fsus_pret():
        # Servir un F-SUS sans ses libelles publies produirait un score qui ne
        # se compare a rien. Mieux vaut bloquer que recolter de l'inexploitable.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Les items F-SUS n'ont pas encore recu leur formulation publiee "
            "(Gronier & Baudet, 2021). Questionnaire non servi.",
        )
    return {
        "nom": questionnaire.nom,
        "titre": questionnaire.titre,
        "duree_estimee_s": questionnaire.duree_estimee_s,
        "items": [
            {
                "id": item.id,
                "libelle": item.libelle,
                "type": item.type,
                "options": list(item.options),
                "obligatoire": item.obligatoire,
                "inverse": item.inverse,
                "depend_de": item.depend_de,
                "ancre_basse": item.ancre_basse,
                "ancre_haute": item.ancre_haute,
            }
            for item in questionnaire.items
        ],
    }


@router.post("/dossiers/{dossier_id}/exclusion")
async def exclure(
    dossier_id: str, corps: Exclusion, user: Utilisateur, db: Base
) -> dict[str, object]:
    """Ecarte un de ses propres dossiers de l'etude, sans le detruire.

    Un cas ouvert par erreur, une dictee d'essai : ils ne doivent compter dans
    aucun taux. Les EFFACER rendrait l'etude incapable de rendre compte de son
    propre effectif — une publication doit dire combien de cas ont ete ecartes
    et pourquoi. L'operation est reversible.
    """
    base = _exiger_base(db)
    await _dossier_du_praticien(base, dossier_id, user.id)
    try:
        dossier = _ecrit(
            await service.exclure_dossier(
                base, dossier_id, corps.motif, user.id, corps.exclu
            )
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    return {"exclu": dossier.exclu, "motif": dossier.motif_exclusion}


@router.post("/questionnaires", status_code=status.HTTP_201_CREATED)
async def repondre(
    corps: Reponses, user: Utilisateur, db: Base
) -> dict[str, int]:
    """Enregistre les items d'un questionnaire, un par ligne."""
    base = _exiger_base(db)
    try:
        ecrites = await service.enregistrer_reponses(
            base,
            praticien_id=user.id,
            questionnaire=corps.questionnaire,
            reponses=corps.reponses,
            dossier_id=corps.dossier_id,
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    return {"items_enregistres": ecrites}
