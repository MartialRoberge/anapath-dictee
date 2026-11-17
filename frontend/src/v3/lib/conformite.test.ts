import { describe, expect, it } from "vitest";
import { blocages, sha256Hex, texteFinal } from "./conformite";
import { creerLocal, ignorerTrou } from "./session";
import type { Projet } from "../types";

const projet = {
  id: "p1", version: "3", titre: "T", dictee: { brute: "", corrigee: "" },
  contexte: { organes: [], organes_libelles: [], contexte_lesionnel: "indetermine", niveau_service: "N0" },
  corrections: [], sections: [{ id: "s", titre: "S", ordre: 0 }],
  elements: [
    { id: "e1", section_id: "s", type: "phrase", texte: "Phrase.", statut: "dicte", confiance: 1, niveau: "haute", sources: [], explication: "", obligatoire: false, options: [] },
    { id: "e2", section_id: "s", type: "trou", texte: "Grade", statut: "a_completer", confiance: 0.5, niveau: "basse", sources: [], explication: "", obligatoire: true, options: [] },
  ],
  alertes: [{ id: "a1", type: "manquant", gravite: "bloquant", message: "m", element_ids: [], confiance: 1, sources: [], agent: "x" }],
  codes: [], trace: [], metriques: { duree_totale_ms: 0, appels_llm: 0, tokens_entree: 0, tokens_sortie: 0, confiance_moyenne: 0 },
} as unknown as Projet;

describe("conformite", () => {
  it("empreinte SHA-256 connue", async () => {
    expect(await sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
  it("blocages : alerte bloquante et trou obligatoire ouverts", () => {
    const l = creerLocal(projet, "texte");
    expect(blocages(l)).toEqual({ alertes_bloquantes: 1, trous_obligatoires: 1 });
    expect(blocages(ignorerTrou(l, "e2")).trous_obligatoires).toBe(0);
  });
  it("le texte final change quand le praticien édite", () => {
    const l = creerLocal(projet, "texte");
    expect(texteFinal(l)).toContain("Phrase.");
  });
});
