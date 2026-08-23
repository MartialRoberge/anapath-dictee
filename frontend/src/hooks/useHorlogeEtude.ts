/**
 * L'horloge de l'etude : elle produit les pauses a deduire du temps de revision.
 *
 * Deux causes d'interruption, une regle chacune :
 *
 *  1. `onglet_masque` — Page Visibility API. La pause court du moment ou
 *     l'onglet devient cache jusqu'au moment ou il redevient visible.
 *
 *  2. `inactivite` — plus de 90 s sans le moindre evenement d'interaction. La
 *     pause est datee RETROACTIVEMENT A PARTIR DE LA DERNIERE ACTION, jamais a
 *     partir de l'expiration du compteur. Si le praticien agit a 10h00 et
 *     revient a 10h05, la pause va de 10h00 a 10h05 — cinq minutes. La dater a
 *     10h01m30 en compterait trois trente et gonflerait le temps de revision de
 *     quatre-vingt-dix secondes a chaque interruption ; sur dix cas, cela suffit
 *     a fausser le resultat principal de l'etude.
 *
 * REGLE DE CHEVAUCHEMENT — un onglet masque est aussi une inactivite, et
 * additionner les deux rendrait le temps net negatif. On ne compte donc que
 * l'UNION des deux causes : une seule pause est ouverte a la fois, elle se
 * ferme quand plus AUCUNE cause n'est active, son debut est le plus ancien
 * debut defendable parmi les causes actives (le masquage date de l'instant du
 * masquage, l'inactivite de la derniere action) et il ne peut que RECULER. La
 * cause enregistree est celle qui a fourni ce debut : c'est elle qui explique
 * l'interruption.
 *
 * L'etat est recalcule a partir des horodatages a chaque evenement, jamais
 * deduit du declenchement d'une minuterie : les minuteries d'un onglet en
 * arriere-plan sont etranglees, voire gelees, par le navigateur. La minuterie
 * ne sert donc qu'a rafraichir l'indicateur affiche ; la mesure, elle, reste
 * exacte meme si elle ne se declenche jamais.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { journaliserPause, type CausePause } from "@/services/etude";

/**
 * Seuil d'inactivite du cahier de recueil §5 (CAUSES_PAUSE / SEUIL_INACTIVITE_S
 * dans backend/etude/vocabulaire.py). Il est repris a l'identique cote client :
 * c'est le client qui date les pauses, une divergence rendrait les durees
 * incomparables d'un poste a l'autre.
 */
export const SEUIL_INACTIVITE_MS = 90_000;

/** Marge ajoutee a la minuterie pour que le seuil soit franchi, pas frole. */
const MARGE_MINUTERIE_MS = 50;

/**
 * Une souris emet une soixantaine d'evenements par seconde. Tant qu'aucune
 * pause n'est ouverte, il est inutile de rejouer le calcul a chaque pixel : la
 * derniere action reste juste au quart de seconde, sans commune mesure avec un
 * seuil de quatre-vingt-dix secondes.
 */
const GRANULARITE_ACTION_MS = 250;

/** Evenements qui attestent que le praticien travaille sur le dossier. */
const EVENEMENTS_INTERACTION = [
  "pointerdown",
  "keydown",
  "wheel",
  "mousemove",
  "scroll",
  "touchstart",
  "input",
] as const;

/* ------------------------------------------------------------------ */
/*  Noyau pur — testable sans DOM ni React                             */
/* ------------------------------------------------------------------ */

export interface PauseOuverte {
  debut: number;
  cause: CausePause;
}

export interface PauseTerminee extends PauseOuverte {
  fin: number;
}

export interface EtatHorloge {
  derniereAction: number;
  cacheDepuis: number | null;
  pause: PauseOuverte | null;
}

export type EvenementHorloge =
  | { type: "action"; instant: number }
  | { type: "masquage"; instant: number }
  | { type: "affichage"; instant: number }
  | { type: "verification"; instant: number }
  | { type: "cloture"; instant: number };

export interface ResultatHorloge {
  etat: EtatHorloge;
  /** Pause TERMINEE, prete a partir. Une pause en cours n'apparait jamais ici. */
  terminee: PauseTerminee | null;
}

export function nouvelEtat(instant: number, cache = false): EtatHorloge {
  return {
    derniereAction: instant,
    cacheDepuis: cache ? instant : null,
    pause: null,
  };
}

/** Le plus ancien debut defendable parmi les causes actives, ou null. */
function causeActive(etat: EtatHorloge, instant: number): PauseOuverte | null {
  let retenue: PauseOuverte | null = null;
  if (etat.cacheDepuis !== null) {
    retenue = { debut: etat.cacheDepuis, cause: "onglet_masque" };
  }
  const inactif = instant - etat.derniereAction > SEUIL_INACTIVITE_MS;
  if (inactif && (retenue === null || etat.derniereAction < retenue.debut)) {
    retenue = { debut: etat.derniereAction, cause: "inactivite" };
  }
  return retenue;
}

function fermer(
  pause: PauseOuverte | null,
  instant: number,
): PauseTerminee | null {
  // Une pause de duree nulle n'apprend rien et polluerait le comptage.
  if (pause === null || instant <= pause.debut) return null;
  return { ...pause, fin: instant };
}

/**
 * Applique un evenement a l'horloge.
 *
 * Fonction pure : c'est ici que vit la regle de chevauchement, et c'est ici
 * qu'elle se verifie sans navigateur.
 */
export function reduire(
  etat: EtatHorloge,
  evenement: EvenementHorloge,
): ResultatHorloge {
  const { instant } = evenement;

  switch (evenement.type) {
    case "action": {
      // Reconcilier AVANT de redater, et fermer dans la foulee.
      //
      // Redater d'abord effacerait l'inactivite qui vient de s'ecouler : le
      // praticien reste cent secondes sans toucher a rien puis clique, et
      // l'ecart disparait sans laisser de trace. La minuterie devrait l'avoir
      // detecte, mais un navigateur etrangle — voire gele — les minuteries d'un
      // onglet en arriere-plan. Detecter ici rend la mesure independante de la
      // minuterie, ce que ce module promet.
      const ouvert = reconcilier(etat, instant);
      const clos =
        ouvert.terminee !== null ? ouvert : cloturerPause(ouvert.etat, instant);
      return {
        etat: { ...clos.etat, derniereAction: instant },
        terminee: clos.terminee,
      };
    }

    case "masquage":
      // Un second masquage sans affichage intermediaire ne redate rien.
      return reconcilier(
        { ...etat, cacheDepuis: etat.cacheDepuis ?? instant },
        instant,
      );

    case "affichage":
      // L'onglet revient, mais l'inactivite peut fort bien courir encore : la
      // pause ne se referme qu'a la reprise effective du travail.
      return reconcilier({ ...etat, cacheDepuis: null }, instant);

    case "verification":
      return reconcilier(etat, instant);

    case "cloture": {
      // Reconcilier d'abord : une pause que la minuterie n'a pas eu le temps
      // d'ouvrir doit exister avant d'etre fermee, sinon on perd
      // systematiquement la derniere interruption du dossier.
      const reconcilie = reconcilier(etat, instant);
      if (reconcilie.terminee !== null) return reconcilie;
      return cloturerPause(reconcilie.etat, instant);
    }
  }
}

/**
 * Ferme la pause en cours ET borne le depart de la suivante.
 *
 * L'INVARIANT QUI MANQUAIT, et sans lequel le resultat principal de l'etude
 * s'effondre : une periode envoyee au serveur ne doit jamais pouvoir etre
 * recouverte par une pause ulterieure. Le serveur somme les durees a plat, sans
 * union ni deduplication — a lui seul il ne peut pas rattraper un chevauchement.
 *
 * Sans ce bornage : un masquage de 70 s pendant une inactivite qui court encore
 * etait facture une fois comme `onglet_masque`, puis une seconde fois a
 * l'interieur de l'inactivite datee de la derniere action. Sur un profil banal —
 * lecture, aller-retour vers un referentiel, relecture a l'ecran sans souris —
 * la somme des pauses depassait le temps de revision et `revision_nette_ms`
 * tombait a zero.
 *
 * Avancer `derniereAction` a la fin de la pause est aussi la lecture juste :
 * sortir d'une interruption EST une reprise du travail.
 */
function cloturerPause(etat: EtatHorloge, instant: number): ResultatHorloge {
  const terminee = fermer(etat.pause, instant);
  if (terminee === null) return { etat: { ...etat, pause: null }, terminee: null };
  return {
    etat: {
      ...etat,
      pause: null,
      derniereAction: Math.max(etat.derniereAction, terminee.fin),
    },
    terminee,
  };
}

function reconcilier(etat: EtatHorloge, instant: number): ResultatHorloge {
  const active = causeActive(etat, instant);

  if (active === null) {
    if (etat.pause === null) return { etat, terminee: null };
    return cloturerPause(etat, instant);
  }

  // Le debut ne peut que reculer : c'est ce qui absorbe le masquage survenu
  // pendant une inactivite deja commencee sans compter la periode deux fois.
  if (etat.pause === null || active.debut < etat.pause.debut) {
    return { etat: { ...etat, pause: active }, terminee: null };
  }
  return { etat, terminee: null };
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

export interface HorlogeEtude {
  /** Une interruption court : l'ecran peut griser son chronometre. */
  enPause: boolean;
  causeEnCours: CausePause | null;
  /** Pauses dont l'envoi a echoue : la mesure de ce dossier est incomplete. */
  pausesNonEnvoyees: number;
  /** Ferme la pause en cours et vide la file. A appeler AVANT de clore. */
  cloturer: () => Promise<void>;
}

/**
 * Chronometre les interruptions d'un dossier instrumente.
 *
 * @param dossierId identifiant du dossier en cours, ou null hors etude —
 *   l'horloge est alors totalement au repos (aucun ecouteur, aucun envoi).
 */
export function useHorlogeEtude(dossierId: string | null): HorlogeEtude {
  // Null tant que l'horloge n'a pas demarre : la dater au rendu appellerait
  // Date.now() pendant celui-ci, et un dossier deja demonte n'a plus d'etat du
  // tout — c'est ce qui interdit de lui attribuer une pause apres coup.
  const etatRef = useRef<EtatHorloge | null>(null);
  const fileRef = useRef<PauseTerminee[]>([]);
  const minuterieRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [pause, setPause] = useState<PauseOuverte | null>(null);
  const [pausesNonEnvoyees, setPausesNonEnvoyees] = useState(0);

  /**
   * Vide la file d'envoi. Un echec reseau ne bloque jamais le praticien : la
   * pause retourne en file et le compteur le dit a l'ecran, plutot que de
   * laisser croire que la mesure est enregistree.
   */
  const viderFile = useCallback(async (id: string): Promise<void> => {
    const aEnvoyer = fileRef.current;
    fileRef.current = [];
    const echecs: PauseTerminee[] = [];

    for (const p of aEnvoyer) {
      try {
        await journaliserPause(id, {
          debut: new Date(p.debut).toISOString(),
          fin: new Date(p.fin).toISOString(),
          cause: p.cause,
        });
      } catch {
        echecs.push(p);
      }
    }

    fileRef.current = [...echecs, ...fileRef.current];
    setPausesNonEnvoyees(fileRef.current.length);
  }, []);

  /** Applique un evenement et rend l'etat obtenu, ou null si l'horloge dort. */
  const traiter = useCallback(
    (evenement: EvenementHorloge, id: string | null): EtatHorloge | null => {
      const precedent = etatRef.current;
      if (precedent === null) return null;

      const { etat, terminee } = reduire(precedent, evenement);
      etatRef.current = etat;
      // L'identite de `pause` est preservee tant que rien ne change : React
      // renonce alors au rendu, et un mouvement de souris ne coute rien.
      setPause(etat.pause);
      if (terminee !== null && id !== null) {
        fileRef.current.push(terminee);
        void viderFile(id);
      }
      return etat;
    },
    [viderFile],
  );

  useEffect(() => {
    if (dossierId === null) return;

    // Repartir de l'instant present : une derniere action heritee du dossier
    // precedent fabriquerait une pause fictive des l'ouverture.
    const depart = Date.now();
    etatRef.current = nouvelEtat(depart, document.visibilityState === "hidden");

    const programmer = (depuis: number): void => {
      if (minuterieRef.current !== null) clearTimeout(minuterieRef.current);
      const restant = SEUIL_INACTIVITE_MS - (Date.now() - depuis);
      minuterieRef.current = setTimeout(
        () => traiter({ type: "verification", instant: Date.now() }, dossierId),
        Math.max(restant, 0) + MARGE_MINUTERIE_MS,
      );
    };

    const surAction = (): void => {
      const courant = etatRef.current;
      if (courant === null) return;
      const instant = Date.now();
      if (
        courant.pause === null &&
        instant - courant.derniereAction < GRANULARITE_ACTION_MS
      ) {
        return;
      }
      const suivant = traiter({ type: "action", instant }, dossierId);
      if (suivant !== null) programmer(suivant.derniereAction);
    };

    const surVisibilite = (): void => {
      const cache = document.visibilityState === "hidden";
      const suivant = traiter(
        { type: cache ? "masquage" : "affichage", instant: Date.now() },
        dossierId,
      );
      if (!cache && suivant !== null) programmer(suivant.derniereAction);
    };

    // Capture : `scroll` ne remonte pas jusqu'a window depuis un conteneur
    // interne, et c'est justement la que defile le compte-rendu.
    const options: AddEventListenerOptions = { capture: true, passive: true };
    EVENEMENTS_INTERACTION.forEach((nom) =>
      window.addEventListener(nom, surAction, options),
    );
    document.addEventListener("visibilitychange", surVisibilite);
    programmer(depart);

    return () => {
      EVENEMENTS_INTERACTION.forEach((nom) =>
        window.removeEventListener(nom, surAction, options),
      );
      document.removeEventListener("visibilitychange", surVisibilite);
      if (minuterieRef.current !== null) {
        clearTimeout(minuterieRef.current);
        minuterieRef.current = null;
      }
      // Une pause encore ouverte appartient au dossier que l'on quitte :
      // l'abandonner reviendrait a compter une interruption comme du temps de
      // revision. Elle part sur l'identifiant capture par cet effet, jamais sur
      // le suivant.
      traiter({ type: "cloture", instant: Date.now() }, dossierId);
      // Plus d'horloge : un evenement tardif ne peut plus rien attribuer a un
      // dossier deja quitte.
      etatRef.current = null;
    };
  }, [dossierId, traiter]);

  const cloturer = useCallback(async (): Promise<void> => {
    if (minuterieRef.current !== null) {
      clearTimeout(minuterieRef.current);
      minuterieRef.current = null;
    }
    const courant = etatRef.current;
    if (courant === null || dossierId === null) return;

    const { etat, terminee } = reduire(courant, {
      type: "cloture",
      instant: Date.now(),
    });
    etatRef.current = etat;
    setPause(null);
    // Par la file, comme les autres : une seule voie d'envoi, un seul endroit
    // ou un echec reseau se rattrape.
    if (terminee !== null) fileRef.current.push(terminee);
    await viderFile(dossierId);
  }, [dossierId, viderFile]);

  return {
    enPause: pause !== null,
    causeEnCours: pause?.cause ?? null,
    pausesNonEnvoyees,
    cloturer,
  };
}
