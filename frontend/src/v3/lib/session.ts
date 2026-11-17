// État local d'un projet ouvert : le Projet serveur (immuable) + les décisions du praticien.
// Fonctions pures : aucune écriture réseau, tout reste dans le navigateur.
import type { Alerte, Code, Element, Projet, Section } from "../types";
import { prochainTrou, type EtatTrou, type TrouOrdre } from "./holes";

export type DecisionAlerte = "resolue" | "ignoree";

export interface ProjetLocal {
  projet: Projet;
  /** Texte édité par élément (remplace element.texte à l'affichage et à la copie). */
  edits: Record<string, string>;
  /** Trous : valeur saisie, ou null = ignoré. Absent = ouvert. */
  fills: Record<string, string | null>;
  alertes: Record<string, DecisionAlerte>;
  /** Corrections phonétiques : décision du praticien (choix = candidat retenu). */
  corrections: Record<string, { appliquee: boolean; choix?: string }>;
  /** Codes modifiés : clé `${systeme}:${code}` -> nouveau code. */
  codes: Record<string, string>;
  /** Titre édité. */
  titre?: string;
  feedback?: { sens: "plus" | "moins"; motif: string };
  source: "audio" | "texte";
  maj: number;
}

export function creerLocal(projet: Projet, source: "audio" | "texte"): ProjetLocal {
  return { projet, edits: {}, fills: {}, alertes: {}, corrections: {}, codes: {}, source, maj: Date.now() };
}

export const estTrou = (el: Element) => el.type === "trou" && el.statut === "a_completer";

export const texteElement = (l: ProjetLocal, el: Element) => l.edits[el.id] ?? el.texte;

export function etatTrou(l: ProjetLocal, el: Element): EtatTrou {
  if (!(el.id in l.fills)) return "ouvert";
  return l.fills[el.id] === null ? "ignore" : "rempli";
}

export interface BlocSection { section: Section; elements: Element[] }

/** Sections triées + leurs éléments, dans l'ordre du document. Les éléments orphelins vont en fin. */
export function ordreDocument(projet: Projet): BlocSection[] {
  const sections = [...projet.sections].sort((a, b) => a.ordre - b.ordre);
  const blocs = sections.map((section) => ({ section, elements: projet.elements.filter((e) => e.section_id === section.id) }));
  const connus = new Set(sections.map((s) => s.id));
  const orphelins = projet.elements.filter((e) => !connus.has(e.section_id));
  if (orphelins.length) blocs.push({ section: { id: "__autres", titre: "Autres éléments", ordre: 9999 }, elements: orphelins });
  return blocs;
}

export function trousOrdonnes(l: ProjetLocal): TrouOrdre[] {
  return ordreDocument(l.projet)
    .flatMap((b) => b.elements)
    .filter(estTrou)
    .map((el) => ({ id: el.id, ouvert: etatTrou(l, el) === "ouvert" }));
}

export const trouSuivant = (l: ProjetLocal, courantId: string | null, sens: 1 | -1 = 1) =>
  prochainTrou(trousOrdonnes(l), courantId, sens);

export const trousOuverts = (l: ProjetLocal) => trousOrdonnes(l).filter((t) => t.ouvert).length;

export const alertesOuvertes = (l: ProjetLocal): Alerte[] => l.projet.alertes.filter((a) => !l.alertes[a.id]);

export const codeAffiche = (l: ProjetLocal, c: Code) => l.codes[`${c.systeme}:${c.code}`] ?? c.code;

const maj = (l: ProjetLocal, patch: Partial<ProjetLocal>): ProjetLocal => ({ ...l, ...patch, maj: Date.now() });

export const editerTitre = (l: ProjetLocal, titre: string) => maj(l, { titre });
export const titreAffiche = (l: ProjetLocal) => l.titre ?? l.projet.titre;
export const editerElement = (l: ProjetLocal, id: string, texte: string) => maj(l, { edits: { ...l.edits, [id]: texte } });
// Combler un trou règle l'alerte « champ manquant » qui ne portait que sur des trous désormais remplis (jamais ignorés) :
// un geste de moins par point. Rouvrir le trou rouvre l'alerte. Les autres types d'alerte ne sont jamais touchés.
const manquantes = (l: ProjetLocal, trouId: string) => l.projet.alertes.filter((a) => a.type === "manquant" && a.element_ids.includes(trouId));
const toutRempli = (fills: ProjetLocal["fills"], ids: string[]) => ids.length > 0 && ids.every((i) => typeof fills[i] === "string" && fills[i] !== "");
export const remplirTrou = (l: ProjetLocal, id: string, valeur: string) => {
  const fills = { ...l.fills, [id]: valeur };
  const alertes = { ...l.alertes };
  for (const a of manquantes(l, id)) if (!alertes[a.id] && toutRempli(fills, a.element_ids)) alertes[a.id] = "resolue";
  return maj(l, { fills, alertes });
};
export const ignorerTrou = (l: ProjetLocal, id: string) => maj(l, { fills: { ...l.fills, [id]: null } });
const sans = <T,>(o: Record<string, T>, cle: string): Record<string, T> => Object.fromEntries(Object.entries(o).filter(([k]) => k !== cle));
export const rouvrirTrou = (l: ProjetLocal, id: string) => {
  const alertes = { ...l.alertes };
  for (const a of manquantes(l, id)) if (alertes[a.id] === "resolue") delete alertes[a.id];
  return maj(l, { fills: sans(l.fills, id), alertes });
};
export const decider = (l: ProjetLocal, alerteId: string, d: DecisionAlerte | null) => {
  const reste = sans(l.alertes, alerteId);
  return maj(l, { alertes: d ? { ...reste, [alerteId]: d } : reste });
};
export const modifierCode = (l: ProjetLocal, c: Code, nouveau: string) =>
  maj(l, { codes: { ...l.codes, [`${c.systeme}:${c.code}`]: nouveau } });
export const donnerFeedback = (l: ProjetLocal, sens: "plus" | "moins", motif: string) => maj(l, { feedback: { sens, motif } });

const echapper = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Décision sur une correction phonétique : remplace dans les éléments le terme précédemment appliqué
 * par le terme choisi (original ou candidat). Rien n'est inventé : seuls des termes déjà proposés par l'agent.
 */
export function decisionCorrection(l: ProjetLocal, corrId: string, choix: string | "original"): ProjetLocal {
  const c = l.projet.corrections.find((x) => x.id === corrId);
  if (!c) return l;
  const precedent = l.corrections[corrId];
  const termeAvant = !precedent ? (c.appliquee ? c.corrige : c.original) : precedent.appliquee ? (precedent.choix ?? c.corrige) : c.original;
  const termeApres = choix === "original" ? c.original : choix;
  const appliquee = choix !== "original";
  let edits = l.edits;
  if (termeAvant !== termeApres) {
    const re = new RegExp(echapper(termeAvant), "g");
    edits = { ...l.edits };
    for (const el of l.projet.elements) {
      const t = l.edits[el.id] ?? el.texte;
      if (re.test(t)) edits[el.id] = t.replace(re, termeApres);
      re.lastIndex = 0;
    }
  }
  return maj(l, { edits, corrections: { ...l.corrections, [corrId]: { appliquee, choix: appliquee ? choix : undefined } } });
}

/** Tranche de longueur pour la télémétrie (jamais le texte lui-même). */
export function tranche(n: number): string {
  if (n <= 0) return "0";
  if (n <= 10) return "1-10";
  if (n <= 50) return "11-50";
  if (n <= 200) return "51-200";
  return "200+";
}

/** Nombre de caractères modifiés entre deux textes (distance grossière préfixe/suffixe commun). */
export function caracteresModifies(avant: string, apres: string): number {
  let i = 0;
  while (i < avant.length && i < apres.length && avant[i] === apres[i]) i++;
  let j = 0;
  while (j < avant.length - i && j < apres.length - i && avant[avant.length - 1 - j] === apres[apres.length - 1 - j]) j++;
  return Math.max(avant.length - i - j, apres.length - i - j);
}

/**
 * Fusion après une itération : le nouveau projet remplace l'ancien, les décisions du praticien
 * sont conservées là où elles ont encore un sens (élément, alerte, correction ou trou toujours présents).
 */
export function fusionnerIteration(ancien: ProjetLocal, projet: Projet): ProjetLocal {
  const ids = new Set(projet.elements.map((e) => e.id));
  const trous = new Set(projet.elements.filter(estTrou).map((e) => e.id));
  const garder = <T,>(src: Record<string, T>, ok: (k: string) => boolean) => Object.fromEntries(Object.entries(src).filter(([k]) => ok(k)));
  return {
    ...ancien,
    projet,
    edits: garder(ancien.edits, (k) => ids.has(k)),
    fills: garder(ancien.fills, (k) => trous.has(k)),
    alertes: garder(ancien.alertes, (k) => projet.alertes.some((a) => a.id === k)),
    corrections: garder(ancien.corrections, (k) => projet.corrections.some((c) => c.id === k)),
    maj: Date.now(),
  };
}
