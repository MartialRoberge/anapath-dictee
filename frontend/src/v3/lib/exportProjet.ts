// Projet « à jour » pour l'export : éditions du praticien appliquées, trous comblés convertis,
// trous ignorés retirés. Les trous restés ouverts restent des trous (jamais de valeur inventée).
import type { Element, Projet } from "../types";
import { libelleSansUnite, uniteDuTrou, valeurAvecUnite } from "./holes";
import { estTrou, etatTrou, titreAffiche, type ProjetLocal } from "./session";

export function projetPourExport(l: ProjetLocal): Projet {
  const elements: Element[] = [];
  for (const el of l.projet.elements) {
    if (estTrou(el)) {
      const etat = etatTrou(l, el);
      if (etat === "ignore") continue;
      if (etat === "rempli") {
        const v = valeurAvecUnite(l.fills[el.id] ?? "", uniteDuTrou(el));
        elements.push({ ...el, type: "phrase", statut: "normalise", niveau: "haute", confiance: 1, texte: `${libelleSansUnite(el.texte)} : ${v}`, options: [] });
        continue;
      }
    }
    elements.push(l.edits[el.id] !== undefined ? { ...el, texte: l.edits[el.id] } : el);
  }
  return { ...l.projet, titre: titreAffiche(l), elements };
}
