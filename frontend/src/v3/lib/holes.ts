// Logique des trous (textes à trous) : libellés, valeurs, ordre document, navigation Tab.
import type { Element } from "../types";

/** « Taille tumorale (mm) » -> « Taille tumorale ». */
export function libelleSansUnite(libelle: string): string {
  return libelle.replace(/\s*\(([^)]*)\)\s*$/, "").trim();
}

/** Unité d'un trou : champ `unite`, sinon parenthèse finale courte du libellé (« mm », « % »). */
export function uniteDuTrou(el: Pick<Element, "texte" | "unite">): string | null {
  if (el.unite) return el.unite;
  const m = el.texte.match(/\(([^)]{1,6})\)\s*$/);
  return m ? m[1].trim() : null;
}

const NOMBRE = /^\s*[<>≤≥]?\s*\d+([.,]\d+)?\s*$/;

/** Valeur saisie -> texte du compte rendu : unité ajoutée seulement pour un nombre nu. */
export function valeurAvecUnite(valeur: string, unite: string | null): string {
  const v = valeur.trim();
  if (unite && NOMBRE.test(v)) return `${v} ${unite}`;
  return v;
}

export type EtatTrou = "ouvert" | "rempli" | "ignore";

export interface TrouOrdre { id: string; ouvert: boolean }

/**
 * Trou suivant (sens=1) ou précédent (sens=-1) un trou ouvert, dans l'ordre du document.
 * `courantId` peut être un trou déjà résolu (on repart de sa position) ou null (début).
 */
export function prochainTrou(ordre: TrouOrdre[], courantId: string | null, sens: 1 | -1 = 1): string | null {
  if (ordre.length === 0) return null;
  const i = courantId ? ordre.findIndex((t) => t.id === courantId) : -1;
  if (sens === 1) {
    for (let k = i + 1; k < ordre.length; k++) if (ordre[k].ouvert) return ordre[k].id;
  } else {
    for (let k = (i === -1 ? ordre.length : i) - 1; k >= 0; k--) if (ordre[k].ouvert) return ordre[k].id;
  }
  return null;
}

/** Filtre de la liste d'options d'un trou (insensible à la casse et aux accents). */
export function filtrerOptions(options: string[], saisie: string): string[] {
  const norm = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const q = norm(saisie.trim());
  return q ? options.filter((o) => norm(o).includes(q)) : options;
}
