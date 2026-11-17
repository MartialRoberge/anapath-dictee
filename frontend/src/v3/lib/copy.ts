// Copie du projet : texte propre (sans markdown) + HTML riche collable dans Word.
import type { Element } from "../types";
import { libelleSansUnite, uniteDuTrou, valeurAvecUnite } from "./holes";
import { estTrou, etatTrou, ordreDocument, texteElement, titreAffiche, type ProjetLocal } from "./session";

/** Ligne de texte d'un élément pour la copie ; null = rien à écrire (trou ignoré). */
export function ligneElement(l: ProjetLocal, el: Element): { texte: string; trouOuvert: boolean } | null {
  if (estTrou(el)) {
    const etat = etatTrou(l, el);
    if (etat === "ignore") return null;
    const label = libelleSansUnite(el.texte);
    if (etat === "ouvert") return { texte: `[${label} : à compléter]`, trouOuvert: true };
    const v = valeurAvecUnite(l.fills[el.id] ?? "", uniteDuTrou(el));
    return { texte: `${label} : ${v}`, trouOuvert: false };
  }
  return { texte: texteElement(l, el).trim(), trouOuvert: false };
}

const retirerMarkdown = (s: string) => s.replace(/[*_`#]+/g, "").replace(/^\s*[-•]\s+/, "");

/** Texte propre, sans markdown : titre, puis sections en majuscules et leurs lignes. */
export function texteProprePourCopie(l: ProjetLocal): string {
  const blocs: string[] = [titreAffiche(l).trim()];
  for (const { section, elements } of ordreDocument(l.projet)) {
    const lignes: string[] = [];
    for (const el of elements) {
      const lig = ligneElement(l, el);
      if (!lig || !lig.texte) continue;
      const t = retirerMarkdown(lig.texte);
      lignes.push(el.type === "liste" ? `– ${t}` : t);
    }
    if (lignes.length) blocs.push(`${section.titre.toUpperCase()}\n${lignes.join("\n")}`);
  }
  return blocs.join("\n\n");
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** HTML riche : styles en ligne (Word ignore les feuilles de style externes). Trous ouverts surlignés. */
export function htmlPourCopie(l: ProjetLocal): string {
  const parts: string[] = [`<h1 style="font-family:Calibri,Arial,sans-serif;font-size:14pt;font-weight:bold;text-align:center">${esc(titreAffiche(l).trim())}</h1>`];
  for (const { section, elements } of ordreDocument(l.projet)) {
    const items: string[] = [];
    let liste: string[] = [];
    const fermerListe = () => {
      if (liste.length) items.push(`<ul>${liste.join("")}</ul>`);
      liste = [];
    };
    for (const el of elements) {
      const lig = ligneElement(l, el);
      if (!lig || !lig.texte) continue;
      const t = retirerMarkdown(lig.texte);
      const contenu = lig.trouOuvert ? `<span style="background:#FFF2CC">${esc(t)}</span>` : esc(t);
      if (el.type === "liste") liste.push(`<li>${contenu}</li>`);
      else {
        fermerListe();
        items.push(el.type === "titre" ? `<p><b>${contenu}</b></p>` : `<p style="margin:0 0 4pt">${contenu}</p>`);
      }
    }
    fermerListe();
    if (items.length) parts.push(`<h2 style="font-family:Calibri,Arial,sans-serif;font-size:11pt;font-weight:bold;text-transform:uppercase;margin:12pt 0 4pt">${esc(section.titre)}</h2>${items.join("")}`);
  }
  return `<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">${parts.join("")}</div>`;
}

/** Copie texte + HTML dans le presse-papiers ; repli sur writeText. Retourne true si réussi. */
export async function copierProjet(l: ProjetLocal): Promise<boolean> {
  const texte = texteProprePourCopie(l);
  const html = htmlPourCopie(l);
  try {
    if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({ "text/plain": new Blob([texte], { type: "text/plain" }), "text/html": new Blob([html], { type: "text/html" }) }),
      ]);
      return true;
    }
    await navigator.clipboard.writeText(texte);
    return true;
  } catch {
    try {
      await navigator.clipboard.writeText(texte);
      return true;
    } catch {
      return false;
    }
  }
}

export async function copierTexte(texte: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(texte);
    return true;
  } catch {
    return false;
  }
}
