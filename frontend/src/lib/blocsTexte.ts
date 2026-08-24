/**
 * Le compte rendu decoupe en blocs de travail.
 *
 * LE COMPTE RENDU EST LA SURFACE DE TRAVAIL, pas un resultat qu'on relit.
 * Tout se decide dedans : accepter, refuser, remplir un trou, choisir dans une
 * liste. Le panneau d'analyse, a cote, est PUREMENT CONSULTATIF — il dit
 * pourquoi une chose est la, jamais quoi en faire.
 *
 * La raison est simple : decider a gauche ce qu'on lit a droite oblige a tenir
 * les deux en tete pendant l'aller-retour, et c'est exactement pendant cet
 * aller-retour qu'on accepte sans relire.
 *
 * QUATRE NATURES, ET PAS UNE DE PLUS
 *
 * `dicte`     — le praticien l'a dit. Grave dans le marbre : rien a decider.
 * `propose`   — strictement implique par ce qu'il a dit. A valider ou refuser.
 * `verifier`  — quelque chose ne s'appuie sur rien de dicte. A regarder.
 * `libre`     — du texte de structure : un titre, une transition. Pas un fait.
 *
 * Un TROU n'est pas une nature : c'est un manque A L'INTERIEUR d'un bloc. Une
 * phrase peut etre dictee et porter un trou (« la lesion mesure [A COMPLETER:
 * taille] »). En faire une nature obligerait a couper la phrase en deux, et le
 * praticien lirait un fragment sans son verbe.
 */

import type { PointATraiter } from "@/lib/pointsATraiter";

/* ------------------------------------------------------------------ */
/*  Le modele                                                          */
/* ------------------------------------------------------------------ */

export type NatureBloc = "dicte" | "propose" | "verifier" | "libre";

/** Un manque, a l'interieur d'un bloc. */
export interface Trou {
  /** Position dans le texte DU BLOC, pas du compte rendu. */
  debut: number;
  fin: number;
  /** Le champ demande, tel qu'il est ecrit dans le marqueur. */
  champ: string;
  /**
   * La phrase DICTEE qui rend ce champ attendu, recopiee sans reformulation.
   * C'est elle qui repond a « pourquoi tu me demandes ca ».
   */
  declencheur: string | null;
  raison: string | null;
  /**
   * La liste FERMEE des valeurs possibles. VIDE quand le champ est une mesure,
   * un compte ou un texte libre : le praticien ecrit ce qu'il veut, et il le
   * sait. Une liste inventee serait pire que pas de liste — on choisit dedans
   * sans la remettre en cause.
   */
  options: readonly string[];
  /**
   * LA REGLE METIER qui rend ce champ attendu, et sa SOURCE nommee.
   *
   * C'est la difference entre « il figure ça » et « selon la classification
   * OMS 2022 / les donnees minimales INCa ». Un praticien ne change pas sa
   * pratique parce qu'un logiciel le lui demande ; il la change parce qu'une
   * reference qu'il connait le dit. Sans la source nommee, l'explicabilite
   * n'apporte rien a sa decision.
   *
   * Ces phrases viennent d'une base de connaissances ecrite a la main, jamais
   * du modele : une source generee serait une source inventee.
   */
  norme: string | null;
  /** Ce que ce champ conditionne en pratique. */
  enjeu: string | null;
  /** Ce qui se passe s'il manque. */
  risque: string | null;
}

export interface Bloc {
  id: string;
  /**
   * Le bloc est un element de liste. La puce est RETIREE du texte et rendue a
   * part : la garder dans le texte l'affichait telle quelle (« - Trois
   * fragments ») puisque le rendu Markdown est neutralise en ligne, et le
   * compte rendu perdait ses listes.
   */
  puce: boolean;
  /** Offsets dans le compte rendu complet : c'est lui la source de verite. */
  debut: number;
  fin: number;
  texte: string;
  nature: NatureBloc;
  sectionCle: string;
  sectionLibelle: string;
  /** Le point d'etude rattache, quand ce bloc en porte un. */
  point: PointATraiter | null;
  trous: readonly Trou[];
}

/* ------------------------------------------------------------------ */
/*  Decoupage                                                          */
/* ------------------------------------------------------------------ */

/** `**Microscopie :**`, `**__CONCLUSION :__**`, `### 2) Curage`... */
const ENTETE =
  /^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:__)?\s*([^\n*_|]{2,60}?)\s*:?\s*(?:__)?(?:\*\*)?\s*:?\s*$/;

/** Le marqueur de trou, tel que le moteur l'ecrit. */
const MARQUEUR_TROU = /\[A COMPLETER\s*:\s*([^\]]+)\]/gi;

/** Une ligne de tableau Markdown. Elle se lit, elle ne se decide pas. */
const LIGNE_TABLEAU = /^\s*\|/;

/** Une puce ou une numerotation en debut de ligne. */
const MARQUEUR_LISTE = /^\s*(?:[-*+]|\d+[.)])\s+/;

function cleDeSection(libelle: string): string {
  return libelle
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Une ligne est-elle un en-tete de section ?
 *
 * On exige le gras ou le diese. Sans cette exigence, « Les limites sont
 * saines » — courte, sans ponctuation finale — passerait pour un titre, et la
 * phrase disparaitrait du travail du praticien.
 */
function estEntete(ligne: string): boolean {
  const nettoye = ligne.trim();
  if (nettoye === "") return false;
  if (LIGNE_TABLEAU.test(nettoye)) return false;
  const marque =
    nettoye.startsWith("#") || nettoye.startsWith("**") || nettoye.startsWith("__");
  return marque && ENTETE.test(nettoye);
}

function libelleDEntete(ligne: string): string {
  const trouve = ENTETE.exec(ligne.trim());
  return (trouve?.[1] ?? ligne).trim();
}

/** Extrait les trous d'un texte de bloc, positions relatives au bloc. */
export function trousDe(
  texteBloc: string,
  renseigner?: (champ: string) => Omit<Trou, "debut" | "fin" | "champ"> | undefined,
): Trou[] {
  const trous: Trou[] = [];
  MARQUEUR_TROU.lastIndex = 0;
  for (const trouve of texteBloc.matchAll(MARQUEUR_TROU)) {
    const champ = trouve[1].trim();
    if (champ === "" || trouve.index === undefined) continue;
    const complement = renseigner?.(champ);
    trous.push({
      debut: trouve.index,
      fin: trouve.index + trouve[0].length,
      champ,
      declencheur: complement?.declencheur ?? null,
      raison: complement?.raison ?? null,
      options: complement?.options ?? [],
      norme: complement?.norme ?? null,
      enjeu: complement?.enjeu ?? null,
      risque: complement?.risque ?? null,
    });
  }
  return trous;
}

export interface EntreeDecoupage {
  /** Le compte rendu complet, en Markdown. */
  cr: string;
  /** Les points d'etude, a rattacher aux blocs qu'ils visent. */
  points: readonly PointATraiter[];
  /** Complement d'un trou : declencheur, raison, options. */
  renseignerTrou?: (
    champ: string,
  ) => Omit<Trou, "debut" | "fin" | "champ"> | undefined;
}

/**
 * Coupe le compte rendu en blocs, dans l'ordre du document.
 *
 * LE DECOUPAGE EST FAIT ICI ET NULLE PART AILLEURS. Le panneau d'analyse
 * consomme ces memes blocs : deux decoupages differeraient des la premiere
 * phrase inhabituelle, et l'explication cesserait de designer le passage
 * qu'elle pretend expliquer.
 */
export function decouperEnBlocs({
  cr,
  points,
  renseignerTrou,
}: EntreeDecoupage): Bloc[] {
  const blocs: Bloc[] = [];
  if (cr.trim() === "") return blocs;

  const parTexte = new Map<string, PointATraiter>();
  for (const point of points) {
    const cle = normaliser(point.detail);
    if (cle !== "" && !parTexte.has(cle)) parTexte.set(cle, point);
  }

  let sectionCle = "document";
  let sectionLibelle = "Document";
  let curseur = 0;

  const lignes = cr.split("\n");
  for (let rang = 0; rang < lignes.length; rang += 1) {
    const ligne = lignes[rang];
    const debutLigne = curseur;
    curseur += ligne.length + 1; // +1 pour le \n retire par le split

    if (ligne.trim() === "") continue;

    // UN TABLEAU SE LIT D'UN SEUL TENANT. Le couper ligne par ligne le
    // detruisait a l'affichage : chaque ligne devenait un paragraphe avec ses
    // barres verticales apparentes, au lieu d'un tableau.
    if (LIGNE_TABLEAU.test(ligne)) {
      let fin = rang;
      while (fin + 1 < lignes.length && LIGNE_TABLEAU.test(lignes[fin + 1])) {
        fin += 1;
        curseur += lignes[fin].length + 1;
      }
      const tableau = lignes.slice(rang, fin + 1).join("\n");
      blocs.push(
        construire(tableau, debutLigne, sectionCle, sectionLibelle, "libre", null, []),
      );
      rang = fin;
      continue;
    }

    if (estEntete(ligne)) {
      sectionLibelle = libelleDEntete(ligne);
      sectionCle = cleDeSection(sectionLibelle) || "document";
      blocs.push(
        construire(ligne, debutLigne, sectionCle, sectionLibelle, "libre", null, []),
      );
      continue;
    }

    const listeTrouvee = MARQUEUR_LISTE.exec(ligne);
    if (listeTrouvee !== null) {
      const decalage = listeTrouvee[0].length;
      const contenu = ligne.slice(decalage);
      const point = parTexte.get(normaliser(contenu)) ?? null;
      const trous = trousDe(contenu, renseignerTrou);
      blocs.push(
        construire(
          contenu,
          debutLigne + decalage,
          sectionCle,
          sectionLibelle,
          natureDe(point),
          point,
          trous,
          true,
        ),
      );
      continue;
    }

    for (const phrase of phrasesDe(ligne)) {
      const point = parTexte.get(normaliser(phrase.texte)) ?? null;
      const trous = trousDe(phrase.texte, renseignerTrou);
      blocs.push(
        construire(
          phrase.texte,
          debutLigne + phrase.decalage,
          sectionCle,
          sectionLibelle,
          natureDe(point),
          point,
          trous,
        ),
      );
    }
  }

  return blocs;
}

/**
 * La nature d'un bloc se DEDUIT, elle ne se devine pas.
 *
 * Un bloc sans point rattache est dicte : le college ne l'a pas retenu, donc
 * rien ne lui est reproche. C'est le cas de loin le plus frequent, et c'est
 * pour cela qu'il doit etre le plus discret a l'ecran.
 */
function natureDe(point: PointATraiter | null): NatureBloc {
  // Un trou ne change PAS la nature du bloc. « La lesion mesure [A COMPLETER:
  // taille] » reste une phrase dictee : c'est la valeur qui manque, pas la
  // phrase. La peindre comme suspecte ferait douter d'un enonce du praticien.
  if (point === null) return "dicte";
  if (point.citation === null && point.origine === "proposition") return "verifier";
  if (point.gravite === "haute") return "verifier";
  return "propose";
}

function construire(
  texte: string,
  debut: number,
  sectionCle: string,
  sectionLibelle: string,
  nature: NatureBloc,
  point: PointATraiter | null,
  trous: readonly Trou[],
  puce = false,
): Bloc {
  return {
    id: `bloc:${debut}`,
    puce,
    debut,
    fin: debut + texte.length,
    texte,
    nature,
    sectionCle,
    sectionLibelle,
    point,
    trous,
  };
}

/** Coupe une ligne en phrases, en gardant les abreviations intactes. */
function phrasesDe(ligne: string): { texte: string; decalage: number }[] {
  const morceaux: { texte: string; decalage: number }[] = [];
  const separateur = /(?<![A-Z])\.(?=\s+[A-ZÀ-Ý])|(?<=\.)\s+(?=[A-ZÀ-Ý])/g;

  let debut = 0;
  for (const coupure of ligne.matchAll(separateur)) {
    if (coupure.index === undefined) continue;
    const fin = coupure.index + coupure[0].length;
    const texte = ligne.slice(debut, fin);
    if (texte.trim() !== "") morceaux.push({ texte, decalage: debut });
    debut = fin;
  }
  const reste = ligne.slice(debut);
  if (reste.trim() !== "") morceaux.push({ texte: reste, decalage: debut });
  return morceaux.length > 0 ? morceaux : [{ texte: ligne, decalage: 0 }];
}

function normaliser(texte: string): string {
  return texte
    .replace(/\[A COMPLETER\s*:[^\]]*\]/gi, " ")
    .replace(/[*_|#>]/g, " ")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/* ------------------------------------------------------------------ */
/*  Remplir un trou                                                    */
/* ------------------------------------------------------------------ */

/**
 * Remplace le texte d'un bloc, DANS LE COMPTE RENDU COMPLET.
 *
 * Comme pour un trou, on travaille sur les offsets absolus et jamais par
 * recherche de chaine : deux phrases identiques dans deux sections differentes
 * (« Les limites sont saines. ») feraient remplacer la premiere a la place de
 * la seconde, sans que rien ne le signale.
 *
 * Le garde-fou compare le texte attendu a ce que le compte rendu porte
 * reellement a ces offsets : si le texte a bouge depuis le decoupage, on ne
 * touche a rien plutot que d'ecraser une phrase au hasard.
 */
export function remplacerTexteDuBloc(
  cr: string,
  bloc: Bloc,
  texte: string,
): string {
  if (cr.slice(bloc.debut, bloc.fin) !== bloc.texte) return cr;
  return cr.slice(0, bloc.debut) + texte + cr.slice(bloc.fin);
}

/**
 * Remplace un trou par la valeur retenue, DANS LE COMPTE RENDU COMPLET.
 *
 * On travaille sur les offsets absolus et jamais par recherche de texte : deux
 * trous peuvent demander le meme champ (« [A COMPLETER: taille] » sur deux
 * prelevements), et un remplacement par chaine remplirait le premier a la
 * place du second sans que rien ne le signale.
 */
export function remplirTrou(
  cr: string,
  bloc: Bloc,
  trou: Trou,
  valeur: string,
): string {
  const debut = bloc.debut + trou.debut;
  const fin = bloc.debut + trou.fin;
  // Garde-fou : si les offsets ne designent plus le marqueur, le compte rendu
  // a bouge depuis le decoupage. On ne touche a rien plutot que d'ecraser une
  // phrase au hasard.
  if (!/^\[A COMPLETER\s*:/i.test(cr.slice(debut, fin))) return cr;
  return cr.slice(0, debut) + valeur + cr.slice(fin);
}
