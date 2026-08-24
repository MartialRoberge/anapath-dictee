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

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from etude.extraction import PropositionExtraite
from etude.models import (
    EtudeDossier,
    EtudePause,
    EtudePrelevement,
    EtudeProposition,
    EtudeRevisionDecision,
    EtudeReponseQuestionnaire,
    EtudeSession,
)
from etude.vocabulaire import (
    CAUSES_ERREUR,
    CAUSES_PAUSE,
    ETAT_ABANDONNE,
    ETAT_NON_VU,
    ETAT_VU_NON_DECIDE,
    MOTIFS_ABANDON,
    NATURES_CORRECTION,
    QUESTIONNAIRES,
    decision_valide,
    est_hative,
    etat_de_la_decision,
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
    """Convertit une proposition extraite en ligne de base.

    Le bloc nait NON VU, jamais "en attente d'acceptation" : tant que rien ne
    prouve qu'il a ete affiche a l'ecran, l'etude n'a rien mesure sur lui.
    """
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
        etat=ETAT_NON_VU,
        # Chaine vide = verifie, aucun chiffre suspect. NULL serait "non
        # mesure", ce qui n'est vrai que des lignes d'avant la colonne.
        chiffres_non_dictes=" | ".join(extraite.chiffres_non_dictes),
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


# --- Affichage reel a l'ecran ----------------------------------------------
#
# Ce que le serveur sait sans cette etape : qu'il a REMIS les blocs au client.
# Ce qu'il ne sait pas : lequel a ete affiche. Un compte rendu qui defile sur
# trois ecrans peut se clore sans que la moitie des blocs ait paru, et ces
# blocs-la ne sont ni acceptes ni refuses — ils ne sont pas mesures.


def _appliquer_vue(proposition: EtudeProposition, moment: datetime) -> bool:
    """Date le premier affichage du bloc. Vrai si c'etait bien le premier.

    IDEMPOTENT, et c'est l'invariant de cette fonction : un second signalement
    ne reecrit ni la date ni l'etat. C'est le PREMIER affichage qui date la
    mesure. Le reecrire raccourcirait le temps de lecture de tout bloc regarde
    deux fois, et le praticien qui revient sur un bloc pour le relire
    paraitrait plus expeditif que celui qui l'a tranche du premier coup.
    """
    if proposition.vu_a is not None:
        return False
    proposition.vu_a = moment
    # L'etat ne bouge que si rien n'a encore ete tranche. Un bloc deja decide
    # garde sa decision, et un bloc deja marque abandonne reste abandonne : un
    # signal d'affichage arrive en retard ne doit pas defaire une mesure.
    if proposition.decision is None and proposition.etat != ETAT_ABANDONNE:
        proposition.etat = ETAT_VU_NON_DECIDE
    return True


async def marquer_vue(
    db: AsyncSession | None, proposition_id: str
) -> EtudeProposition | None:
    """Signale qu'un bloc a ete affiche a l'ecran du praticien.

    L'horodatage est pris cote SERVEUR, comme les latences : un moment fourni
    par le client pourrait etre recule pour allonger un temps de lecture, et
    c'est precisement ce temps que l'etude publie.
    """
    if db is None:
        return None
    proposition = await db.get(EtudeProposition, proposition_id)
    if proposition is None:
        raise EtudeRefus("Proposition introuvable.")
    _appliquer_vue(proposition, _maintenant())
    await db.commit()
    await db.refresh(proposition)
    return proposition


async def marquer_vues(
    db: AsyncSession | None, dossier_id: str, proposition_ids: list[str]
) -> tuple[int, int]:
    """Signale l'affichage de plusieurs blocs d'un coup.

    Renvoie (blocs nouvellement dates, identifiants ignores).

    Un envoi groupe plutot qu'un appel par bloc : un observateur de defilement
    voit entrer plusieurs blocs a la fois, et une route par bloc ferait perdre
    des signaux au premier ralentissement du reseau — c'est-a-dire des blocs
    comptes non vus alors qu'ils l'ont ete.

    Les identifiants qui n'appartiennent pas au dossier sont COMPTES et non
    ecrits : les refuser en bloc ferait perdre les signaux valides du meme
    envoi, les ignorer en silence cacherait un defaut du client.

    Tous les blocs d'un envoi prennent le MEME horodatage : c'est le moment ou
    le client a signale, et l'etude n'observe rien de plus fin.
    """
    if db is None or not proposition_ids:
        return 0, 0
    attendus = set(proposition_ids)
    resultat = await db.execute(
        select(EtudeProposition)
        .where(EtudeProposition.dossier_id == dossier_id)
        .where(EtudeProposition.id.in_(attendus))
    )
    trouvees = list(resultat.scalars().all())
    moment = _maintenant()
    marquees = sum(1 for proposition in trouvees if _appliquer_vue(proposition, moment))
    await db.commit()
    return marquees, len(attendus) - len(trouvees)


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

    # La grille a deja accepte la decision : si la correspondance manque, c'est
    # qu'une decision a ete ajoutee sans lui donner d'etat. On refuse plutot
    # que d'ecrire un bloc decide qui resterait indistinguable d'un bloc
    # jamais vu au depouillement.
    etat = etat_de_la_decision(proposition.type, decision)
    if etat is None:
        raise EtudeRefus(
            f"Aucun etat ne correspond a la decision '{decision}' "
            f"du type '{proposition.type}'."
        )

    _appliquer_decision(
        proposition, decision, etat, valeur_retenue, nature_correction, cause_erreur,
        justif_ouverte, justif_duree_ms,
    )
    await _horodater_dossier(db, proposition)
    await db.commit()
    await db.refresh(proposition)
    return proposition


def _appliquer_decision(
    proposition: EtudeProposition,
    decision: str,
    etat: str,
    valeur_retenue: str | None,
    nature_correction: str | None,
    cause_erreur: str | None,
    justif_ouverte: bool,
    justif_duree_ms: int | None,
) -> None:
    """Ecrit la decision, son etat et sa telemetrie sur la ligne."""
    # LA metrique d'explicabilite : la justification a-t-elle change l'avis ?
    # Elle ne se mesure qu'au moment ou l'avis change, donc avant l'ecrasement.
    if (
        proposition.decision is not None
        and proposition.decision != decision
        and (justif_ouverte or proposition.justif_ouverte)
    ):
        proposition.decision_changee_apres_justif = True

    maintenant = _maintenant()
    # LE JOURNAL AVANT L'ECRASEMENT. La ligne courante va etre remplacee ;
    # celle-ci reste. C'est ce qui separe, au depouillement, un clic errant
    # rattrape dans la seconde d'un changement d'avis apres lecture de la
    # justification — deux gestes que l'etat courant seul rend identiques.
    proposition.revisions.append(
        EtudeRevisionDecision(
            rang=len(proposition.revisions) + 1,
            decision=decision,
            etat=etat,
            valeur_retenue=valeur_retenue,
            nature_correction=nature_correction,
            cause_erreur=cause_erreur,
            justif_ouverte=justif_ouverte,
            decide_a=maintenant,
        )
    )
    proposition.decision = decision
    # Une decision explicite ecrase toujours l'etat de parcours : elle prouve
    # a elle seule que le bloc etait sous les yeux du praticien.
    proposition.etat = etat
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

    # Le temps de lecture REEL, compte depuis l'affichage du bloc et non depuis
    # la remise du compte rendu entier. Il reste NUL quand aucun affichage n'a
    # ete signale : dater le debut de la lecture au moment de la decision
    # donnerait zero milliseconde a tout bloc decide sans signal, et ferait
    # passer pour expeditif un praticien qu'on n'a simplement pas observe.
    if proposition.vu_a is not None:
        vue = _en_utc(proposition.vu_a)
        proposition.latence_vue_ms = max(
            0, int((maintenant - vue).total_seconds() * 1000)
        )


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
    commentaire_validation: str | None = None,
) -> EtudeDossier | None:
    """Fige le compte rendu valide, son commentaire et la charge d'edition.

    Le nombre de blocs jamais affiches est fige ICI, au moment ou le praticien
    valide : un compte rendu valide dont la moitie des blocs n'a jamais paru a
    l'ecran ne se lit pas comme un compte rendu entierement revu, et le compte
    ne serait plus reconstituable si un signal d'affichage tardif arrivait
    apres la cloture.
    """
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
    dossier.commentaire_validation = _commentaire(commentaire_validation)
    dossier.nb_blocs_non_vus = await _compter_non_vus(db, dossier_id)
    dossier.t5_cloture = _maintenant()
    await db.commit()
    await db.refresh(dossier)
    return dossier


def _commentaire(texte: str | None) -> str | None:
    """Le commentaire de validation, ou None quand rien n'a ete ecrit.

    Une chaine vide et une absence de commentaire se lisent pareil mais se
    COMPTENT differemment : sans cette normalisation, le nombre de cas
    commentes compterait chaque champ laisse vide, et le seul indicateur
    qualitatif de l'etude serait faux vers le haut.
    """
    if texte is None:
        return None
    return texte.strip() or None


async def _compter_non_vus(db: AsyncSession, dossier_id: str) -> int:
    """Blocs de ce dossier jamais affiches a l'ecran.

    Compte sur l'ETAT et non sur `vu_a` : une decision explicite prouve que le
    bloc etait a l'ecran, meme quand aucun signal d'affichage n'est arrive. Le
    compter non vu contredirait la decision qu'il porte.

    Un etat NUL — ligne anterieure a l'instrumentation — n'est pas compte : on
    ne sait pas s'il a ete vu, et une absence de mesure n'est pas un non-vu.
    """
    resultat = await db.execute(
        select(func.count())
        .select_from(EtudeProposition)
        .where(EtudeProposition.dossier_id == dossier_id)
        .where(EtudeProposition.etat == ETAT_NON_VU)
    )
    return int(resultat.scalar_one())


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
    await _marquer_blocs_abandonnes(db, dossier_id)
    dossier.nb_blocs_non_vus = await _compter_non_vus(db, dossier_id)
    await db.commit()


async def _marquer_blocs_abandonnes(db: AsyncSession, dossier_id: str) -> None:
    """Passe a `abandonne` les blocs vus et laisses sans decision.

    SEULEMENT ceux-la, et les deux exclusions comptent autant que la regle.

    Un bloc jamais affiche reste NON VU : on ne peut pas dire d'un praticien
    qu'il a quitte un bloc qu'il n'a jamais eu sous les yeux. L'ecraser
    detruirait en plus le compte des blocs non vus, c'est-a-dire justement ce
    qui distingue un cas survole d'un cas interrompu.

    Un bloc deja tranche garde sa decision : l'abandon survient apres, il ne
    l'annule pas.
    """
    await db.execute(
        update(EtudeProposition)
        .where(EtudeProposition.dossier_id == dossier_id)
        .where(EtudeProposition.etat == ETAT_VU_NON_DECIDE)
        .values(etat=ETAT_ABANDONNE)
    )


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
