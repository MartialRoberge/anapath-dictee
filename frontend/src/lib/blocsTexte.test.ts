/**
 * Le decoupage du compte rendu en surface de travail.
 *
 * Ce fichier tient la fondation : si le decoupage se trompe, le praticien
 * decide sur des fragments, l'explication designe la mauvaise phrase, et un
 * trou se remplit au mauvais endroit. Tout le reste de l'interface en depend.
 */

import { describe, expect, it } from "vitest";
import { decouperEnBlocs, remplirTrou, trousDe } from "./blocsTexte";
import type { PointATraiter } from "./pointsATraiter";

function point(detail: string, extra: Partial<PointATraiter> = {}): PointATraiter {
  return {
    id: `p-${detail.slice(0, 8)}`,
    origine: "proposition",
    titre: "À vérifier",
    detail,
    pourquoi: [],
    citation: "quelque chose de dicté",
    empan: null,
    gravite: "moyenne",
    actions: [],
    ...extra,
  };
}

describe("decoupage", () => {
  it("garde les en-tetes comme structure, jamais comme fait a decider", () => {
    const blocs = decouperEnBlocs({
      cr: "**Macroscopie :**\nTrois fragments bruns.",
      points: [],
    });
    expect(blocs[0].nature).toBe("libre");
    expect(blocs[0].sectionLibelle).toBe("Macroscopie");
    expect(blocs[1].nature).toBe("dicte");
    expect(blocs[1].sectionCle).toBe("macroscopie");
  });

  it("ne prend PAS une phrase courte pour un titre", () => {
    // Sans l'exigence de gras ou de diese, « Les limites sont saines » — courte
    // et sans ponctuation finale — passait pour un titre. La phrase
    // disparaissait alors du travail du praticien.
    const blocs = decouperEnBlocs({
      cr: "**Conclusion :**\nLes limites sont saines",
      points: [],
    });
    expect(blocs.filter((b) => b.nature === "libre")).toHaveLength(1);
    expect(blocs[1].texte).toContain("limites");
  });

  it("ne soumet pas une ligne de tableau", () => {
    const blocs = decouperEnBlocs({
      cr: "**IHC :**\n| Anticorps | Résultat |\n| TTF1 | Positif |",
      points: [],
    });
    expect(blocs.every((b) => b.nature === "libre")).toBe(true);
  });

  it("rattache un point a la phrase qu'il vise", () => {
    const blocs = decouperEnBlocs({
      cr: "**Microscopie :**\nLa tumeur infiltre le parenchyme.",
      points: [point("La tumeur infiltre le parenchyme")],
    });
    const vise = blocs.find((b) => b.point !== null);
    expect(vise?.nature).toBe("propose");
  });

  it("peint en « a verifier » une phrase que rien ne soutient", () => {
    const blocs = decouperEnBlocs({
      cr: "**Microscopie :**\nAucun embole vasculaire.",
      points: [point("Aucun embole vasculaire", { citation: null })],
    });
    expect(blocs.find((b) => b.point !== null)?.nature).toBe("verifier");
  });

  it("laisse une phrase trouee en « dicte »", () => {
    // C'est la VALEUR qui manque, pas la phrase. La peindre comme suspecte
    // ferait douter d'un enonce du praticien.
    const blocs = decouperEnBlocs({
      cr: "**Macroscopie :**\nLa lésion mesure [A COMPLETER: taille].",
      points: [],
    });
    const troue = blocs.find((b) => b.trous.length > 0);
    expect(troue?.nature).toBe("dicte");
    expect(troue?.trous[0].champ).toBe("taille");
  });
});

describe("trous", () => {
  it("recupere le declencheur, la raison et les options", () => {
    const [trou] = trousDe("Grade : [A COMPLETER: grade de dysplasie].", () => ({
      declencheur: "adénome tubuleux",
      raison: "Un adénome se grade toujours.",
      options: ["bas grade", "haut grade"],
    }));
    expect(trou.declencheur).toBe("adénome tubuleux");
    expect(trou.options).toEqual(["bas grade", "haut grade"]);
  });

  it("laisse les options vides quand rien ne les renseigne", () => {
    const [trou] = trousDe("Taille : [A COMPLETER: taille].");
    expect(trou.options).toEqual([]);
    expect(trou.raison).toBeNull();
  });
});

describe("remplissage", () => {
  const cr =
    "**Macroscopie :**\nFragment A : [A COMPLETER: taille].\nFragment B : [A COMPLETER: taille].";

  it("remplit le bon trou quand deux champs portent le meme nom", () => {
    // LE PIEGE. Un remplacement par recherche de chaine remplirait le premier
    // a la place du second, sans que rien ne le signale.
    const blocs = decouperEnBlocs({ cr, points: [] });
    const troues = blocs.filter((b) => b.trous.length > 0);
    expect(troues).toHaveLength(2);

    const apres = remplirTrou(cr, troues[1], troues[1].trous[0], "4 mm");
    expect(apres).toContain("Fragment A : [A COMPLETER: taille]");
    expect(apres).toContain("Fragment B : 4 mm");
  });

  it("ne touche a rien si le compte rendu a bouge depuis le decoupage", () => {
    const blocs = decouperEnBlocs({ cr, points: [] });
    const troue = blocs.filter((b) => b.trous.length > 0)[0];
    const modifie = "Texte entierement different, sans aucun marqueur.";
    expect(remplirTrou(modifie, troue, troue.trous[0], "4 mm")).toBe(modifie);
  });
});
