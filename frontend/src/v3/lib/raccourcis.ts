// Raccourcis clavier MARC : un seul endroit pour la liste, les libellés par plateforme et la détection des champs de saisie.
// Choix : Alt + touche physique (event.code), car Ctrl+Alt = AltGr en disposition française ; D, E, F sont évitées (menus et barre d'adresse des navigateurs).

export const estMac = (): boolean => {
  try { return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent); } catch { return false; }
};

/** Libellé d'une touche modificateur + lettre, ex. « ⌥C » (Mac) ou « Alt+C ». */
export const touche = (k: string): string => (estMac() ? `⌥${k}` : `Alt+${k}`);

export const estChampSaisie = (t: EventTarget | null): boolean =>
  t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

export interface Raccourci { touches: string; action: string }
export interface GroupeRaccourcis { titre: string; items: Raccourci[] }

export const groupes = (): GroupeRaccourcis[] => [
  {
    titre: "Dicter",
    items: [
      { touches: "Espace (maintenu)", action: "Dicter un nouveau projet (hors champ de saisie)" },
      { touches: "Échap", action: "Annuler l'enregistrement" },
      { touches: touche("M"), action: "Compléter à la voix : ouvrir, démarrer, arrêter" },
      { touches: touche("N"), action: "Nouveau projet" },
    ],
  },
  {
    titre: "Combler les trous",
    items: [
      { touches: "Tab · Maj+Tab", action: "Trou suivant · précédent" },
      { touches: "Une lettre ou un chiffre", action: "Sur un trou : ouvre le champ et commence la saisie" },
      { touches: "Entrée", action: "Valider la valeur et passer au trou suivant" },
      { touches: "Échap", action: "Fermer le champ" },
    ],
  },
  {
    titre: "Relire et vérifier",
    items: [
      { touches: `${touche("↓")} · ${touche("↑")}`, action: "Point suivant · précédent, surligné dans le texte" },
      { touches: "Clic ou Tab sur une phrase", action: "Ouvre « Pourquoi » : dictée, règles, référentiel, modèle" },
      { touches: touche("R"), action: "Résoudre le point actif" },
      { touches: touche("I"), action: "Ignorer le point actif" },
      { touches: `${touche("1")} à ${touche("5")}`, action: "Onglets du panneau : Pourquoi, À vérifier, Codes, Dictée, Progression" },
    ],
  },
  {
    titre: "Valider et sortir",
    items: [
      { touches: touche("V"), action: "Valider le compte rendu (Entrée confirme)" },
      { touches: touche("C"), action: "Copier tout, mise en forme Word incluse" },
      { touches: touche("X"), action: "Exporter en DOCX" },
      { touches: "? ou " + touche("/"), action: "Afficher cette aide" },
    ],
  },
];

/** Raccourci Alt+touche physique. Retourne la clé normalisée (« KeyC », « ArrowDown », « Digit1 »…) ou null. */
export const cleAlt = (e: KeyboardEvent): string | null =>
  e.altKey && !e.ctrlKey && !e.metaKey ? e.code : null;

export const ACTION = "marc:action";
export type NomAction = "valider" | "completer" | "aide";
export const declencher = (a: NomAction) => window.dispatchEvent(new CustomEvent(ACTION, { detail: a }));
