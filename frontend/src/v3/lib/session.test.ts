import { describe, expect, it } from "vitest";
import { projetPoumon } from "../fixtures/projetPoumon";
import { alertesOuvertes, creerLocal, ignorerTrou, remplirTrou, rouvrirTrou } from "./session";

describe("alertes « champ manquant » liées aux trous", () => {
  const base = () => creerLocal(projetPoumon, "texte");
  it("remplir le trou règle l'alerte manquante qui le porte, pas les autres", () => {
    const l = remplirTrou(base(), "e9", "60 %");
    expect(alertesOuvertes(l).some((a) => a.id === "a1")).toBe(false);
    expect(alertesOuvertes(l).some((a) => a.type !== "manquant")).toBe(true);
  });
  it("ignorer un trou laisse l'alerte ouverte", () => {
    expect(alertesOuvertes(ignorerTrou(base(), "e9")).some((a) => a.id === "a1")).toBe(true);
  });
  it("rouvrir le trou rouvre l'alerte", () => {
    const l = rouvrirTrou(remplirTrou(base(), "e9", "60 %"), "e9");
    expect(alertesOuvertes(l).some((a) => a.id === "a1")).toBe(true);
  });
});
