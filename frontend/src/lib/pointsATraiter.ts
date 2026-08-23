/**
 * Une seule file de points a traiter, quelle que soit leur origine.
 *
 * LE PROBLEME QUE CE FICHIER RESOUT
 *
 * Le praticien avait trois panneaux — propositions du college, champs
 * obligatoires manquants, alertes de coherence — qui demandaient tous le meme
 * geste : regarder, decider, avancer. Repartis a trois endroits, avec trois
 * vocabulaires et trois compteurs, ils ne donnaient AUCUN sentiment de
 * progression. On voyait des panneaux, jamais une tache qui se termine.
 *
 * Ici, tout devient un POINT A TRAITER. Une file, un compteur, et le compteur
 * descend. C'est la seule chose qui fait sentir qu'on avance.
 *
 * CE QUI EST UNIFIE, ET CE QUI NE L'EST PAS
 *
 * Unifie : la FORME. Trois verbes, toujours les memes, toujours au meme
 * endroit — accepter, modifier, ecarter.
 *
 * Pas unifie : le SENS. Chaque verbe s'enregistre dans la grille de decision de
 * son type, et ces grilles sont distinctes a dessein. "Je n'ai pas dit ca" sur
 * une proposition mesure une hallucination ; "pas pertinent" sur un champ
 * manquant mesure un faux positif de completude. Les confondre fausserait un
 * taux publie. Le praticien voit un geste simple, l'etude enregistre la mesure
 * exacte.
 */

import type { Marker } from "@/services/api";
import type { PropositionAffichee } from "@/services/etude";

/* ------------------------------------------------------------------ */
/*  Le point                                                           */
/* ------------------------------------------------------------------ */

export type OriginePoint =
  | "proposition"
  | "champ_manquant"
  | "code"
  | "coherence";

/** Le verbe que le praticien voit. Trois, jamais plus. */
export type Verbe = "accepter" | "modifier" | "ecarter";

export type Gravite = "haute" | "moyenne" | "basse";

export interface ActionPoint {
  verbe: Verbe;
  /** Ce que le bouton dit, dans le vocabulaire du point. */
  libelle: string;
  /**
   * La valeur enregistree dans la grille de l'etude. Elle differe du verbe :
   * c'est elle qui porte la mesure, et elle n'est jamais devinee a l'affichage.
   */
  decision: string;
  /** Le verbe ouvre une saisie : corriger un texte, completer un champ. */
  saisie?: boolean;
}

export interface PointATraiter {
  id: string;
  origine: OriginePoint;
  /** Ce qu'on demande, en une ligne, lisible sans contexte. */
  titre: string;
  /** Le texte concerne : l'assertion, le champ, le code. */
  detail: string;
  /**
   * POURQUOI ce point existe, dans les mots de qui l'a produit.
   *
   * Ces phrases ne sont jamais reformulees pour le praticien : ce sont celles
   * que les relecteurs ont ecrites en jugeant, ou l'enonce de la regle qui a
   * declenche l'alerte. Les reecrire reviendrait a GENERER l'explication d'une
   * decision au lieu de la CONSTATER — ce ne serait plus de l'explicabilite.
   */
  pourquoi: string[];
  /** Le passage de la dictee qui soutient le point, s'il existe. */
  citation: string | null;
  /** Offsets dans la transcription, pour le surlignage. */
  empan: { debut: number; fin: number } | null;
  gravite: Gravite;
  actions: ActionPoint[];
  /** Valeur courante d'un champ a completer. */
  valeur?: string;
  /** Decompte des voix du college, quand il y en a un. */
  voix?: { pour: number; total: number };
}

/* ------------------------------------------------------------------ */
/*  Les grilles, par origine                                           */
/* ------------------------------------------------------------------ */

/**
 * Les libelles viennent du protocole et ne s'improvisent pas.
 *
 * "Je n'ai pas dit ca" est volontairement brutal : c'est la reponse la plus
 * precieuse de l'etude, et une formulation polie ferait cliquer "conforme" par
 * courtoisie.
 */
const ACTIONS_PROPOSITION: ActionPoint[] = [
  { verbe: "accepter", libelle: "Conforme", decision: "conforme" },
  { verbe: "modifier", libelle: "À corriger", decision: "corrige", saisie: true },
  { verbe: "ecarter", libelle: "Je n'ai pas dit ça", decision: "non_dicte" },
  { verbe: "ecarter", libelle: "Hors sujet", decision: "hors_sujet" },
];

const ACTIONS_CODE: ActionPoint[] = [
  { verbe: "accepter", libelle: "Code juste", decision: "juste" },
  { verbe: "modifier", libelle: "Corriger le code", decision: "corrige", saisie: true },
  { verbe: "ecarter", libelle: "Je ne sais pas", decision: "je_ne_sais_pas" },
];

/**
 * "Pertinent, mais je ne le mets pas" n'est PAS un rejet : un praticien qui
 * juge la suggestion pertinente et choisit souverainement de ne pas l'ecrire
 * valide le systeme. Le confondre avec "pas pertinent" ferait passer un succes
 * pour un echec.
 */
const ACTIONS_CHAMP: ActionPoint[] = [
  { verbe: "accepter", libelle: "Compléter", decision: "pertinent_ajoute", saisie: true },
  {
    verbe: "modifier",
    libelle: "Pertinent, mais je ne le mets pas",
    decision: "pertinent_non_retenu",
  },
  { verbe: "ecarter", libelle: "Pas pertinent ici", decision: "non_pertinent" },
];

/**
 * Une alerte de coherence n'est pas une proposition : elle ne dit pas ce qui
 * est vrai, elle dit ce qui est INCOHERENT avec le reste du document. Elle ne
 * s'enregistre donc dans aucune grille de l'etude — d'ou la decision vide.
 */
const ACTIONS_COHERENCE: ActionPoint[] = [
  { verbe: "accepter", libelle: "C'est corrigé", decision: "" },
  { verbe: "ecarter", libelle: "Ce n'est pas une erreur", decision: "" },
];

/* ------------------------------------------------------------------ */
/*  Construction de la file                                            */
/* ------------------------------------------------------------------ */

const ORDRE_GRAVITE: Record<Gravite, number> = { haute: 0, moyenne: 1, basse: 2 };

/**
 * Une proposition sans empan n'est pas un surlignage rate : c'est une
 * assertion qu'AUCUN passage de la dictee ne soutient. La question posee change
 * alors de nature — non plus "est-ce fidele ?" mais "l'avez-vous dit ?" — et
 * c'est la mesure centrale de l'etude.
 */
function pointDeProposition(
  proposition: PropositionAffichee,
  justifications: string[],
  citation: string | null,
  voix: { pour: number; total: number } | undefined,
): PointATraiter {
  const ancree = proposition.empan_debut !== null && proposition.empan_fin !== null;
  const estCode = proposition.type === "code";
  const estChamp = proposition.type === "completude";

  return {
    id: proposition.id,
    origine: estCode ? "code" : estChamp ? "champ_manquant" : "proposition",
    titre: estCode
      ? "Code proposé"
      : estChamp
        ? "Information à compléter"
        : ancree
          ? "À vérifier dans votre dictée"
          : "L'avez-vous dit ?",
    detail: proposition.valeur_proposee,
    pourquoi: justifications,
    citation,
    empan: ancree
      ? { debut: proposition.empan_debut as number, fin: proposition.empan_fin as number }
      : null,
    gravite: !ancree && !estChamp ? "haute" : estCode ? "moyenne" : "basse",
    actions: estCode ? ACTIONS_CODE : estChamp ? ACTIONS_CHAMP : ACTIONS_PROPOSITION,
    voix,
  };
}

/**
 * Un champ obligatoire absent devient un point comme un autre — c'est tout
 * l'objet de ce fichier. Avant, il vivait dans un panneau separe ou l'on ne
 * pouvait que le LIRE : il fallait redicter pour le remplir.
 */
function pointDeMarqueur(marqueur: Marker): PointATraiter {
  return {
    id: `champ:${marqueur.rule_id}`,
    origine: "champ_manquant",
    titre: "Information à compléter",
    detail: marqueur.field,
    pourquoi: marqueur.message ? [marqueur.message] : [],
    citation: null,
    empan: null,
    gravite: marqueur.severity === "error" ? "moyenne" : "basse",
    actions: ACTIONS_CHAMP,
    valeur: marqueur.auto_filled ? marqueur.auto_filled_value : "",
  };
}

function pointDeCoherence(code: string, message: string, bloquant: boolean): PointATraiter {
  return {
    id: `coherence:${code}`,
    origine: "coherence",
    titre: "Incohérence dans le document",
    detail: message,
    // La regle EST l'explication : elle se cite, elle ne se reformule pas.
    pourquoi: [`Règle ${code}`],
    citation: null,
    empan: null,
    gravite: bloquant ? "haute" : "moyenne",
    actions: ACTIONS_COHERENCE,
  };
}

export interface SourcesPoints {
  propositions: PropositionAffichee[];
  /** Justifications par identifiant de proposition, telles qu'ecrites. */
  justifications: Record<string, string[]>;
  /** Extraits de dictee par identifiant de proposition. */
  citations: Record<string, string>;
  /** Decompte des voix du college, par identifiant de proposition. */
  voix: Record<string, { pour: number; total: number }>;
  marqueurs: Marker[];
  coherence: { code: string; message: string; severity: string }[];
}

/**
 * Assemble la file unique, la plus grave en premier.
 *
 * Les champs deja portes par une proposition ne sont pas repris depuis les
 * marqueurs : un meme champ signale par les deux sources ne doit faire qu'UN
 * point, sinon le praticien le traite deux fois et le compteur ment.
 */
export function construirePoints(sources: SourcesPoints): PointATraiter[] {
  const points = sources.propositions.map((proposition) =>
    pointDeProposition(
      proposition,
      sources.justifications[proposition.id] ?? [],
      sources.citations[proposition.id] ?? null,
      sources.voix[proposition.id],
    ),
  );

  const champsDejaPortes = new Set(
    points
      .filter((point) => point.origine === "champ_manquant")
      .map((point) => point.detail.toLowerCase().trim()),
  );

  for (const marqueur of sources.marqueurs) {
    if (champsDejaPortes.has(marqueur.field.toLowerCase().trim())) continue;
    points.push(pointDeMarqueur(marqueur));
  }

  for (const alerte of sources.coherence) {
    points.push(
      pointDeCoherence(alerte.code, alerte.message, alerte.severity === "bloquant"),
    );
  }

  return points.sort(
    (a, b) => ORDRE_GRAVITE[a.gravite] - ORDRE_GRAVITE[b.gravite],
  );
}

/** Ce qui reste a traiter, dans l'ordre. */
export function restants(
  points: PointATraiter[],
  traites: Readonly<Record<string, string>>,
): PointATraiter[] {
  return points.filter((point) => !(point.id in traites));
}
