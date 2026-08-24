/**
 * Brouillons locaux : un enregistrement par dossier.
 *
 * L'autosave ecrivait sous une cle unique : ouvrir un second dossier ecrasait
 * silencieusement le brouillon du premier. Chaque dossier a desormais sa
 * propre cle, et les brouillons perimes sont purges au chargement pour que le
 * navigateur ne conserve pas indefiniment des donnees de compte-rendu.
 */

import type {
  CoherenceVerdict,
  DonneeManquante,
  Marker,
  ReportTrace,
} from "../services/api";

const PREFIX = "iris_autosave:";

// Ancienne cle unique, conservee le temps d'une migration : sans elle, le
// brouillon en cours au moment de la mise a jour serait perdu.
const LEGACY_KEY = "iris_autosave";

// Au-dela d'un jour un brouillon local n'a plus de valeur : soit le CR a ete
// sauvegarde en base, soit il est abandonne.
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface DraftExplication {
  trace: ReportTrace;
  warnings: string[];
  coherence: CoherenceVerdict;
}

export interface Draft {
  report: string;
  rawTranscription: string | null;
  organeDetecte: string;
  explication: DraftExplication | null;
  /**
   * CE QUI RESTE A COMPLETER, et il faut le garder.
   *
   * Sans ces deux listes, un rafraichissement de page rendait le compte rendu
   * et son explicabilite, mais plus rien de la completude : les trous du texte
   * restaient affiches sans leur declencheur, sans leur raison et sans leurs
   * options, et la liste « a completer » sortait vide. Le praticien voyait donc
   * un compte rendu qui n'avait plus rien a completer, ce qui est faux.
   */
  markers?: Marker[];
  manquants?: DonneeManquante[];
  timestamp: number;
}

/** Identifiant de brouillon pour un CR qui n'existe pas encore en base. */
export function createDraftId(): string {
  // randomUUID n'existe qu'en contexte securise : repli sur horodatage + alea.
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

function isDraft(value: unknown): value is Partial<Draft> {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Partial<Draft>;
  return typeof draft.report === "string" && typeof draft.timestamp === "number";
}

/** JSON stocke -> brouillon complet, ou null si illisible ou incomplet. */
function parseDraft(raw: string | null): Draft | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isDraft(parsed)) return null;
    return {
      report: parsed.report ?? "",
      rawTranscription: parsed.rawTranscription ?? null,
      organeDetecte: parsed.organeDetecte ?? "",
      explication: parsed.explication ?? null,
      timestamp: parsed.timestamp ?? 0,
    };
  } catch {
    return null;
  }
}

function draftKeys(): string[] {
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith(PREFIX)) keys.push(key);
  }
  return keys;
}

/** Supprime les brouillons perimes ou illisibles. */
function purgeExpired(): void {
  const now = Date.now();
  for (const key of draftKeys()) {
    const draft = parseDraft(localStorage.getItem(key));
    if (!draft || now - draft.timestamp > MAX_AGE_MS) localStorage.removeItem(key);
  }
}

/** Reprend l'ancien brouillon a cle unique sous la nouvelle convention. */
function migrateLegacyDraft(): void {
  const legacy = localStorage.getItem(LEGACY_KEY);
  if (legacy === null) return;
  localStorage.removeItem(LEGACY_KEY);
  if (parseDraft(legacy)) localStorage.setItem(PREFIX + createDraftId(), legacy);
}

export function saveDraft(draftId: string, draft: Draft): void {
  try {
    localStorage.setItem(PREFIX + draftId, JSON.stringify(draft));
  } catch {
    // Quota depasse : on libere les brouillons perimes plutot que de
    // laisser l'exception interrompre l'edition en cours.
    purgeExpired();
  }
}

export function removeDraft(draftId: string): void {
  localStorage.removeItem(PREFIX + draftId);
}

/** Brouillon valide le plus recent, les perimes etant purges au passage. */
export function loadLatestDraft(): { id: string; draft: Draft } | null {
  migrateLegacyDraft();
  purgeExpired();
  let latest: { id: string; draft: Draft } | null = null;
  for (const key of draftKeys()) {
    const draft = parseDraft(localStorage.getItem(key));
    if (!draft) continue;
    if (!latest || draft.timestamp > latest.draft.timestamp) {
      latest = { id: key.slice(PREFIX.length), draft };
    }
  }
  return latest;
}
