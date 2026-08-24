"""Tables de l'instrumentation de l'etude.

Le modele suit la hierarchie de la specification :

    Session  ->  Dossier (compte rendu)  ->  Prelevement  ->  Proposition

Les noms de champs reprennent ceux du schema d'evenement (cahier §8) pour que
l'export d'analyse se fasse sans table de correspondance.

Aucune donnee identifiante patient n'est stockee : l'entree est une dictee sans
identifiant, et l'audio n'est jamais conserve (decision actee, cahier §1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db_models import Base
from etude.vocabulaire import ETAT_NON_VU


def _uuid_str() -> str:
    return str(uuid.uuid4())


class EtudeSession(Base):
    """Une session de travail d'un praticien : plusieurs cas d'affilee.

    Sert a mesurer l'effet d'apprentissage (ordre des cas) et la faisabilite en
    conditions reelles (duree, nombre de cas).
    """

    __tablename__ = "etude_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    praticien_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    debut: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Renseigne a la cloture ; evite un COUNT a chaque lecture.
    nb_cas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dossiers: Mapped[list["EtudeDossier"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_etude_sessions_praticien", "praticien_id"),)


class EtudeDossier(Base):
    """Un compte rendu instrumente, de la dictee a l'export.

    Porte les sept horodatages de la mesure du temps (cahier §5). Le transcript
    et les DEUX versions du compte rendu sont conserves : sans le texte propose
    a cote du texte valide, la charge d'edition n'est pas calculable.
    """

    __tablename__ = "etude_dossiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_sessions.id", ondelete="CASCADE"), nullable=False
    )
    #: Rang du cas dans la session : sert a l'analyse par tercile (effet d'apprentissage).
    index_session: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    transcription: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Ce que le systeme a propose, fige a l'affichage. Ne doit jamais etre ecrase.
    cr_propose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Ce que le praticien a valide. Rempli a l'export.
    cr_valide: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Les sept horodatages (cahier §5) --------------------------------
    t0_debut_dictee: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    t1_fin_dictee: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    t2_affichage: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    t3_premiere_decision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    t4_derniere_decision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    t5_cloture: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    t6_export: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Segmentation (le bug le plus signale du terrain) ----------------
    nb_prelevements_detecte: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nb_prelevements_corrige: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # -- Cloture (cahier §3.4 : la mesure d'omission) --------------------
    omission_signalee: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    omission_texte: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Ce que le praticien dit du compte rendu au moment de le valider, en
    #: texte libre.
    #:
    #: C'est souvent la SEULE trace de ce qui l'a gene sans qu'aucune case ne
    #: le capture : une case cochee dit qu'il y a eu un probleme, elle ne dit
    #: jamais lequel. Nul quand rien n'a ete ecrit — une chaine vide et une
    #: absence de commentaire se compteraient pareil, et le nombre de cas
    #: commentes serait faux.
    commentaire_validation: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Nombre de blocs JAMAIS AFFICHES a l'ecran au moment de la cloture.
    #:
    #: Un compte rendu valide dont la moitie des blocs n'a jamais ete affichee
    #: ne se lit pas comme un compte rendu entierement revu. Sans ce compte, la
    #: validation du dossier laisserait croire a une revue complete.
    #:
    #: NUL tant que le dossier n'est pas clos : c'est une absence de mesure et
    #: non un zero. Ecrire 0 avant la cloture ferait passer tout dossier en
    #: cours pour un dossier integralement parcouru.
    nb_blocs_non_vus: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # -- Abandon (cahier §4, garde-fou n°1) ------------------------------
    abandonne: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motif_abandon: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # -- Exclusion (essais, saisies aberrantes) ---------------------------
    #
    # On EXCLUT, on ne supprime pas. Une etude qui efface des cas ne peut plus
    # rendre compte de son propre effectif : le diagramme de flux exige de dire
    # combien de cas ont ete ecartes et pourquoi. Un cas exclu reste en base,
    # n'entre dans AUCUN taux, et son motif est publiable.
    #
    # L'exclusion est REVERSIBLE : on retire un cas d'essai par erreur bien plus
    # souvent qu'on ne veut le detruire.
    exclu: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motif_exclusion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    exclu_par: Mapped[str | None] = mapped_column(String(36), nullable=True)

    #: Caracteres modifies entre cr_propose et cr_valide, calcule a l'export.
    caracteres_modifies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    organe: Mapped[str | None] = mapped_column(String(80), nullable=True)

    cree_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[EtudeSession] = relationship(back_populates="dossiers")
    prelevements: Mapped[list["EtudePrelevement"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    propositions: Mapped[list["EtudeProposition"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    questions: Mapped[list["EtudeQuestion"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    pauses: Mapped[list["EtudePause"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_etude_dossiers_session", "session_id"),)


class EtudePrelevement(Base):
    """Un prelevement du dossier. Porte ses propres codes ADICAP.

    L'existence de cette table EST la correction du bug de cardinalite : un
    dossier a n prelevements, chacun avec un code primaire et n codes
    secondaires (spec maitresse §4).
    """

    __tablename__ = "etude_prelevements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    dossier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_dossiers.id", ondelete="CASCADE"), nullable=False
    )
    #: 1, 2, 3... tel qu'affiche au praticien.
    rang: Mapped[int] = mapped_column(Integer, nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    #: Codes ADICAP de ce prelevement : [{"code","role","positions"}].
    #: role = "primaire" | "secondaire".
    codes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dossier: Mapped[EtudeDossier] = relationship(back_populates="prelevements")
    propositions: Mapped[list["EtudeProposition"]] = relationship(
        back_populates="prelevement"
    )

    __table_args__ = (Index("ix_etude_prelevements_dossier", "dossier_id"),)


class EtudeProposition(Base):
    """L'unite d'analyse de l'etude.

    Regle fondatrice (cahier §2) : ce qui est une copie litterale du verbatim
    n'est pas une proposition, c'est une transcription. SEULE L'INFERENCE SE
    VALIDE. Cible : 8 a 15 propositions par compte rendu ; au-dela de 20, le
    praticien clique sans lire et la mesure se detruit elle-meme.

    Regle d'ancrage (00_INDEX) : pas d'empan, pas de proposition. Une
    proposition sans empan verifie dans le transcript est rejetee avant
    affichage, jamais ecrite ici.
    """

    __tablename__ = "etude_propositions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    dossier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_dossiers.id", ondelete="CASCADE"), nullable=False
    )
    prelevement_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("etude_prelevements.id", ondelete="SET NULL"), nullable=True
    )

    # -- Nature -----------------------------------------------------------
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    sous_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    valeur_proposee: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Descente dans le referentiel : ["D5", "A tumeur adenomateuse", ...].
    chemin: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Positions ADICAP concernees, pour une proposition de code : [5,6,7,8].
    positions: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confiance: Mapped[float | None] = mapped_column(Float, nullable=True)

    # -- Ancrage (le survol qui surligne) --------------------------------
    empan_debut: Mapped[int | None] = mapped_column(Integer, nullable=True)
    empan_fin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    longueur_mots: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: Regles deterministes evaluees : [{"id","resultat"}].
    regles_evaluees: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Les chiffres de l'assertion absents de la dictee, separes par " | ".
    #: Vide quand il n'y en a pas ; NULL sur les lignes anterieures a la
    #: mesure, qu'on ne peut pas declarer indemnes retroactivement.
    #:
    #: SIGNAL DISTINCT DE L'ANCRAGE, et il le fallait. L'ancrage se fait sur
    #: les mots — ancrer sur les chiffres faisait qu'un "5 %" s'appuyait sur un
    #: "5 mm" dicte plus loin. Mais une phrase dont tous les mots sont dictes
    #: passait alors pour soutenue avec un chiffre invente. Vu sur un cas reel :
    #: dictee de 5 + 2 + 3 ganglions, compte rendu "0/22 ganglions examines",
    #: tous les mots ancres, et c'est le 22 qui dit si le curage est adequat.
    chiffres_non_dictes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Telemetrie de decision (cahier §7) ------------------------------
    #: Moment ou le serveur a REMIS le bloc au client : t2 du dossier. Il dit
    #: que la proposition etait dans la page, pas qu'elle a ete vue.
    affiche_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: PREMIER affichage reel du bloc a l'ecran, signale par le client.
    #:
    #: C'est ce champ, et lui seul, qui separe non_vu de vu_non_decide. C'est
    #: aussi lui qui rend la latence interpretable : une latence comptee depuis
    #: un affichage qui n'a jamais eu lieu ne mesure rien. Le PREMIER affichage
    #: date la mesure et ne se reecrit jamais — un second passage devant le
    #: bloc raccourcirait artificiellement le temps de lecture.
    vu_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decide_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Delai depuis `affiche_a`, donc depuis la remise du CR entier.
    latence_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Delai depuis `vu_a` : le temps de lecture REEL du bloc. Nul quand aucun
    #: affichage n'a ete signale — on ne fabrique pas une duree de lecture a
    #: partir d'un affichage qu'on n'a pas observe.
    latence_vue_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    justif_ouverte: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    justif_duree_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: LA metrique d'explicabilite : la justification a-t-elle change la decision ?
    decision_changee_apres_justif: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # -- Decision ---------------------------------------------------------
    #: OU EN EST CE BLOC, sur un axe commun aux trois grilles : non_vu,
    #: vu_non_decide, accepte, corrige, refuse, abstenu, abandonne.
    #:
    #: Sans lui, un bloc que le praticien n'a pas touche etait compte comme
    #: accepte — une inference, pas une mesure, et un bloc jamais affiche
    #: gonflait le taux d'acceptation.
    #:
    #: NULLABLE, et c'est delibere : les lignes ecrites AVANT l'ajout de cette
    #: colonne n'ont pas d'etat observe. Leur donner "non_vu" par defaut
    #: declarerait jamais-vues des propositions qui portent une decision. Un
    #: etat nul se lit "non instrumente a l'epoque", jamais "non vu". Toute
    #: ligne creee depuis prend `non_vu` a l'insertion.
    etat: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=ETAT_NON_VU
    )
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    valeur_retenue: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: LA distinction que "corrige" seul ne porte pas : le systeme s'est-il
    #: trompe (erreur_fond), ou le praticien ecrit-il autrement (style,
    #: precision) ? Sans elle, une reformulation de confort et une erreur
    #: clinique comptent pareil, et le taux publie ne veut rien dire.
    nature_correction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cause_erreur: Mapped[str | None] = mapped_column(String(20), nullable=True)

    dossier: Mapped[EtudeDossier] = relationship(back_populates="propositions")
    prelevement: Mapped[EtudePrelevement | None] = relationship(
        back_populates="propositions"
    )
    #: Le journal des decisions, du plus ancien au plus recent. Charge d'office :
    #: sans lui, relire l'historique declencherait une requete par proposition.
    revisions: Mapped[list["EtudeRevisionDecision"]] = relationship(
        back_populates="proposition",
        cascade="all, delete-orphan",
        order_by="EtudeRevisionDecision.rang",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_etude_propositions_dossier", "dossier_id"),
        Index("ix_etude_propositions_type", "type"),
    )


class EtudeQuestion(Base):
    """Une question de levee de doute posee au praticien.

    Budget de 3 par compte rendu (Politique_de_questions §5). Le champ
    `propositions_evitees` mesure ce que la question a fait gagner en aval :
    c'est lui qui justifiera de la garder ou de la supprimer.
    """

    __tablename__ = "etude_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    dossier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_dossiers.id", ondelete="CASCADE"), nullable=False
    )
    #: Identifiant stable de la question pre-redigee, ex "d1_exerese_i_o".
    question_id: Mapped[str] = mapped_column(String(60), nullable=False)
    source_doute: Mapped[str] = mapped_column(String(20), nullable=False)

    #: Empan qui a declenche la question. Une question sans declencheur
    #: affichable ne se pose pas (Politique §5).
    empan_debut: Mapped[int | None] = mapped_column(Integer, nullable=True)
    empan_fin: Mapped[int | None] = mapped_column(Integer, nullable=True)

    options: Mapped[str | None] = mapped_column(Text, nullable=True)
    affichee_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repondue_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latence_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reponse: Mapped[str | None] = mapped_column(String(60), nullable=True)
    propositions_evitees: Mapped[int | None] = mapped_column(Integer, nullable=True)

    dossier: Mapped[EtudeDossier] = relationship(back_populates="questions")

    __table_args__ = (Index("ix_etude_questions_dossier", "dossier_id"),)


class EtudePause(Base):
    """Une interruption neutralisee du chronometre.

    Les pauses sont loguees SEPAREMENT, pas seulement soustraites : leur nombre
    et leur duree sont eux-memes un resultat sur la faisabilite en conditions
    reelles (cahier §5).
    """

    __tablename__ = "etude_pauses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    dossier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_dossiers.id", ondelete="CASCADE"), nullable=False
    )
    debut: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duree_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause: Mapped[str] = mapped_column(String(20), nullable=False)

    dossier: Mapped[EtudeDossier] = relationship(back_populates="pauses")

    __table_args__ = (Index("ix_etude_pauses_dossier", "dossier_id"),)


class EtudeErgonomie(Base):
    """Un instantane d'usage d'une zone de l'ecran, agrege par le client.

    Mesurer l'ergonomie reelle sans traceur tiers : le produit se vend sur la
    souverainete des donnees, brancher un service etranger sur un outil medical
    annulerait l'argument. Tout reste donc ici.

    UNE LIGNE = UN INSTANTANE CUMULE, PAS UN INCREMENT. Le client envoie a
    intervalles reguliers l'etat COURANT de ses compteurs depuis l'ouverture du
    dossier ; le depouillement ne retient que le dernier instantane de chaque
    couple (dossier, zone). Deux consequences, et c'est tout l'interet :
    un lot perdu ne coute que du detail, jamais un total, et un envoi rejoue ne
    compte rien deux fois. Sommer ces lignes, en revanche, compterait les memes
    secondes autant de fois qu'il y a eu d'envois.

    Ce qui n'est PAS ici : le contenu saisi, la position du curseur, les
    frappes. On mesure des comportements d'usage, pas ce que le praticien ecrit.
    """

    __tablename__ = "etude_ergonomie"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    dossier_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_dossiers.id", ondelete="CASCADE"), nullable=False
    )
    #: Nom de zone du vocabulaire de etude/ergonomie.py, jamais un selecteur CSS.
    zone: Mapped[str] = mapped_column(String(20), nullable=False)

    #: Temps cumule avec la zone a l'ecran, onglet au premier plan. Un onglet
    #: masque ne compte pas : ce serait mesurer la pause cafe.
    visible_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clics: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Part du contenu atteinte en defilant, entre 0 et 1. NULLE quand la zone
    #: tient dans l'ecran : il n'y a alors pas de profondeur a mesurer, et
    #: ecrire 100 % confondrait "il a tout parcouru" et "il n'y avait rien a
    #: parcourir".
    profondeur_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: 1 pour la zone ou le praticien a agi en premier, 2 pour la suivante...
    #: Nul tant qu'aucun geste n'y a eu lieu — par ou l'on commence ne se
    #: devine pas d'un panneau simplement visible, l'ecran en montre deux.
    rang_premiere_visite: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: Part de la largeur du plan de travail donnee a la zone. Le partage choisi
    #: a la glissiere est une mesure d'ergonomie a lui seul.
    part_largeur: Mapped[float | None] = mapped_column(Float, nullable=True)

    releve_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_etude_ergonomie_dossier", "dossier_id"),)


class EtudeReponseQuestionnaire(Base):
    """Une reponse a un item de questionnaire.

    Un enregistrement par item plutot qu'un blob : permet de depouiller sans
    parser, et de retirer un item en cours de rodage sans migration.
    """

    __tablename__ = "etude_reponses_questionnaire"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    praticien_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: Renseigne pour le questionnaire par cas ; nul pour inclusion et fin d'etude.
    dossier_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("etude_dossiers.id", ondelete="CASCADE"), nullable=True
    )
    questionnaire: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Identifiant stable de l'item, ex "sus_03", "par_cas_04", "inclusion_09".
    item: Mapped[str] = mapped_column(String(40), nullable=False)
    valeur: Mapped[str] = mapped_column(Text, nullable=False, default="")
    repondu_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_etude_reponses_praticien", "praticien_id"),
        Index("ix_etude_reponses_questionnaire", "questionnaire"),
    )


class EtudeRevisionDecision(Base):
    """Toute decision jamais prise sur un bloc, dans l'ordre, sans ecrasement.

    DANS UNE ETUDE, ON N'ECRASE PAS UNE MESURE. `EtudeProposition` porte l'etat
    COURANT du bloc — c'est ce qu'il faut pour afficher et pour tous les taux.
    Mais chaque nouvelle decision y remplacait la precedente, et la precedente
    disparaissait : au depouillement, un clic errant corrige dans la seconde et
    un vrai changement d'avis apres avoir ouvert la justification etaient
    devenus la meme ligne.

    La difference n'est pas cosmetique. Elle porte le critere d'explicabilite :
    "la justification a-t-elle change l'avis ?" ne se demontre qu'en montrant
    l'avis d'avant, celui d'apres, et le temps passe entre les deux. Avec un
    seul champ ecrase, ce critere reposait sur un booleen que rien ne permettait
    de rejouer. Ici, il se recalcule depuis les lignes.

    Cette table s'ecrit et ne se modifie JAMAIS. Aucun taux n'en depend : elle
    sert la relecture, la reversibilite et la defense de l'etude. Une ligne de
    plus ne peut donc pas fausser un resultat, alors qu'une ligne perdue, si.
    """

    __tablename__ = "etude_revisions_decision"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    proposition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("etude_propositions.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: 1 pour la premiere decision, 2 pour la suivante. Le rang le plus eleve
    #: correspond a ce que porte `EtudeProposition` : c'est la verification que
    #: le journal et l'etat courant ne divergent pas.
    rang: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    etat: Mapped[str] = mapped_column(String(20), nullable=False)
    valeur_retenue: Mapped[str | None] = mapped_column(Text, nullable=True)
    nature_correction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cause_erreur: Mapped[str | None] = mapped_column(String(20), nullable=True)

    #: La justification etait-elle ouverte AU MOMENT de cette decision-la ?
    #: Sur la proposition, le champ est cumulatif ; ici il date l'evenement.
    justif_ouverte: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    latence_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decide_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    proposition: Mapped[EtudeProposition] = relationship(back_populates="revisions")

    __table_args__ = (
        Index("ix_etude_revisions_proposition", "proposition_id"),
    )
