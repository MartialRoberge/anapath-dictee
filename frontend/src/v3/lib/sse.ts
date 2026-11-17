// Lecture du flux SSE (fetch + ReadableStream). Pur et testable : le parseur est incrémental
// et tolère les découpages arbitraires des chunks réseau.
import type { ProjetEvent, TraceStep, Projet, Element } from "../types";

export interface SseMessage { event: string; data: string }

/** Parseur SSE incrémental (spec WHATWG : champs event/data, commentaires ':', fin de bloc = ligne vide). */
export function creerParseurSse(onMessage: (m: SseMessage) => void) {
  let tampon = "";
  let event = "";
  let donnees: string[] = [];

  const traiterLigne = (ligne: string) => {
    if (ligne === "") {
      if (donnees.length > 0) onMessage({ event: event || "message", data: donnees.join("\n") });
      event = "";
      donnees = [];
      return;
    }
    if (ligne.startsWith(":")) return; // commentaire / keep-alive
    const i = ligne.indexOf(":");
    const champ = i === -1 ? ligne : ligne.slice(0, i);
    let valeur = i === -1 ? "" : ligne.slice(i + 1);
    if (valeur.startsWith(" ")) valeur = valeur.slice(1);
    if (champ === "event") event = valeur;
    else if (champ === "data") donnees.push(valeur);
  };

  return {
    push(chunk: string) {
      tampon += chunk;
      const lignes = tampon.split(/\r\n|\n|\r/);
      // un \r final peut précéder un \n du chunk suivant : on garde la dernière ligne en tampon
      tampon = lignes.pop() ?? "";
      lignes.forEach(traiterLigne);
    },
    /** Fin de flux : traite le reste du tampon et un éventuel bloc non terminé. */
    flush() {
      if (tampon) traiterLigne(tampon);
      tampon = "";
      traiterLigne("");
    },
  };
}

/** Complète un Projet partiel (backend en évolution) sans jamais inventer de contenu. */
export function normaliserProjet(p: Partial<Projet> & { id: string }): Projet {
  return {
    id: p.id,
    version: "3",
    titre: p.titre ?? "Projet de compte rendu",
    dictee: p.dictee ?? { brute: "", corrigee: "" },
    contexte: p.contexte ?? { organes: [], organes_libelles: [], contexte_lesionnel: "indetermine", niveau_service: "N0" },
    corrections: p.corrections ?? [],
    sections: p.sections ?? [],
    elements: (p.elements ?? []).map(normaliserElement),
    alertes: p.alertes ?? [],
    codes: p.codes ?? [],
    trace: p.trace ?? [],
    metriques: p.metriques ?? { duree_totale_ms: 0, appels_llm: 0, tokens_entree: 0, tokens_sortie: 0, confiance_moyenne: 0 },
  };
}

export function normaliserElement(e: Element): Element {
  return { ...e, sources: e.sources ?? [], options: e.options ?? [], explication: e.explication ?? "", obligatoire: !!e.obligatoire };
}

const estObjet = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

/** Message SSE -> évènement typé. Retourne null pour un évènement ignorable (ping, inconnu, illisible). */
export function decoderEvenement(m: SseMessage): ProjetEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(m.data);
  } catch {
    return m.event === "projet"
      ? { event: "error", data: { message: "La réponse du serveur est illisible.", recuperable: true } }
      : null;
  }
  if (!estObjet(data)) return null;
  switch (m.event) {
    case "step":
      if (typeof data.id === "string" && typeof data.titre === "string" && typeof data.statut === "string") {
        const s = data as unknown as TraceStep;
        return { event: "step", data: { ...s, details: s.details ?? [], resume: s.resume ?? "", debut_ms: s.debut_ms ?? 0 } };
      }
      return null;
    case "partial":
      return Array.isArray(data.elements)
        ? { event: "partial", data: { elements: (data.elements as Element[]).map(normaliserElement) } }
        : null;
    case "projet":
      return typeof data.id === "string" && Array.isArray(data.elements)
        ? { event: "projet", data: normaliserProjet(data as unknown as Projet) }
        : { event: "error", data: { message: "Le projet reçu est incomplet.", recuperable: true } };
    case "error":
      return { event: "error", data: { message: typeof data.message === "string" ? data.message : "Erreur du service.", recuperable: data.recuperable !== false } };
    default:
      return null;
  }
}

/** Lit un Response SSE jusqu'à la fin ; appelle onEvent pour chaque évènement décodé. */
export async function lireFluxSse(res: Response, onEvent: (e: ProjetEvent) => void, signal?: AbortSignal): Promise<void> {
  if (!res.body) throw new Error("Flux indisponible.");
  const lecteur = res.body.getReader();
  const decodeur = new TextDecoder("utf-8");
  const parseur = creerParseurSse((m) => {
    const e = decoderEvenement(m);
    if (e) onEvent(e);
  });
  try {
    for (;;) {
      if (signal?.aborted) break;
      const { done, value } = await lecteur.read();
      if (done) break;
      parseur.push(decodeur.decode(value, { stream: true }));
    }
    parseur.push(decodeur.decode());
    parseur.flush();
  } finally {
    lecteur.releaseLock?.();
  }
}
