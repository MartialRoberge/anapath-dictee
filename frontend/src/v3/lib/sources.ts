// Sources : libellés de fiabilité en mots, extrait (citation ou localisation) et lecture défensive de la fiche de consultation.
// La forme de GET /v3/kb/sources/{id} est en cours de définition côté backend : tout est optionnel, plusieurs noms de clé sont acceptés.
import type { SourceRef } from "../types";

export type Fiabilite = NonNullable<SourceRef["fiabilite"]>;

/** Fiabilité écrite en mots, discrète (jamais la lettre seule). */
export const FIABILITE_MOT: Record<Fiabilite, string> = {
  A: "Référentiel officiel",
  B: "Pathologiste référente",
  C: "Synthèse MARC à valider",
  D: "Non validé",
};

/** Une phrase pour expliquer ce que la fiabilité implique. */
export const FIABILITE_PHRASE: Record<Fiabilite, string> = {
  A: "Référentiel officiel publié, national ou international (INCa, ANS, OMS).",
  B: "Document de la pathologiste référente, ou règle MARC relue par elle.",
  C: "Synthèse ou dérivé interne de MARC : à faire valider par la pathologiste référente.",
  D: "Semence ou heuristique non validée : à recouper avant de s'y fier.",
};

export const motFiabilite = (f?: string | null): string | null => (f && f in FIABILITE_MOT ? FIABILITE_MOT[f as Fiabilite] : null);

/**
 * Extrait d'une source : « localisation » (chapitre, rubrique, fiche : court, sans ponctuation finale)
 * ou « citation » (phrase du texte, affichée entre guillemets). La dictée est toujours une citation.
 */
export function formeExtrait(s: Pick<SourceRef, "kind" | "extrait">): { type: "citation" | "localisation"; texte: string } | null {
  const brut = (s.extrait ?? "").trim();
  if (!brut) return null;
  const sansGuillemets = brut.replace(/^[«"“]\s*/, "").replace(/\s*[»"”]$/, "");
  const entoure = sansGuillemets !== brut;
  const localisation = s.kind !== "dictee" && !entoure && brut.length <= 70 && !/[.!?…]$/.test(brut);
  return { type: localisation ? "localisation" : "citation", texte: sansGuillemets };
}

export interface SourceDetail {
  titre?: string;
  description?: string;
  editeur?: string;
  date?: string;
  version?: string;
  fiabilite?: Fiabilite;
  url?: string;
  /** Sens de la fiabilité en une phrase, fourni par la base. */
  fiabilite_sens?: string;
  note?: string;
  licence?: string;
  /** Champs et règles qui citent cette source. */
  cite_par: Array<{ libelle: string; type?: string }>;
  /** Nombre total d'éléments de la base qui citent la source (peut dépasser la liste). */
  cite_total?: number;
}

const txt = (v: unknown): string | undefined => (typeof v === "string" && v.trim() ? v.trim() : typeof v === "number" ? String(v) : undefined);
const premier = (o: Record<string, unknown>, cles: string[]) => cles.map((k) => txt(o[k])).find(Boolean);

function citations(o: Record<string, unknown>): SourceDetail["cite_par"] {
  const out: SourceDetail["cite_par"] = [];
  for (const cle of ["cite_par", "citee_par", "utilise_par", "citations", "champs", "regles", "references"]) {
    let v = o[cle];
    if (v && typeof v === "object" && !Array.isArray(v)) v = (v as Record<string, unknown>).elements; // { total, par_type, elements }
    if (!Array.isArray(v)) continue;
    const type = cle === "regles" ? "règle" : cle === "champs" ? "champ" : undefined;
    for (const x of v) {
      if (typeof x === "string" && x.trim()) out.push({ libelle: x.trim(), type });
      else if (x && typeof x === "object") {
        const r = x as Record<string, unknown>;
        const libelle = premier(r, ["libelle", "titre", "label", "nom", "champ_id", "regle_id", "id"]);
        if (libelle) out.push({ libelle, type: premier(r, ["type", "kind", "categorie"]) ?? type });
      }
    }
  }
  return out;
}

/** Réponse brute -> fiche exploitable. Une réponse inattendue donne une fiche vide (jamais d'exception). */
export function normaliserDetail(brut: unknown): SourceDetail {
  const o = brut && typeof brut === "object" ? (brut as Record<string, unknown>) : {};
  const f = txt(o.fiabilite);
  const url = premier(o, ["url", "lien"]);
  return {
    titre: premier(o, ["titre_court", "titre", "libelle", "nom"]),
    description: premier(o, ["description", "resume", "notes"]),
    editeur: premier(o, ["editeur", "organisme", "auteur", "publisher"]),
    date: premier(o, ["date", "date_publication", "date_version", "annee"]),
    version: premier(o, ["version", "edition"]),
    fiabilite: f && f in FIABILITE_MOT ? (f as Fiabilite) : undefined,
    url: url && /^https?:\/\//i.test(url) ? url : undefined,
    fiabilite_sens: premier(o, ["fiabilite_sens"]),
    note: premier(o, ["note"]),
    licence: premier(o, ["licence"]),
    cite_par: citations(o),
    cite_total: (() => {
      const r = o.references as Record<string, unknown> | undefined;
      return r && typeof r === "object" && typeof r.total === "number" ? r.total : undefined;
    })(),
  };
}

/** Les sources de type dictée ou agent n'ont pas de fiche dans la base : pas d'appel réseau. */
export const aUneFiche = (s: Pick<SourceRef, "kind">) => s.kind === "kb" || s.kind === "regle" || s.kind === "web";
