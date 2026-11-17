import { describe, expect, it } from "vitest";
import { filtrerOptions, libelleSansUnite, prochainTrou, uniteDuTrou, valeurAvecUnite } from "./holes";
import { segmenter } from "./segments";

describe("trous", () => {
  it("libellé et unité", () => {
    expect(libelleSansUnite("Taille tumorale (mm)")).toBe("Taille tumorale");
    expect(uniteDuTrou({ texte: "Taille tumorale (mm)" })).toBe("mm");
    expect(uniteDuTrou({ texte: "PD-L1 (% de cellules tumorales)" })).toBeNull();
    expect(uniteDuTrou({ texte: "PD-L1 (% de cellules tumorales)", unite: "%" })).toBe("%");
  });
  it("l'unité n'est ajoutée qu'à un nombre nu", () => {
    expect(valeurAvecUnite("24", "mm")).toBe("24 mm");
    expect(valeurAvecUnite("2,5", "mm")).toBe("2,5 mm");
    expect(valeurAvecUnite("≥ 50", "%")).toBe("≥ 50 %");
    expect(valeurAvecUnite("Non réalisé", "%")).toBe("Non réalisé");
  });
  it("filtre d'options sans accents", () => {
    expect(filtrerOptions(["Demandée", "Non demandée"], "demande")).toHaveLength(2);
    expect(filtrerOptions(["Demandée", "Non demandée"], "non")).toEqual(["Non demandée"]);
  });
});

describe("navigation Tab entre trous", () => {
  const ordre = [{ id: "a", ouvert: true }, { id: "b", ouvert: false }, { id: "c", ouvert: true }];
  it("avance au prochain trou ouvert en sautant les résolus", () => {
    expect(prochainTrou(ordre, null)).toBe("a");
    expect(prochainTrou(ordre, "a")).toBe("c");
    expect(prochainTrou(ordre, "c")).toBeNull();
  });
  it("recule avec Maj+Tab", () => {
    expect(prochainTrou(ordre, "c", -1)).toBe("a");
    expect(prochainTrou(ordre, "a", -1)).toBeNull();
    expect(prochainTrou(ordre, null, -1)).toBe("c");
  });
  it("repart de la position d'un trou tout juste résolu", () => {
    expect(prochainTrou([{ id: "a", ouvert: false }, { id: "b", ouvert: true }], "a")).toBe("b");
    expect(prochainTrou([], "a")).toBeNull();
  });
});

describe("segments surlignés", () => {
  it("découpe et ignore les bornes invalides ou chevauchantes", () => {
    const s = segmenter("abcdefghij", [{ debut: 2, fin: 4, cle: "x" }, { debut: 3, fin: 6, cle: "chev" }, { debut: 8, fin: 99, cle: "hors" }, { debut: 6, fin: 8, cle: "y" }]);
    expect(s.map((x) => [x.texte, x.cle])).toEqual([["ab", undefined], ["cd", "x"], ["ef", undefined], ["gh", "y"], ["ij", undefined]]);
  });
});
