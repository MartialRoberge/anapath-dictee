"""Ecritures de l'instrumentation : ouvrir, decider, clore.

Ce module est le SEUL endroit qui ecrit dans les tables etude_*. Les invariants
de la mesure y sont appliques en code, pas confies a l'appelant :

- `cr_propose` est fige a la creation et jamais reecrit. Sans le texte propose
  a cote du texte valide, la charge d'edition n'est pas calculable — et c'est
  irrattrapable apres coup.
- une decision est verifiee contre la grille de SON type. Ecrire "non_dicte"
  sur une completude fausserait le taux d'hallucination au depouillement.
- `latence_ms` et `hative` sont calcules ici a partir des horodatages serveur.
  Un client qui enverrait ses propres latences pourrait les rendre flatteuses.

Toutes les fonctions acceptent une session nulle : en developpement sans base,
l'instrumentation est inerte et ne doit jamais faire echouer une generation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from etude.extraction import PropositionExtraite
from etude.models import (
    EtudeDossier,
    EtudePause,
    EtudePrelevement,
    EtudeProposition,
    EtudeReponseQuestionnaire,
    EtudeSession,
)
from etude.vocabulaire import (
    CAUSES_ERREUR,
    CAUSES_PAUSE,
    MOTIFS_ABANDON,
    NATURES_CORRECTION,
    QUESTIONNAIRES,
    decision_valide,
    est_hative,
    periodique_du,
)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def _en_utc(moment: datetime) -> datetime:
    """Rend un horodatage relu comparable a l'heure courante.

    PostgreSQL restitue un datetime avec fuseau, SQLite un datetime nu. Soustraire
    l'un de l'autre leve une TypeError : le calcul de latence casserait en
    developpement, la ou tourne justement le rodage avec les praticiens. Les
    colonnes sont ecrites en UTC, on remet donc le fuseau quand il manque.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class EtudeRefus(ValueError):
    """Ecriture refusee parce qu'elle detruirait une mesure.

    Distincte d'une erreur technique : elle signale une tentative de corrompre
    la donnee d'etude, et doit remonter en 4xx, pas en 5xx.
    """


# --- Session ---------------------------------------------------------------


async def ouvrir_session(
    db: AsyncSession | None, praticien_id: str
) -> EtudeSession | None:
    """Ouvre une session de travail pour un praticien."""
    if db is None:
        return None
    session = EtudeSession(praticien_id=praticien_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def clore_session(db: AsyncSession | None, session_id: str) -> None:
    """Ferme la session et fige son nombre de cas."""
    if db is None:
        return
    session = await db.get(EtudeSession, session_id)
    if session is None:
        return
    session.fin = _maintenant()
    session.nb_cas = await _compter_dossiers(db, session_id)
    await db.commit()


async def _compter_dossiers(db: AsyncSession, session_id: str) -> int:
    resultat = await db.execute(
        select(func.count())
        .select_from(EtudeDossier)
        .where(EtudeDossier.session_id == session_id)
    )
    return int(resultat.scalar_one())


# --- Dossier ---------------------------------------------------------------


async def ouvrir_dossier(
    db: AsyncSession | None,
    session_id: str,
    transcription: str,
    cr_propose: str,
    propositions: list[PropositionExtraite],
    organe: str | None = None,
    t0: datetime | None = None,
    t1: datetime | None = None,
) -> EtudeDossier | None:
    """Cree le dossier, fige le texte propose et enregistre ses propositions.

    Les propositions sont ecrites en meme temps que le dossier : une proposition
    creee plus tard n'aurait pas d'`affiche_a` fiable, donc pas de latence, donc
    pas de marquage `hative`.
    """
    if db is None:
        return None

    dossier = EtudeDossier(
        session_id=session_id,
        index_session=await _compter_dossiers(db, session_id),
        transcription=transcription,
        cr_propose=cr_propose,
        organe=organe,
        t0_debut_dictee=t0,
        t1_fin_dictee=t1,
        t2_affichage=_maintenant(),
    )
    db.add(dossier)
    await db.flush()

    affiche_a = dossier.t2_affichage
    for extraite in propositions:
        db.add(_vers_ligne(dossier.id, extraite, affiche_a))

    await db.commit()
    await db.refresh(dossier)
    return dossier


def _vers_ligne(
    dossier_id: str, extraite: PropositionExtraite, affiche_a: datetime | None
) -> EtudeProposition:
    """Convertit une proposition extraite en ligne de base."""
    return EtudeProposition(
        dossier_id=dossier_id,
        type=extraite.type_proposition,
        sous_type=extraite.sous_type,
        valeur_proposee=extraite.valeur_proposee,
        chemin=extraite.chemin,
        confiance=extraite.confiance,
        empan_debut=extraite.empan_debut,
        empan_fin=extraite.empan_fin,
        longueur_mots=extraite.longueur_mots,
        affiche_a=affiche_a,
    )


async def enregistrer_prelevements(
    db: AsyncSession | None,
    dossier_id: str,
    prelevements: list[dict[str, object]],
) -> None:
    """Enregistre les prelevements detectes et leurs codes.

    Un prelevement par ligne : c'est cette cardinalite qui permet de mesurer un
    code juste et un code faux dans le meme dossier plutot qu'une moyenne.
    """
    if db is None:
        return
    for rang, prelevement in enumerate(prelevements, start=1):
        db.add(
            EtudePrelevement(
                dossier_id=dossier_id,
                rang=rang,
                libelle=str(prelevement.get("libelle") or ""),
                codes=json.dumps(prelevement.get("codes") or [], ensure_ascii=False),
            )
        )
    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is not None:
        dossier.nb_prelevements_detecte = len(prelevements)
    await db.commit()


# --- Decision --------------------------------------------------------------


async def enregistrer_decision(
    db: AsyncSession | None,
    proposition_id: str,
    decision: str,
    valeur_retenue: str | None = None,
    nature_correction: str | None = None,
    cause_erreur: str | None = None,
    justif_ouverte: bool = False,
    justif_duree_ms: int | None = None,
) -> EtudeProposition | None:
    """Enregistre la decision du praticien sur une proposition.

    La latence est calculee cote serveur depuis `affiche_a` : une latence
    fournie par le client pourrait etre rendue flatteuse, et c'est elle qui
    fonde le marquage `hative`.
    """
    if db is None:
        return None

    proposition = await db.get(EtudeProposition, proposition_id)
    if proposition is None:
        raise EtudeRefus("Proposition introuvable.")
    if not decision_valide(proposition.type, decision):
        raise EtudeRefus(
            f"Decision '{decision}' hors grille pour le type '{proposition.type}'."
        )
    if cause_erreur is not None and cause_erreur not in CAUSES_ERREUR:
        raise EtudeRefus(f"Cause d'erreur inconnue : '{cause_erreur}'.")
    if nature_correction is not None and nature_correction not in NATURES_CORRECTION:
        raise EtudeRefus(f"Nature de correction inconnue : '{nature_correction}'.")
    if cause_erreur is not None and nature_correction not in (None, "erreur_fond"):
        # Demander la cause d'une reformulation de style n'a pas de sens : la
        # cause qualifie une ERREUR, et une correction de style n'en est pas une.
        raise EtudeRefus(
            "Une cause d'erreur ne se renseigne que sur une erreur de fond."
        )

    _appliquer_decision(
        proposition, decision, valeur_retenue, nature_correction, cause_erreur,
        justif_ouverte, justif_duree_ms,
    )
    await _horodater_dossier(db, proposition)
    await db.commit()
    await db.refresh(proposition)
    return proposition


def _appliquer_decision(
    proposition: EtudeProposition,
    decision: str,
    valeur_retenue: str | None,
    nature_correction: str | None,
    cause_erreur: str | None,
    justif_ouverte: bool,
    justif_duree_ms: int | None,
) -> None:
    """Ecrit la decision et sa telemetrie sur la ligne."""
    # LA metrique d'explicabilite : la justification a-t-elle change l'avis ?
    # Elle ne se mesure qu'au moment ou l'avis change, donc avant l'ecrasement.
    if (
        proposition.decision is not None
        and proposition.decision != decision
        and (justif_ouverte or proposition.justif_ouverte)
    ):
        proposition.decision_changee_apres_justif = True

    maintenant = _maintenant()
    proposition.decision = decision
    proposition.valeur_retenue = valeur_retenue
    proposition.nature_correction = nature_correction
    proposition.cause_erreur = cause_erreur
    proposition.decide_a = maintenant
    proposition.justif_ouverte = proposition.justif_ouverte or justif_ouverte
    if justif_duree_ms is not None:
        proposition.justif_duree_ms = (proposition.justif_duree_ms or 0) + justif_duree_ms

    if proposition.affiche_a is not None:
        affiche_a = _en_utc(proposition.affiche_a)
        latence = int((maintenant - affiche_a).total_seconds() * 1000)
        proposition.latence_ms = max(0, latence)
        proposition.hative = est_hative(proposition.latence_ms, proposition.longueur_mots)


async def _horodater_dossier(db: AsyncSession, proposition: EtudeProposition) -> None:
    """Met a jour t3 (premiere decision) et t4 (derniere) sur le dossier."""
    dossier = await db.get(EtudeDossier, proposition.dossier_id)
    if dossier is None:
        return
    if dossier.t3_premiere_decision is None:
        dossier.t3_premiere_decision = proposition.decide_a
    dossier.t4_derniere_decision = proposition.decide_a


# --- Pauses ----------------------------------------------------------------


async def enregistrer_pause(
    db: AsyncSession | None,
    dossier_id: str,
    debut: datetime,
    fin: datetime,
    cause: str,
) -> None:
    """Journalise une interruption du chronometre.

    Les pauses sont loguees, pas seulement soustraites : leur nombre et leur
    duree sont eux-memes un resultat sur la faisabilite en conditions reelles.
    """
    if db is None:
        return
    if cause not in CAUSES_PAUSE:
        raise EtudeRefus(f"Cause de pause inconnue : '{cause}'.")
    duree = _en_utc(fin) - _en_utc(debut)
    db.add(
        EtudePause(
            dossier_id=dossier_id,
            debut=debut,
            fin=fin,
            duree_ms=max(0, int(duree.total_seconds() * 1000)),
            cause=cause,
        )
    )
    await db.commit()


# --- Cloture ---------------------------------------------------------------


async def clore_dossier(
    db: AsyncSession | None,
    dossier_id: str,
    cr_valide: str,
    omission_signalee: bool | None = None,
    omission_texte: str | None = None,
    nb_prelevements_corrige: int | None = None,
) -> EtudeDossier | None:
    """Fige le compte rendu valide et calcule la charge d'edition."""
    if db is None:
        return None

    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        raise EtudeRefus("Dossier introuvable.")
    if dossier.abandonne:
        raise EtudeRefus("Dossier abandonne : il ne peut plus etre clos.")

    dossier.cr_valide = cr_valide
    dossier.caracteres_modifies = distance_edition(dossier.cr_propose, cr_valide)
    dossier.omission_signalee = omission_signalee
    dossier.omission_texte = omission_texte
    dossier.nb_prelevements_corrige = nb_prelevements_corrige
    dossier.t5_cloture = _maintenant()
    await db.commit()
    await db.refresh(dossier)
    return dossier


async def periodique_est_du(db: AsyncSession | None, praticien_id: str) -> bool:
    """Le releve periodique tombe-t-il apres ce dossier ?

    Le decompte est tenu ICI, pas par le client : un compteur local deriverait
    d'un poste a l'autre et la courbe ne serait plus alignee entre praticiens.
    """
    if db is None:
        return False
    resultat = await db.execute(
        select(func.count())
        .select_from(EtudeDossier)
        .join(EtudeSession, EtudeDossier.session_id == EtudeSession.id)
        .where(EtudeSession.praticien_id == praticien_id)
        .where(EtudeDossier.t5_cloture.is_not(None))
        .where(EtudeDossier.abandonne.is_(False))
        .where(EtudeDossier.exclu.is_(False))
    )
    return periodique_du(int(resultat.scalar_one()))


async def marquer_export(db: AsyncSession | None, dossier_id: str) -> None:
    """Horodate la sortie du compte rendu (t6)."""
    if db is None:
        return
    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        return
    dossier.t6_export = _maintenant()
    await db.commit()


async def abandonner_dossier(
    db: AsyncSession | None, dossier_id: str, motif: str
) -> None:
    """Enregistre un abandon motive.

    Sans porte de sortie, un praticien bloque valide par complaisance et
    l'etude est fausse tout en paraissant parfaite (cahier §4).
    """
    if db is None:
        return
    if motif not in MOTIFS_ABANDON:
        raise EtudeRefus(f"Motif d'abandon inconnu : '{motif}'.")
    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        raise EtudeRefus("Dossier introuvable.")
    dossier.abandonne = True
    dossier.motif_abandon = motif
    dossier.t5_cloture = _maintenant()
    await db.commit()


async def exclure_dossier(
    db: AsyncSession | None,
    dossier_id: str,
    motif: str,
    par: str,
    exclu: bool = True,
) -> EtudeDossier | None:
    """Ecarte un dossier de l'etude, sans le detruire.

    Un essai d'administrateur, une saisie aberrante, un cas ouvert par erreur :
    ils ne doivent compter dans aucun taux. Mais les EFFACER rendrait l'etude
    incapable de rendre compte de son propre effectif — le diagramme de flux
    d'une publication demande combien de cas ont ete ecartes et pourquoi.

    Reversible : on exclut un cas par erreur bien plus souvent qu'on ne veut le
    detruire.
    """
    if db is None:
        return None
    if exclu and not motif.strip():
        # Un motif vide rendrait l'exclusion inexplicable au depouillement, donc
        # inutilisable dans une publication.
        raise EtudeRefus("Une exclusion doit porter un motif.")

    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        raise EtudeRefus("Dossier introuvable.")

    dossier.exclu = exclu
    dossier.motif_exclusion = motif.strip() if exclu else None
    dossier.exclu_par = par if exclu else None
    await db.commit()
    await db.refresh(dossier)
    return dossier


async def supprimer_dossier(db: AsyncSession | None, dossier_id: str) -> bool:
    """Detruit un dossier et tout ce qui en depend. Sans retour.

    QUAND L'UTILISER, ET QUAND NE PAS L'UTILISER.

    Avant le debut de l'etude, les dossiers sont des ESSAIS : mises au point,
    demonstrations, praticiens qui decouvrent l'outil. Ils n'ont jamais fait
    partie de la population etudiee, il n'y a donc rien a justifier a leur sujet
    et les garder ne ferait que polluer la base. On supprime.

    Une fois l'etude commencee, c'est l'inverse : effacer un cas rendrait
    l'etude incapable de rendre compte de son propre effectif, et toute
    publication demande combien de cas ont ete ecartes et pourquoi. On EXCLUT —
    voir `exclure_dossier`, qui conserve et se defait.

    La suppression emporte propositions, prelevements, pauses et questions par
    cascade. Les reponses de questionnaire attachees au dossier partent aussi ;
    celles qui portent sur le praticien, comme le releve periodique, survivent :
    elles ne dependent d'aucun cas.
    """
    if db is None:
        return False
    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        return False

    # Les reponses de questionnaire sont effacees EXPLICITEMENT : elles n'ont
    # pas de relation ORM vers le dossier, et SQLite n'applique pas les
    # cascades declarees en base sauf a activer les cles etrangeres. Sans cette
    # ligne, elles survivaient a leur dossier — verifie par un test, pas
    # suppose. Une reponse orpheline gonfle un denominateur sans qu'aucun cas ne
    # lui corresponde.
    #
    # `dossier_id` non nul seulement : le releve periodique porte sur le
    # PRATICIEN et doit survivre a la suppression d'un cas.
    await db.execute(
        delete(EtudeReponseQuestionnaire).where(
            EtudeReponseQuestionnaire.dossier_id == dossier_id
        )
    )
    await db.delete(dossier)
    await db.commit()
    return True


def distance_edition(propose: str, valide: str) -> int:
    """Nombre de caracteres modifies entre le texte propose et le texte valide.

    Mesure la charge d'edition reelle, la seule qui compte pour le praticien :
    un compte rendu accepte tel quel donne zero.
    """
    matcher = SequenceMatcher(None, propose, valide, autojunk=False)
    return sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )


# --- Questionnaires --------------------------------------------------------


async def enregistrer_reponses(
    db: AsyncSession | None,
    praticien_id: str,
    questionnaire: str,
    reponses: dict[str, str],
    dossier_id: str | None = None,
) -> int:
    """Enregistre les items d'un questionnaire, un par ligne.

    Une ligne par item plutot qu'un blob : le depouillement se fait sans parser
    et un item peut etre retire en cours de rodage sans migration.
    """
    if db is None:
        return 0
    if questionnaire not in QUESTIONNAIRES:
        raise EtudeRefus(f"Questionnaire inconnu : '{questionnaire}'.")
    for item, valeur in reponses.items():
        db.add(
            EtudeReponseQuestionnaire(
                praticien_id=praticien_id,
                dossier_id=dossier_id,
                questionnaire=questionnaire,
                item=item,
                valeur=valeur,
            )
        )
    await db.commit()
    return len(reponses)
