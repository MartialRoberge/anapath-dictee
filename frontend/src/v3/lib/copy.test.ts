import { describe, expect, it } from "vitest";
import { htmlPourCopie, texteProprePourCopie } from "./copy";
import { projetPoumon } from "../fixtures/projetPoumon";
import { caracteresModifies, creerLocal, decisionCorrection, decider, editerElement, ignorerTrou, remplirTrou, tranche, trouSuivant, trousOuverts, alertesOuvertes, fusionnerIteration } from "./session";
import { projetPourExport } from "./exportProjet";

const base = () => creerLocal(structuredClone(projetPoumon), "texte");

describe("copie du texte propre", () => {
  it("sans markdown, sections en majuscules, trous ouverts explicites", () => {
    const t = texteProprePourCopie(base());
    expect(t.startsWith("EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES BRONCHIQUES")).toBe(true);
    expect(t).toContain("MACROSCOPIE\nQuatre fragments mesurant de 2 à 4 cm.");
    expect(t).toContain("[PD-L1 : à compléter]");
    expect(t).not.toMatch(/[*_`#]/);
  });
  it("trou comblé : valeur et unité ; trou ignoré : retiré ; édition prise en compte", () => {
    let l = base();
    l = remplirTrou(l, "e9", "60");
    l = ignorerTrou(l, "e10");
    l = editerElement(l, "e2", "Quatre fragments mesurant de 2 à 4 mm.");
    const t = texteProprePourCopie(l);
    expect(t).toContain("PD-L1 : 60 %");
    expect(t).not.toContain("Biologie moléculaire");
    expect(t).toContain("de 2 à 4 mm.");
    expect(trousOuverts(l)).toBe(0);
  });
  it("HTML riche : surligne les trous ouverts et échappe", () => {
    const h = htmlPourCopie(editerElement(base(), "e5", "A < B & C"));
    expect(h).toContain("background:#FFF2CC");
    expect(h).toContain("A &lt; B &amp; C");
    expect(h).toContain("<h2");
  });
});

describe("état local", () => {
  it("Tab : prochain trou depuis un trou ou depuis rien", () => {
    const l = base();
    expect(trouSuivant(l, null)).toBe("e9");
    expect(trouSuivant(l, "e9")).toBe("e10");
    expect(trouSuivant(remplirTrou(l, "e10", "Demandée"), "e9")).toBeNull();
  });
  it("alertes ouvertes selon décisions", () => {
    const l = base();
    expect(alertesOuvertes(l)).toHaveLength(5);
    expect(alertesOuvertes(decider(l, "a1", "resolue"))).toHaveLength(4);
  });
  it("décision de correction : remplace le terme dans le texte et reste réversible", () => {
    let l = base();
    l = decisionCorrection(l, "c3", "original"); // rejette P40 -> « P quarante »
    expect(l.edits["e8"]).toBe("P quarante négatif.");
    l = decisionCorrection(l, "c3", "P63");
    expect(l.edits["e8"]).toBe("P63 négatif.");
    l = decisionCorrection(l, "c3", "P40");
    expect(l.edits["e8"]).toBe("P40 négatif.");
  });
  it("export : trou comblé devient phrase, ignoré retiré, ouvert conservé", () => {
    const l = remplirTrou(ignorerTrou(base(), "e10"), "e9", "60");
    const p = projetPourExport(l);
    expect(p.elements.find((e) => e.id === "e9")).toMatchObject({ type: "phrase", texte: "PD-L1 : 60 %" });
    expect(p.elements.find((e) => e.id === "e10")).toBeUndefined();
    expect(projetPourExport(base()).elements.find((e) => e.id === "e9")?.type).toBe("trou");
  });
  it("fusion d'itération : garde les décisions encore valides", () => {
    let l = decider(editerElement(remplirTrou(base(), "e10", "Demandée"), "e2", "x"), "a1", "resolue");
    const nouveau = structuredClone(projetPoumon);
    nouveau.alertes = nouveau.alertes.filter((a) => a.id !== "a1");
    const f = fusionnerIteration(l, nouveau);
    expect(f.edits.e2).toBe("x");
    expect(f.fills.e10).toBe("Demandée");
    expect(f.alertes.a1).toBeUndefined();
    l = f;
  });
  it("tranches et caractères modifiés (jamais le texte)", () => {
    expect(tranche(0)).toBe("0");
    expect(tranche(12)).toBe("11-50");
    expect(tranche(500)).toBe("200+");
    expect(caracteresModifies("de 2 à 4 cm", "de 2 à 4 mm")).toBe(1);
    expect(caracteresModifies("abc", "abc")).toBe(0);
  });
});
