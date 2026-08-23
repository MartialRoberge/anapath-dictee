/**
 * Source de verite unique de la completude d'un compte-rendu.
 *
 * Trois indicateurs (pastille de la barre laterale, tiroir « Champs
 * obligatoires », badge de la barre d'outils) comptaient trois choses
 * differentes et s'affichaient en meme temps. Ils lisent desormais tous
 * l'etat calcule ici, une seule fois, par App.
 *
 * La verite PRIMAIRE est le TEXTE du compte-rendu : les pastilles
 * [A COMPLETER: xxx] sont ce que le praticien voit et ce qui partira dans le
 * .docx. Les marqueurs du backend n'apportent que des metadonnees (section,
 * caractere obligatoire) et les controles structurels qui, eux, n'ont pas de
 * pastille dans le texte. Un CR rouvert depuis l'historique n'a plus de
 * marqueurs : recalculer depuis le texte evite d'annoncer « complet » a tort.
 */

import type { Marker } from "../services/api";
import { findFieldKnowledge, type FieldKnowledge } from "../data/field-knowledge";

/* ------------------------------------------------------------------ */
/*  Champs administratifs (RGPD et entete)                             */
/* ------------------------------------------------------------------ */

// Ces champs relevent de l'entete du dossier, pas du raisonnement medical :
// le backend peut les signaler, l'interface ne les reclame pas au praticien.
// Le filtre ne s'applique QU'AUX marqueurs backend : une pastille reellement
// presente dans le texte est toujours comptee, sous peine de faux negatif.
const EXCLUDED_ADMIN_FIELDS: string[] = [
  "hopital", "hôpital", "nom du patient", "nom et prenom", "prenom",
  "patient", "date de naissance", "numero de dossier", "n° dossier",
  "numero", "numéro", "medecin prescripteur", "médecin prescripteur",
  "medecin referent", "médecin référent", "clinicien", "service demandeur",
  "nom du service", "adresse", "telephone", "téléphone",
  "securite sociale", "sécurité sociale", "ipp", "nda", "compte-rendu n",
  "renseignements cliniques", "renseignement clinique",
  "nom et signature", "signature", "nom du pathologiste",
  "pathologiste", "medecin signataire",
  "date du prelevement", "date de prélèvement", "date de reception",
  "date de réception", "date du compte", "date",
  "numero de compte", "reference", "référence",
  "nom",
];

function isAdminField(field: string): boolean {
  const normalized = field.toLowerCase();
  return EXCLUDED_ADMIN_FIELDS.some((excl) => normalized.includes(excl));
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type Severity = "error" | "warning" | "info";

/** Un champ restant a completer, pret a etre affiche. */
export interface PendingField {
  /** Cle stable (nom normalise) : relie texte, marqueurs et suggestions ignorees. */
  key: string;
  marker: Marker;
  knowledge: FieldKnowledge | null;
  severity: Severity;
}

/** Etat de completude affiche a l'identique par tous les indicateurs. */
export interface CompletionState {
  pending: PendingField[];
  /** Le seul nombre affiche : champs restant a traiter. */
  remaining: number;
  /** Champs que le praticien a explicitement ecartes. */
  dismissed: number;
  total: number;
  errorCount: number;
  warningCount: number;
  /**
   * Les marqueurs backend correspondent-ils au texte affiche ? Si non, on ne
   * sait pas si le CR est complet et l'interface ne doit pas l'affirmer.
   */
  verified: boolean;
}

export interface CompletionInput {
  report: string | null;
  markers: Marker[];
  /** Cles normalisees des champs ecartes par le praticien. */
  dismissedFields: Set<string>;
  organeDetecte: string;
  /** true si les marqueurs ont ete calcules sur CE texte exactement. */
  markersMatchReport: boolean;
}

export const EMPTY_COMPLETION: CompletionState = {
  pending: [],
  remaining: 0,
  dismissed: 0,
  total: 0,
  errorCount: 0,
  warningCount: 0,
  verified: false,
};

/* ------------------------------------------------------------------ */
/*  Extraction depuis le texte                                         */
/* ------------------------------------------------------------------ */

const A_COMPLETER_PATTERN = "\\[(?:[AÀ]\\s*COMPL[EÉ]TER)\\s*:\\s*([^\\]]+)\\]";

/** Nom de champ -> cle comparable (casse, accents et espaces neutralises). */
export function normalizeFieldKey(field: string): string {
  return field
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Champs signales par une pastille [A COMPLETER: ...] visible dans le CR. */
function fieldsFromText(report: string): string[] {
  const regex = new RegExp(A_COMPLETER_PATTERN, "gi");
  const seen = new Set<string>();
  const fields: string[] = [];
  for (const match of report.matchAll(regex)) {
    const field = match[1].trim();
    const key = normalizeFieldKey(field);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    fields.push(field);
  }
  return fields;
}

/** Marqueur minimal pour une pastille du texte que le backend n'a pas decrite. */
function markerFromText(field: string): Marker {
  return {
    field,
    section: "non_determine",
    rule_id: `texte.${normalizeFieldKey(field)}`,
    severity: "error",
    message: "Champ signale a completer dans le texte du compte-rendu.",
    auto_filled: false,
    auto_filled_value: "",
  };
}

/* ------------------------------------------------------------------ */
/*  Calcul unique                                                      */
/* ------------------------------------------------------------------ */

function toPendingField(marker: Marker, organeDetecte: string): PendingField {
  const knowledge = findFieldKnowledge(marker.field, organeDetecte);
  return {
    key: normalizeFieldKey(marker.field),
    marker,
    knowledge,
    severity: knowledge?.severity ?? marker.severity,
  };
}

/** Les champs obligatoires d'abord : c'est l'ordre de lecture attendu. */
function errorsFirst(a: PendingField, b: PendingField): number {
  if (a.severity === "error" && b.severity !== "error") return -1;
  if (a.severity !== "error" && b.severity === "error") return 1;
  return 0;
}

/**
 * Assemble les champs a completer : pastilles du texte (source primaire)
 * completees par les marqueurs backend qui n'ont pas de pastille (controles
 * structurels), moins ce que le praticien a ecarte.
 */
export function computeCompletion(input: CompletionInput): CompletionState {
  const { report, markers, dismissedFields, organeDetecte, markersMatchReport } = input;
  if (!report) return EMPTY_COMPLETION;

  const byKey = new Map<string, Marker>();
  for (const field of fieldsFromText(report)) {
    byKey.set(normalizeFieldKey(field), markerFromText(field));
  }
  for (const marker of markers) {
    const key = normalizeFieldKey(marker.field);
    if (byKey.has(key)) {
      // Le backend decrit une pastille deja vue : ses metadonnees priment.
      byKey.set(key, marker);
      continue;
    }
    if (isAdminField(marker.field)) continue;
    byKey.set(key, marker);
  }

  const all = [...byKey.values()].map((m) => toPendingField(m, organeDetecte));
  const pending = all.filter((f) => !dismissedFields.has(f.key)).sort(errorsFirst);
  const errorCount = pending.filter((f) => f.severity === "error").length;

  return {
    pending,
    remaining: pending.length,
    dismissed: all.length - pending.length,
    total: all.length,
    errorCount,
    warningCount: pending.length - errorCount,
    verified: markersMatchReport,
  };
}
