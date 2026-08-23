/**
 * Client de l'instrumentation de l'etude (prefixes /etude et /admin/etude).
 *
 * Un fichier a part, comme le routeur backend : le jour ou l'etude s'arrete,
 * ce client se retire sans toucher au moteur de redaction.
 *
 * Les types sont le MIROIR EXACT du backend, champs `snake_case` compris. Un
 * renommage de confort cote frontend ferait diverger silencieusement les deux
 * cotes le jour ou le backend evolue ; ici, la compilation le signale.
 *
 * Aucun etat : ces fonctions ne font qu'emettre une requete et rendre sa
 * reponse. L'etat de l'etude vit dans les hooks (useEtudeDossier, useHorlogeEtude).
 */

import { API_BASE } from "@/lib/config";
import { getAuthHeaders, jsonHeaders } from "@/services/api";

/* ------------------------------------------------------------------ */
/*  Erreur transportant le code HTTP                                   */
/* ------------------------------------------------------------------ */

/**
 * Le statut est conserve parce qu'il porte du sens metier : le questionnaire
 * de fin d'etude repond 409 tant que les libelles F-SUS publies ne sont pas en
 * place. C'est un refus attendu, a distinguer d'une panne.
 */
export class ErreurEtude extends Error {
  readonly statut: number;

  constructor(statut: number, message: string) {
    super(message);
    this.name = "ErreurEtude";
    this.statut = statut;
  }
}

/** Vrai quand le questionnaire demande existe mais n'est pas encore servable. */
export function estQuestionnaireIndisponible(erreur: unknown): boolean {
  return erreur instanceof ErreurEtude && erreur.statut === 409;
}

/* ------------------------------------------------------------------ */
/*  Vocabulaire ferme — miroir de backend/etude/vocabulaire.py         */
/* ------------------------------------------------------------------ */

export type TypeProposition = "restitution" | "code" | "completude";

/**
 * TROIS GRILLES DISTINCTES, jamais melangees : le backend refuse en 400 une
 * decision hors grille, et les confondre fausserait un taux publie.
 */
export type DecisionRestitution =
  | "conforme"
  | "corrige"
  | "non_dicte"
  | "hors_sujet";
export type DecisionCode = "juste" | "corrige" | "je_ne_sais_pas";
export type DecisionCompletude =
  | "pertinent_ajoute"
  | "pertinent_non_retenu"
  | "non_pertinent";

export type Decision = DecisionRestitution | DecisionCode | DecisionCompletude;

/** Relie un type de proposition a sa grille, au niveau des types. */
export type DecisionPourType<T extends TypeProposition> = T extends "restitution"
  ? DecisionRestitution
  : T extends "code"
    ? DecisionCode
    : DecisionCompletude;

/**
 * Les grilles a l'execution, pour construire les boutons d'un panneau sans
 * recopier la liste — une liste recopiee derive au premier remaniement.
 */
export const GRILLES: {
  readonly [T in TypeProposition]: readonly DecisionPourType<T>[];
} = {
  restitution: ["conforme", "corrige", "non_dicte", "hors_sujet"],
  code: ["juste", "corrige", "je_ne_sais_pas"],
  completude: ["pertinent_ajoute", "pertinent_non_retenu", "non_pertinent"],
};

/**
 * La grille d'un type, elargie a `Decision`.
 *
 * `GRILLES[type]` sur un type non litteral rend l'union des trois tableaux, sur
 * laquelle `includes` ne se type pas. Cette lecture rend la verification d'une
 * decision possible sans conversion forcee.
 */
export function grilleDe(type: TypeProposition): readonly Decision[] {
  return GRILLES[type];
}

/** Libelles montres au praticien. Le mot exact fait partie du protocole. */
export const LIBELLES_DECISION: Record<Decision, string> = {
  conforme: "Conforme",
  corrige: "À corriger",
  non_dicte: "Je n'ai pas dit ça",
  hors_sujet: "Hors sujet",
  juste: "Code juste",
  je_ne_sais_pas: "Je ne sais pas",
  pertinent_ajoute: "Pertinent, je l'ajoute",
  pertinent_non_retenu: "Pertinent, mais je ne le mets pas",
  non_pertinent: "Pas pertinent ici",
};

/** Separe les deux mecanismes d'erreur (question facultative sur ✎ et ✗). */
export type CauseErreur = "transcription" | "interpretation";

export const LIBELLES_CAUSE_ERREUR: Record<CauseErreur, string> = {
  transcription: "La transcription a mal compris un mot",
  interpretation: "La transcription était juste, l'interprétation est fausse",
};

/** La porte de sortie du praticien : sans elle, on obtient des validations
 *  de complaisance et l'etude est fausse tout en paraissant parfaite. */
export type MotifAbandon =
  | "outil_trop_lent"
  | "propositions_inexploitables"
  | "interruption"
  | "cas_trop_complexe"
  | "autre";

export const LIBELLES_MOTIF_ABANDON: Record<MotifAbandon, string> = {
  outil_trop_lent: "L'outil est trop lent",
  propositions_inexploitables: "Les propositions sont inexploitables",
  interruption: "J'ai été interrompu",
  cas_trop_complexe: "Le cas est trop complexe",
  autre: "Autre raison",
};

export type CausePause = "onglet_masque" | "inactivite";

export type NomQuestionnaire = "inclusion" | "par_cas" | "fin_etude";

export type TypeItem =
  | "likert_5"
  | "echelle_10"
  | "choix_unique"
  | "choix_multiple"
  | "texte_libre"
  | "nombre"
  | "oui_non"
  | "classement";

/* ------------------------------------------------------------------ */
/*  Types d'echange — miroir de backend/routes_etude.py                */
/* ------------------------------------------------------------------ */

/** Un code ADICAP soumis a validation, ancre sur le terme qui l'a declenche. */
export interface CodeEtude {
  code: string;
  libelle?: string;
  /** Terme de la dictee qui a declenche le code ; a defaut, le libelle. */
  declencheur?: string;
  position?: string;
  confiance?: number;
}

/** Un champ signale manquant, qui deviendra une proposition de completude. */
export interface AlerteEtude {
  champ: string;
  description?: string;
  section?: string;
}

export interface PrelevementEtude {
  libelle: string;
  codes: string[];
}

export interface OuvertureDossier {
  session_id: string;
  transcription: string;
  cr_propose: string;
  organe?: string | null;
  /** ISO 8601. Sert a mesurer la duree de dictee, hors temps de generation. */
  t0_debut_dictee?: string | null;
  t1_fin_dictee?: string | null;
  codes?: CodeEtude[];
  alertes?: AlerteEtude[];
  prelevements?: PrelevementEtude[];
}

export interface PropositionAffichee {
  id: string;
  type: TypeProposition;
  sous_type: string | null;
  valeur_proposee: string;
  /** Offsets de CARACTERES dans la transcription envoyee, calcules serveur. */
  empan_debut: number | null;
  empan_fin: number | null;
  /**
   * Faux quand AUCUN passage de la dictee ne soutient l'assertion. Distinct
   * d'un empan absent par accident : c'est la mesure centrale de l'etude, et
   * l'interface doit poser la question autrement — non plus "est-ce fidele ?"
   * mais "l'avez-vous dit ?".
   */
  ancree: boolean;
  chemin: string | null;
  confiance: number | null;
}

export interface DossierOuvert {
  dossier_id: string;
  propositions: PropositionAffichee[];
  /** Le dossier produit trop peu a valider pour etre exploitable. Ce n'est pas
   *  une erreur : c'est un signal a remonter a l'administration. */
  sous_extraction: boolean;
}

export interface DecisionEnvoi {
  decision: Decision;
  valeur_retenue?: string | null;
  /**
   * Pourquoi la correction : style, precision, ou erreur_fond.
   *
   * Seule `erreur_fond` impute une erreur au systeme. Sans ce champ, une
   * reformulation de confort et une erreur clinique comptent pareil, et le taux
   * publie ne veut rien dire. Le backend refuse une cause d'erreur sur une
   * nature qui n'est pas `erreur_fond`.
   */
  nature_correction?: string | null;
  cause_erreur?: CauseErreur | null;
  justif_ouverte?: boolean;
  justif_duree_ms?: number | null;
}

export interface ResultatDecision {
  latence_ms: number | null;
  /** Decision trop rapide pour avoir ete lue : analysee a part, pas rejetee. */
  hative: boolean;
}

export interface PauseEnvoi {
  /** ISO 8601. */
  debut: string;
  fin: string;
  cause: CausePause;
}

export interface ClotureDossier {
  cr_valide: string;
  omission_signalee?: boolean | null;
  omission_texte?: string | null;
  nb_prelevements_corrige?: number | null;
}

export interface ResultatCloture {
  caracteres_modifies: number | null;
}

export interface ItemQuestionnaire {
  id: string;
  libelle: string;
  type: TypeItem;
  options: string[];
  obligatoire: boolean;
  /** Item a polarite inversee (cotation F-SUS). */
  inverse: boolean;
  /** Identifiant d'un item precedent : celui-ci ne s'affiche que si l'autre a
   *  recu une reponse AUTRE QUE SA PREMIERE OPTION. */
  depend_de: string | null;
  /** Ancres de l'echelle, servies par item : voir etude/questionnaires.py. */
  ancre_basse: string;
  ancre_haute: string;
}

export interface Questionnaire {
  nom: NomQuestionnaire;
  titre: string;
  duree_estimee_s: number;
  items: ItemQuestionnaire[];
}

export interface ReponsesQuestionnaire {
  questionnaire: NomQuestionnaire;
  reponses: Record<string, string>;
  dossier_id?: string | null;
}

/* ------------------------------------------------------------------ */
/*  Types d'administration — miroir de routes_etude_admin.py           */
/* ------------------------------------------------------------------ */

/** Un rapport, toujours accompagne de ses deux termes bruts. `valeur` vaut
 *  null sur denominateur nul : une absence de mesure n'est pas un zero. */
export interface Taux {
  libelle: string;
  numerateur: number;
  denominateur: number;
  valeur: number | null;
}

export type NomTaux =
  | "acceptation_sans_modification"
  | "hallucination"
  | "bruit"
  | "exactitude_codes"
  | "abstention_codes"
  | "utilite_completude"
  | "decisions_hatives"
  | "changement_apres_justification";

export interface IndicateursPropositions {
  decidees: number;
  non_decidees: number;
  taux: Record<NomTaux, Taux>;
}

export interface Depouillement {
  toutes_decisions: IndicateursPropositions;
  /** L'ecart avec le depouillement complet mesure ce que le verrou d'export a
   *  gonfle : c'est un resultat, pas un detail de methode. */
  hors_decisions_hatives: IndicateursPropositions;
}

export interface CorpusEtude {
  nb_praticiens: number;
  nb_dossiers: number;
  nb_dossiers_clos: number;
  nb_abandons: number;
  motifs_abandon: Record<string, number>;
  organes: Record<string, number>;
  caracteres_modifies_moyen: number | null;
}

export interface ApprentissageEtude {
  caracteres_modifies_par_tercile: (number | null)[];
  nb_dossiers_retenus: number;
}

export interface SyntheseEtude {
  corpus: CorpusEtude;
  propositions: Depouillement;
  apprentissage: ApprentissageEtude;
}

export interface LigneDossier {
  id: string;
  praticien_id: string;
  index_session: number;
  organe: string | null;
  cree_a: string;
  abandonne: boolean;
  motif_abandon: MotifAbandon | null;
  nb_propositions: number;
  nb_decidees: number;
  caracteres_modifies: number | null;
  revision_nette_ms: number | null;
}

export interface PropositionDetaillee {
  id: string;
  type: TypeProposition;
  sous_type: string | null;
  valeur_proposee: string;
  chemin: string | null;
  confiance: number | null;
  empan_debut: number | null;
  empan_fin: number | null;
  /** Le passage exact de la dictee, decoupe cote serveur. */
  empan_extrait: string;
  longueur_mots: number | null;
  decision: Decision | null;
  valeur_retenue: string | null;
  cause_erreur: CauseErreur | null;
  latence_ms: number | null;
  hative: boolean;
  justif_ouverte: boolean;
  decision_changee_apres_justif: boolean;
}

export interface TempsDossier {
  dictee_ms: number | null;
  generation_ms: number | null;
  revision_ms: number | null;
  /** Duree de revision hors interruptions : le resultat principal de l'etude. */
  revision_nette_ms: number | null;
  pauses_ms: number;
  nb_pauses: number;
}

export interface PauseDetaillee {
  debut: string;
  fin: string | null;
  duree_ms: number | null;
  cause: CausePause;
}

export interface PrelevementDetaille {
  rang: number;
  libelle: string;
  /** Tableau de codes serialise en JSON, tel qu'il est stocke en base. */
  codes: string;
}

export interface DossierDetaille {
  id: string;
  praticien_id: string;
  organe: string | null;
  transcription: string;
  cr_propose: string;
  cr_valide: string | null;
  caracteres_modifies: number | null;
  abandonne: boolean;
  motif_abandon: MotifAbandon | null;
  omission_signalee: boolean | null;
  omission_texte: string | null;
  nb_prelevements_detecte: number | null;
  nb_prelevements_corrige: number | null;
  prelevements: PrelevementDetaille[];
  propositions: PropositionDetaillee[];
  temps: TempsDossier;
  pauses: PauseDetaillee[];
}

/* ------------------------------------------------------------------ */
/*  Transport                                                          */
/*  Le token est celui de services/api.ts : une seule gestion du JWT.  */
/* ------------------------------------------------------------------ */

async function lire<T>(reponse: Response): Promise<T> {
  if (!reponse.ok) {
    const corps: unknown = await reponse.json().catch(() => null);
    const detail =
      corps !== null &&
      typeof corps === "object" &&
      "detail" in corps &&
      typeof (corps as { detail: unknown }).detail === "string"
        ? (corps as { detail: string }).detail
        : `Erreur HTTP ${reponse.status}`;
    throw new ErreurEtude(reponse.status, detail);
  }
  return reponse.json() as Promise<T>;
}

function poster<T>(chemin: string, corps?: unknown): Promise<T> {
  return fetch(`${API_BASE}/etude${chemin}`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(corps ?? {}),
  }).then((reponse) => lire<T>(reponse));
}

function obtenir<T>(chemin: string): Promise<T> {
  return fetch(`${API_BASE}${chemin}`, { headers: getAuthHeaders() }).then(
    (reponse) => lire<T>(reponse),
  );
}

/* ------------------------------------------------------------------ */
/*  Session                                                            */
/* ------------------------------------------------------------------ */

export async function ouvrirSession(): Promise<string> {
  const { session_id } = await poster<{ session_id: string }>("/sessions");
  return session_id;
}

export async function cloreSession(sessionId: string): Promise<string> {
  const { statut } = await poster<{ statut: string }>(
    `/sessions/${sessionId}/cloture`,
  );
  return statut;
}

/* ------------------------------------------------------------------ */
/*  Dossier                                                            */
/* ------------------------------------------------------------------ */

export function ouvrirDossier(entree: OuvertureDossier): Promise<DossierOuvert> {
  return poster<DossierOuvert>("/dossiers", entree);
}

export function deciderProposition(
  propositionId: string,
  corps: DecisionEnvoi,
): Promise<ResultatDecision> {
  return poster<ResultatDecision>(
    `/propositions/${propositionId}/decision`,
    corps,
  );
}

/** Journalise une interruption du chronometre, une fois qu'elle est TERMINEE. */
export async function journaliserPause(
  dossierId: string,
  pause: PauseEnvoi,
): Promise<void> {
  await poster<{ statut: string }>(`/dossiers/${dossierId}/pauses`, pause);
}

export function cloreDossier(
  dossierId: string,
  corps: ClotureDossier,
): Promise<ResultatCloture> {
  return poster<ResultatCloture>(`/dossiers/${dossierId}/cloture`, corps);
}

/** Horodate la sortie du compte-rendu (t6). */
export async function marquerExport(dossierId: string): Promise<void> {
  await poster<{ statut: string }>(`/dossiers/${dossierId}/export`);
}

export async function abandonnerDossier(
  dossierId: string,
  motif: MotifAbandon,
): Promise<void> {
  await poster<{ statut: string }>(`/dossiers/${dossierId}/abandon`, { motif });
}

/* ------------------------------------------------------------------ */
/*  Questionnaires                                                     */
/* ------------------------------------------------------------------ */

/**
 * Les libelles viennent du backend et jamais d'une constante frontend : le
 * depouillement doit pouvoir associer une reponse a un libelle exact des mois
 * plus tard.
 *
 * Peut lever une ErreurEtude 409 : voir estQuestionnaireIndisponible.
 */
export function chargerQuestionnaire(
  nom: NomQuestionnaire,
): Promise<Questionnaire> {
  return obtenir<Questionnaire>(`/etude/questionnaires/${nom}`);
}

export async function envoyerReponses(
  corps: ReponsesQuestionnaire,
): Promise<number> {
  const { items_enregistres } = await poster<{ items_enregistres: number }>(
    "/questionnaires",
    corps,
  );
  return items_enregistres;
}

/* ------------------------------------------------------------------ */
/*  Administration                                                     */
/* ------------------------------------------------------------------ */

export function chargerSynthese(): Promise<SyntheseEtude> {
  return obtenir<SyntheseEtude>("/admin/etude/synthese");
}

export function chargerDossiers(): Promise<LigneDossier[]> {
  return obtenir<LigneDossier[]>("/admin/etude/dossiers");
}

export function chargerDossier(dossierId: string): Promise<DossierDetaille> {
  return obtenir<DossierDetaille>(`/admin/etude/dossiers/${dossierId}`);
}
