// Flux SSE simulé (mode ?demo=1) : rejoue la trace réelle de la fixture avec de vraies durées compressées.
// Aucun faux message : les étapes affichées sont celles de la fixture, dans l'ordre.
import type { Element, Projet, ProjetEvent, TraceStep } from "../types";
import { projetDemo } from "./projetPoumon";
import { normaliserDetail, type SourceDetail } from "../lib/sources";

const attendre = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("Abort", "AbortError")); }, { once: true });
  });

/** Échelle temporelle de la démo : 1 = durées réelles ; 0.25 = 4x plus rapide. */
const ECHELLE = 0.3;

export async function demoFlux(onEvent: (e: ProjetEvent) => void, signal?: AbortSignal, projet: Projet = projetDemo, retarder = 350) {
  await attendre(retarder, signal);
  const etapes = projet.trace;
  for (let i = 0; i < etapes.length; i++) {
    const t = etapes[i];
    const enCours: TraceStep = { ...t, statut: "en_cours", duree_ms: null, resume: "", details: [] };
    onEvent({ event: "step", data: enCours });
    // les étapes parallèles (même début) se terminent ensemble
    await attendre((t.duree_ms ?? 400) * ECHELLE, signal);
    onEvent({ event: "step", data: t });
    if (t.role === "redacteur") {
      const partiel: Element[] = projet.elements.slice(0, 6);
      onEvent({ event: "partial", data: { elements: partiel } });
    }
  }
  await attendre(250, signal);
  onEvent({ event: "projet", data: projet });
}

/** Itération démo : la dictée d'appoint comble le trou PD-L1 par une phrase, l'alerte bloquante disparaît. */
export async function demoIterer(projet: Projet, onEvent: (e: ProjetEvent) => void, signal?: AbortSignal) {
  const etape = (statut: TraceStep["statut"], resume = ""): TraceStep => ({
    id: "it1", agent: "Rédacteur", role: "redacteur", titre: "Intégrer la dictée complémentaire", statut, debut_ms: 0, duree_ms: statut === "ok" ? 900 : null, modele: "mistral-large-latest", resume, details: [],
  });
  onEvent({ event: "step", data: etape("en_cours") });
  await attendre(700, signal);
  onEvent({ event: "step", data: etape("ok", "Complément intégré sans modifier le reste du projet.") });
  const elements = projet.elements.map((e): Element =>
    e.id === "e9" ? { ...e, type: "phrase", statut: "dicte", texte: "PD-L1 : expression dans moins de 1 % des cellules tumorales.", confiance: 0.9, niveau: "haute", explication: "Ajouté depuis la dictée complémentaire." } : e);
  onEvent({ event: "projet", data: { ...projet, elements, alertes: projet.alertes.filter((a) => a.id !== "a1") } });
}

export async function demoExporter(): Promise<Blob> {
  await attendre(300);
  return new Blob(["Export DOCX de démonstration"], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
}

/** Fiches de consultation de démonstration (clés = `SourceRef.ref`). Une source inconnue échoue, comme un 404. */
const FICHES: Record<string, unknown> = {
  inca_poumon_2011: {
    titre: "INCa · Cancer bronchopulmonaire : données minimales", description: "Liste des données minimales à faire figurer dans le compte rendu anatomopathologique d'un cancer bronchopulmonaire.",
    editeur: "Institut national du cancer", date: "2011", version: "Données minimales, mise à jour 2011", fiabilite: "A", url: "https://www.e-cancer.fr",
    cite_par: [{ libelle: "PD-L1 (% de cellules tumorales)", type: "champ" }, { libelle: "Biologie moléculaire (EGFR, ALK, ROS1)", type: "champ" }, { libelle: "Champ obligatoire : biomarqueurs", type: "règle" }],
  },
  oms_2021_thorax: {
    titre: "OMS 2021 · Tumeurs thoraciques", description: "Classification des tumeurs du poumon, de la plèvre, du thymus et du cœur.",
    editeur: "Organisation mondiale de la santé, CIRC", date: "2021", version: "5e édition", fiabilite: "A", url: "https://tumourclassification.iarc.who.int",
    cite_par: [{ libelle: "Adénocarcinome acineux infiltrant du poumon", type: "phrase" }, { libelle: "CIM-O3 8551/3", type: "code" }],
  },
  bible_ihc_poumon: {
    titre: "Bible de la pathologiste · Biopsies thoraciques", description: "Fiches pratiques du service : immunohistochimie des proliférations tumorales thoraciques.",
    editeur: "Service d'anatomie et cytologie pathologiques", version: "Version interne 2025", fiabilite: "C",
    cite_par: [{ libelle: "Ki67 (% de cellules tumorales)", type: "champ" }],
  },
  acp_macro_biopsies: {
    titre: "Bible de la pathologiste · Biopsies thoraciques", description: "Pratique de description macroscopique et microscopique des biopsies thoraciques dans le service.",
    editeur: "Service d'anatomie et cytologie pathologiques", version: "Version interne 2025", fiabilite: "C",
    cite_par: [{ libelle: "Quatre fragments mesurant de 2 à 4 cm.", type: "phrase" }, { libelle: "Règle : unité des fragments biopsiques", type: "règle" }],
  },
};
export async function demoSource(ref: string): Promise<SourceDetail> {
  await attendre(250);
  const f = FICHES[ref];
  if (!f) throw new Error("Source introuvable");
  return normaliserDetail(f);
}
