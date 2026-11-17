// Vue « Pourquoi » : logique pure (preuves normalisées, somme de confiance, passage de dictée, résumé de progression).
import type { Alerte, Element, Preuve, Projet, SourceRef } from "../types";

export const CATEGORIES: Array<{ cle: Preuve["categorie"]; titre: string }> = [
  { cle: "dictee", titre: "Dictée" },
  { cle: "regle", titre: "Règles" },
  { cle: "referentiel", titre: "Référentiel" },
  { cle: "modele", titre: "Modèle" },
];

/** Nombre à la française : 0,62 (pas de point décimal). */
export const nombre = (n: number, d = 2) => n.toFixed(d).replace(".", ",");

/** Une phrase à relire : confiance basse ou raison explicite du contrat. Seul signe visuel du document avec la sélection. */
export const aRelire = (el: Element): boolean => el.type !== "trou" && (el.niveau === "basse" || !!el.a_verifier);

/** Preuves de l'élément ; pour un ancien projet (sans `preuves`), on les reconstruit depuis `sources` et `explication`. */
export function preuvesDe(el: Element): Preuve[] {
  if (el.preuves && el.preuves.length > 0) return el.preuves;
  const out: Preuve[] = [];
  for (const s of el.sources) {
    if (s.kind === "dictee") out.push({ categorie: "dictee", verdict: "info", titre: "Passage dicté", detail: s.extrait ?? "", source: s });
    else if (s.kind === "regle") out.push({ categorie: "regle", verdict: "info", titre: s.libelle, detail: "", source: s });
    else if (s.kind === "kb" || s.kind === "web") out.push({ categorie: "referentiel", verdict: "info", titre: s.libelle, detail: s.extrait ?? "", source: s });
  }
  if (el.explication) out.push({ categorie: "modele", verdict: "info", titre: "Explication", detail: el.explication });
  return out;
}

/** Intitulés des sections pour un trou : aucun modèle n'intervient, la section Modèle n'existe pas. */
export const TITRES_TROU: Partial<Record<Preuve["categorie"], string>> = { dictee: "Dictée", regle: "Pourquoi c'est demandé", referentiel: "Référentiel" };

/**
 * Preuves d'un trou : celles du backend sans la catégorie « modèle » (rien n'est généré pour un champ vide).
 * Sans preuves, repli minimal : « Non dicté » et « Exigé par » avec la source du référentiel.
 */
export function preuvesTrou(el: Element): Preuve[] {
  const out = (el.preuves ?? []).filter((p) => p.categorie !== "modele");
  const src = el.sources.find((s) => s.kind !== "dictee" && s.kind !== "agent");
  if (!out.some((p) => p.categorie === "dictee")) out.unshift({ categorie: "dictee", verdict: "info", titre: "Non dicté", detail: "" });
  if (!out.some((p) => p.categorie === "regle") && src) out.push({ categorie: "regle", verdict: "info", titre: "Exigé par", detail: "", source: src });
  return out;
}

export const parCategorie = (preuves: Preuve[], titres: Partial<Record<Preuve["categorie"], string>> = {}) =>
  CATEGORIES.map((c) => ({ ...c, titre: titres[c.cle] ?? c.titre, preuves: preuves.filter((p) => p.categorie === c.cle) })).filter((c) => c.preuves.length > 0);

export const VERDICT: Record<Preuve["verdict"], string> = { ok: "Conforme", attention: "À vérifier", echec: "Non conforme", info: "" };
export const verdictAmbre = (v: Preuve["verdict"]) => v === "attention" || v === "echec";

/** Passage de dictée autour de l'empan, avec un peu de contexte. Bornes invalides : null (jamais d'approximation). */
export function passageDictee(texte: string, s: Pick<SourceRef, "debut" | "fin">, marge = 60) {
  const { debut, fin } = s;
  if (debut == null || fin == null || !Number.isInteger(debut) || !Number.isInteger(fin) || debut < 0 || fin <= debut || fin > texte.length) return null;
  const a = Math.max(0, debut - marge);
  const b = Math.min(texte.length, fin + marge);
  return { avant: (a > 0 ? "… " : "") + texte.slice(a, debut), cite: texte.slice(debut, fin), apres: texte.slice(fin, b) + (b < texte.length ? " …" : "") };
}

export interface TermeConfiance { libelle: string; valeur: number }

/** Confiance = somme des effets. Si les effets ne couvrent pas tout, un terme « base » complète pour que la somme reste exacte. */
export function termesConfiance(el: Element): TermeConfiance[] {
  const effets = preuvesDe(el).filter((p) => typeof p.effet === "number" && p.effet !== 0).map((p) => ({ libelle: p.titre, valeur: p.effet as number }));
  if (effets.length === 0) return [];
  const somme = effets.reduce((t, e) => t + e.valeur, 0);
  const reste = el.confiance - somme;
  return Math.abs(reste) >= 0.005 ? [{ libelle: "base", valeur: reste }, ...effets] : effets;
}

export function formuleConfiance(el: Element): string | null {
  const t = termesConfiance(el);
  if (t.length === 0) return null;
  const corps = t.map((x, i) => `${i === 0 ? (x.valeur < 0 ? "− " : "") : x.valeur < 0 ? " − " : " + "}${x.libelle.toLowerCase()} ${nombre(Math.abs(x.valeur))}`).join("");
  return `Confiance ${nombre(el.confiance)} = ${corps}`;
}

/** Alerte : « pourquoi », calcul et action avec repli sur message/suggestion pour les anciens projets. */
export const alerteTextes = (a: Alerte) => ({
  titre: a.message,
  pourquoi: a.pourquoi && a.pourquoi !== a.message ? a.pourquoi : null,
  calcul: a.calcul || null,
  action: a.action || (a.suggestion ? `Suggestion : ${a.suggestion}` : null),
});

export interface LigneResume { texte: string; onglet?: "alertes" | "codes" | "dictee"; alerte?: boolean }

const pluriel = (n: number, un: string, plu = `${un}s`) => `${n} ${n > 1 ? plu : un}`;

/** Résumé en langage clair de ce que le traitement a fait. */
export function resumeProjet(p: Projet): LigneResume[] {
  const l: LigneResume[] = [];
  const { organes_libelles, prelevement } = p.contexte;
  if (organes_libelles.length) l.push({ texte: `Organe identifié : ${organes_libelles.join(", ").toLowerCase()}${prelevement ? `, ${prelevement}` : ""}` });
  const corr = p.corrections.filter((c) => c.appliquee).length;
  if (corr) l.push({ texte: `${pluriel(corr, "terme corrigé", "termes corrigés")} à l'écoute`, onglet: "dictee" });
  const regles = p.elements.filter((e) => e.type !== "trou").flatMap((e) => (e.preuves ?? []).filter((x) => x.categorie === "regle"));
  if (regles.length) {
    const revoir = regles.filter((r) => verdictAmbre(r.verdict)).length;
    l.push({ texte: `${pluriel(regles.length, "règle vérifiée", "règles vérifiées")}, ${revoir ? `${revoir} à revoir` : "toutes conformes"}`, alerte: revoir > 0 });
  }
  const manquants = p.elements.filter((e) => e.type === "trou" && e.obligatoire).length;
  if (manquants) l.push({ texte: `${pluriel(manquants, "champ obligatoire manquant", "champs obligatoires manquants")}`, onglet: "alertes", alerte: true });
  const systemes = [...new Set(p.codes.map((c) => c.systeme.replace("_", " ").replace("CIM O3", "CIM-O3")))];
  if (systemes.length) l.push({ texte: `Codes ${systemes.join(", ")} proposés`, onglet: "codes" });
  const relire = p.elements.filter(aRelire).length;
  if (relire) l.push({ texte: `${pluriel(relire, "phrase à relire", "phrases à relire")} en priorité`, alerte: true });
  return l;
}
