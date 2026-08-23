/**
 * La mesure d'ergonomie : jusqu'ou defile-t-on, ou regarde-t-on, ou clique-t-on ?
 *
 * AUCUN SERVICE TIERS. Ni Hotjar, ni PostHog, ni equivalent : le produit se
 * vend sur la souverainete des donnees, et brancher un traceur etranger sur un
 * outil medical annulerait l'argument, meme sans donnee patient. Tout part vers
 * l'API du projet et rien d'autre.
 *
 * CE QUI EST MESURE : la profondeur de defilement atteinte par zone, le temps
 * passe avec chaque zone a l'ecran, les clics par zone nommee, l'ordre de
 * premiere visite, et la part de largeur donnee a chaque zone — le partage
 * choisi a la glissiere est une mesure d'ergonomie a lui seul.
 *
 * CE QUI NE L'EST PAS : le contenu saisi, la position du curseur au pixel, les
 * frappes. On mesure des COMPORTEMENTS D'USAGE, pas ce que le praticien ecrit.
 *
 * DEUX PROMESSES TENUES PAR LA CONSTRUCTION :
 *
 *  1. La mesure n'interfere jamais. Aucun etat React, donc aucun rendu declenche
 *     — les compteurs vivent dans un objet mutable. Tous les ecouteurs sont
 *     `passive` et en capture, aucun n'appelle preventDefault. La visibilite
 *     vient d'un IntersectionObserver, pas d'un ecouteur de defilement a haute
 *     frequence. Un envoi qui rate est avale : il ne remonte jamais au
 *     praticien et ne fait echouer aucune action.
 *
 *  2. Les envois sont des INSTANTANES CUMULES, pas des increments. Chaque lot
 *     porte l'etat courant des compteurs depuis l'ouverture du dossier, et le
 *     serveur ne retient que le dernier. Un lot perdu ne coute donc que du
 *     detail, jamais un total, et un lot rejoue ne compte rien deux fois. C'est
 *     ce qui permet d'ignorer un echec reseau sans rien reparer.
 *
 * CABLAGE. Une ligne dans App.tsx :
 *
 *     useMesureErgonomie(etude.dossierId);
 *
 * et un attribut `data-ergo` sur le conteneur de chaque zone a mesurer :
 *
 *     <PanneauAnalyse data-ergo="analyse" ... />
 *     <section data-ergo="compte_rendu" ...>      le panneau qui defile
 *     <BarreAjout data-ergo="barre_ajout" ... />
 *     <DialogueValidation data-ergo="validation" ... />
 *
 * L'attribut se pose sur le CONTENEUR QUI DEFILE quand il y en a un : c'est lui
 * qui porte scrollTop et scrollHeight, donc la profondeur atteinte. Les noms
 * sont fermes : le backend refuse un lot portant une zone inconnue plutot que
 * de l'ecarter en silence, parce qu'une zone silencieusement ecartee
 * ressemblerait, au depouillement, a un panneau que personne n'a visite.
 *
 * COUPURE. `VITE_MESURE_ERGONOMIE=0` desactive tout : aucun observateur, aucune
 * minuterie, aucun envoi. Il faut pouvoir faire tourner un cas SANS la mesure
 * pour verifier que la mesure elle-meme ne change pas le comportement.
 */

import { useEffect } from "react";
import { API_BASE } from "@/lib/config";
import { jsonHeaders } from "@/services/api";

/* ------------------------------------------------------------------ */
/*  Vocabulaire — miroir de backend/etude/ergonomie.py                 */
/* ------------------------------------------------------------------ */

export type ZoneErgonomie =
  | "analyse"
  | "compte_rendu"
  | "barre_ajout"
  | "validation";

/** L'attribut a poser sur les conteneurs a mesurer. */
export const ATTRIBUT_ZONE = "data-ergo";

const SELECTEUR_ZONE = `[${ATTRIBUT_ZONE}]`;

const NOMS_DE_ZONE: ReadonlySet<string> = new Set<ZoneErgonomie>([
  "analyse",
  "compte_rendu",
  "barre_ajout",
  "validation",
]);

/** Un instantane de zone, tel que le backend l'attend (champs `snake_case`). */
export interface ReleveErgonomie {
  zone: ZoneErgonomie;
  visible_ms: number;
  clics: number;
  profondeur_max: number | null;
  rang_premiere_visite: number | null;
  part_largeur: number | null;
}

/* ------------------------------------------------------------------ */
/*  Reglages                                                           */
/* ------------------------------------------------------------------ */

const reglage: unknown = import.meta.env.VITE_MESURE_ERGONOMIE;

/** Active par defaut ; `VITE_MESURE_ERGONOMIE=0` (ou `false`) la coupe. */
export const MESURE_ACTIVE: boolean = reglage !== "0" && reglage !== "false";

/**
 * Periode d'envoi. Un evenement par clic saturerait la base et le reseau pour
 * une donnee qu'on ne lira jamais autrement qu'agregee.
 */
const PERIODE_ENVOI_MS = 15_000;

/**
 * Periode de recensement des zones. Les panneaux apparaissent et disparaissent
 * au fil du travail ; un MutationObserver se declencherait a chaque frappe dans
 * le compte rendu, alors qu'une relecture de quatre noeuds toutes les deux
 * secondes ne coute rien.
 */
const PERIODE_RECENSEMENT_MS = 2_000;

/** En deca, la zone affleure l'ecran sans etre regardee. */
const SEUIL_VISIBILITE = 0.1;

/** Un ou deux pixels de debordement ne sont pas un defilement. */
const TOLERANCE_DEFILEMENT_PX = 4;

/* ------------------------------------------------------------------ */
/*  Noyau — des compteurs mutables, aucun etat React                   */
/* ------------------------------------------------------------------ */

interface CompteurZone {
  visibleMs: number;
  /** Instant du debut de la periode a l'ecran en cours, ou null. */
  visibleDepuis: number | null;
  clics: number;
  profondeurMax: number | null;
  rangPremiereVisite: number | null;
  partLargeur: number | null;
}

interface Mesure {
  compteurs: Map<ZoneErgonomie, CompteurZone>;
  /** Les elements marques, et la zone que chacun represente. */
  suivis: Map<Element, ZoneErgonomie>;
  intersectes: Set<Element>;
  ongletVisible: boolean;
  prochainRang: number;
}

function creerMesure(): Mesure {
  return {
    compteurs: new Map(),
    suivis: new Map(),
    intersectes: new Set(),
    ongletVisible: document.visibilityState === "visible",
    prochainRang: 1,
  };
}

function creerCompteur(): CompteurZone {
  return {
    visibleMs: 0,
    visibleDepuis: null,
    clics: 0,
    // Null et non zero : tant que rien n'a ete observe, il n'y a pas de mesure.
    profondeurMax: null,
    rangPremiereVisite: null,
    partLargeur: null,
  };
}

function compteurDe(mesure: Mesure, zone: ZoneErgonomie): CompteurZone {
  const existant = mesure.compteurs.get(zone);
  if (existant !== undefined) return existant;
  const nouveau = creerCompteur();
  mesure.compteurs.set(zone, nouveau);
  return nouveau;
}

function estUneZone(valeur: string | null): valeur is ZoneErgonomie {
  return valeur !== null && NOMS_DE_ZONE.has(valeur);
}

/** L'element marque qui contient la cible d'un evenement, s'il y en a un. */
function elementMarque(cible: EventTarget | null): Element | null {
  if (!(cible instanceof Element)) return null;
  return cible.closest(SELECTEUR_ZONE);
}

/**
 * Date la premiere visite d'une zone.
 *
 * VISITE = PREMIER GESTE, pas premiere apparition a l'ecran. Sur un ecran
 * partage, l'analyse et le compte rendu sont visibles des l'ouverture : leur
 * visibilite ne dit donc rien de l'ordre dans lequel on s'y met. Ce qui le dit,
 * c'est l'endroit ou le praticien agit en premier.
 */
function marquerVisite(mesure: Mesure, zone: ZoneErgonomie): void {
  const compteur = compteurDe(mesure, zone);
  if (compteur.rangPremiereVisite !== null) return;
  compteur.rangPremiereVisite = mesure.prochainRang;
  mesure.prochainRang += 1;
}

function estAffichee(mesure: Mesure, zone: ZoneErgonomie): boolean {
  for (const element of mesure.intersectes) {
    if (mesure.suivis.get(element) === zone) return true;
  }
  return false;
}

/**
 * Ouvre ou ferme la periode a l'ecran de chaque zone.
 *
 * Un onglet masque ne compte pour aucune zone : ce serait mesurer la pause
 * cafe, exactement ce que l'horloge de l'etude deduit deja du temps de revision.
 */
function ajusterHorloges(mesure: Mesure, instant: number): void {
  for (const [zone, compteur] of mesure.compteurs) {
    const aLEcran = mesure.ongletVisible && estAffichee(mesure, zone);
    if (aLEcran && compteur.visibleDepuis === null) {
      compteur.visibleDepuis = instant;
    } else if (!aLEcran && compteur.visibleDepuis !== null) {
      compteur.visibleMs += Math.max(0, instant - compteur.visibleDepuis);
      compteur.visibleDepuis = null;
    }
  }
}

function borner(valeur: number): number {
  return Math.min(1, Math.max(0, valeur));
}

/**
 * Part du contenu vue, ou null quand la zone tient dans l'ecran.
 *
 * Null et non 1 : sans debordement il n'y a pas de profondeur a atteindre, et
 * ecrire 100 % confondrait « il a tout parcouru » et « il n'y avait rien a
 * parcourir ».
 */
function profondeurAtteinte(element: Element): number | null {
  const debordement = element.scrollHeight - element.clientHeight;
  if (debordement <= TOLERANCE_DEFILEMENT_PX) return null;
  return borner(
    (element.scrollTop + element.clientHeight) / element.scrollHeight,
  );
}

/**
 * Part de la largeur du plan de travail occupee par la zone.
 *
 * Mesuree contre le parent plutot que contre la fenetre : c'est le conteneur
 * partage par la glissiere, donc exactement le partage que le praticien a
 * choisi. Null si le parent n'a pas de largeur — une zone repliee n'est pas une
 * zone a qui l'on aurait donne zero.
 */
function partDeLargeur(element: Element): number | null {
  const parent = element.parentElement;
  if (parent === null) return null;
  const largeurParent = parent.getBoundingClientRect().width;
  if (largeurParent <= 0) return null;
  const largeur = element.getBoundingClientRect().width;
  if (largeur <= 0) return null;
  return borner(largeur / largeurParent);
}

/** Releve les mesures geometriques d'un lot d'elements. */
function echantillonner(mesure: Mesure, elements: Iterable<Element>): void {
  for (const element of elements) {
    const zone = mesure.suivis.get(element);
    if (zone === undefined) continue;
    const compteur = compteurDe(mesure, zone);
    const atteinte = profondeurAtteinte(element);
    if (atteinte !== null) {
      compteur.profondeurMax = Math.max(compteur.profondeurMax ?? 0, atteinte);
    }
    const part = partDeLargeur(element);
    // On n'ecrase jamais une largeur mesuree par une absence de mesure.
    if (part !== null) compteur.partLargeur = part;
  }
}

/**
 * L'etat courant des compteurs, sans les remettre a zero.
 *
 * C'est ce qui rend un lot perdu inoffensif : le lot suivant porte les memes
 * secondes et les memes clics, cumules depuis l'ouverture du dossier.
 */
function instantane(mesure: Mesure, instant: number): ReleveErgonomie[] {
  const releves: ReleveErgonomie[] = [];
  for (const [zone, compteur] of mesure.compteurs) {
    const enCours =
      compteur.visibleDepuis === null
        ? 0
        : Math.max(0, instant - compteur.visibleDepuis);
    releves.push({
      zone,
      visible_ms: Math.round(compteur.visibleMs + enCours),
      clics: compteur.clics,
      profondeur_max: compteur.profondeurMax,
      rang_premiere_visite: compteur.rangPremiereVisite,
      part_largeur: compteur.partLargeur,
    });
  }
  return releves;
}

/**
 * Depose un lot. N'echoue jamais : une mesure ratee ne doit pas exister pour le
 * praticien.
 *
 * `keepalive` parce que le dernier lot part souvent au moment ou la page se
 * ferme ou passe en arriere-plan — sans lui, le navigateur l'annulerait, et
 * c'est justement le lot le plus complet.
 */
async function deposer(
  dossierId: string,
  releves: ReleveErgonomie[],
): Promise<void> {
  if (releves.length === 0) return;
  try {
    await fetch(`${API_BASE}/etude/dossiers/${dossierId}/ergonomie`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ releves }),
      keepalive: true,
    });
  } catch {
    // Avale : le prochain instantane porte les memes compteurs.
  }
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

/**
 * Mesure l'usage de l'interface pendant un dossier instrumente.
 *
 * @param dossierId dossier en cours, ou null hors etude — la mesure est alors
 *   totalement au repos : aucun observateur, aucune minuterie, aucun envoi.
 * @param actif faux pour derouler un cas sans mesure du tout, et verifier que
 *   la mesure elle-meme ne change pas le comportement.
 */
export function useMesureErgonomie(
  dossierId: string | null,
  actif: boolean = MESURE_ACTIVE,
): void {
  useEffect(() => {
    if (!actif || dossierId === null) return;

    const mesure = creerMesure();
    let image: number | null = null;
    const aRelire = new Set<Element>();

    const observateur = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (
            entree.isIntersecting &&
            entree.intersectionRatio >= SEUIL_VISIBILITE
          ) {
            mesure.intersectes.add(entree.target);
          } else {
            mesure.intersectes.delete(entree.target);
          }
        }
        ajusterHorloges(mesure, Date.now());
      },
      { threshold: [0, SEUIL_VISIBILITE, 0.5, 1] },
    );

    /** Prend en charge les zones apparues, oublie celles retirees du DOM. */
    const recenser = (): void => {
      document.querySelectorAll(SELECTEUR_ZONE).forEach((element) => {
        const zone = element.getAttribute(ATTRIBUT_ZONE);
        if (!estUneZone(zone) || mesure.suivis.has(element)) return;
        mesure.suivis.set(element, zone);
        // Le compteur nait avec la zone : savoir qu'un panneau etait la et n'a
        // jamais ete regarde est un resultat, pas une absence de mesure.
        compteurDe(mesure, zone);
        observateur.observe(element);
      });
      for (const element of mesure.suivis.keys()) {
        if (element.isConnected) continue;
        // Un panneau demonte n'est plus a l'ecran : sans cela, sa periode
        // visible resterait ouverte jusqu'a la fin du dossier.
        mesure.suivis.delete(element);
        mesure.intersectes.delete(element);
        observateur.unobserve(element);
      }
      ajusterHorloges(mesure, Date.now());
    };

    const relire = (): void => {
      image = null;
      echantillonner(mesure, aRelire);
      aRelire.clear();
    };

    /**
     * Le defilement est le seul geste dont aucun observateur ne rend compte :
     * il faut lire scrollTop sur le conteneur. L'ecouteur ne fait donc rien
     * d'autre que noter l'element, et la lecture — qui declenche un calcul de
     * mise en page — attend la prochaine image.
     */
    const surDefilement = (evenement: Event): void => {
      const element = elementMarque(evenement.target);
      if (element === null) return;
      const zone = mesure.suivis.get(element);
      if (zone === undefined) return;
      marquerVisite(mesure, zone);
      aRelire.add(element);
      if (image === null) image = requestAnimationFrame(relire);
    };

    /**
     * `pointerdown` plutot que `click` : une poignee que l'on saisit pour la
     * faire glisser — la glissiere, precisement — n'emet jamais de clic, et ce
     * geste-la est une mesure d'ergonomie a lui seul.
     */
    const surPointeur = (evenement: Event): void => {
      const element = elementMarque(evenement.target);
      if (element === null) return;
      const zone = mesure.suivis.get(element);
      if (zone === undefined) return;
      compteurDe(mesure, zone).clics += 1;
      marquerVisite(mesure, zone);
    };

    const envoyer = (): void => {
      echantillonner(mesure, mesure.intersectes);
      void deposer(dossierId, instantane(mesure, Date.now()));
    };

    const surVisibiliteOnglet = (): void => {
      mesure.ongletVisible = document.visibilityState === "visible";
      ajusterHorloges(mesure, Date.now());
      // L'onglet masque peut ne jamais revenir : c'est le bon moment pour
      // deposer ce qu'on sait.
      if (!mesure.ongletVisible) envoyer();
    };

    // Capture : le defilement ne remonte pas jusqu'a window depuis un conteneur
    // interne, et c'est justement la que defilent les panneaux. Passif : la
    // mesure ne doit jamais retarder le rendu d'un defilement.
    const options: AddEventListenerOptions = { capture: true, passive: true };
    window.addEventListener("scroll", surDefilement, options);
    window.addEventListener("pointerdown", surPointeur, options);
    document.addEventListener("visibilitychange", surVisibiliteOnglet);

    recenser();
    const minuterieRecensement = setInterval(recenser, PERIODE_RECENSEMENT_MS);
    const minuterieEnvoi = setInterval(envoyer, PERIODE_ENVOI_MS);

    return () => {
      clearInterval(minuterieRecensement);
      clearInterval(minuterieEnvoi);
      if (image !== null) cancelAnimationFrame(image);
      window.removeEventListener("scroll", surDefilement, options);
      window.removeEventListener("pointerdown", surPointeur, options);
      document.removeEventListener("visibilitychange", surVisibiliteOnglet);
      observateur.disconnect();

      // Fermer les periodes ouvertes AVANT le dernier envoi : sans cela, le
      // temps passe sur la derniere zone regardee manquerait a l'appel.
      echantillonner(mesure, mesure.intersectes);
      mesure.intersectes.clear();
      ajusterHorloges(mesure, Date.now());
      // Sur le dossier capture par cet effet, jamais sur le suivant.
      void deposer(dossierId, instantane(mesure, Date.now()));
    };
  }, [dossierId, actif]);
}
