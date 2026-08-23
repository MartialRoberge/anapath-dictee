/**
 * Revue des propositions, version LATERALE : elle vit a cote du compte-rendu
 * pendant que le praticien travaille son texte.
 *
 * ------------------------------------------------------------------
 *  POURQUOI UNE SECONDE VUE
 * ------------------------------------------------------------------
 *
 *  RevuePanel occupe l'ecran entier avec ses trois panneaux. C'est la bonne
 *  vue pour depouiller un dossier, et la mauvaise pour decider EN ECRIVANT :
 *  elle chasse le compte-rendu de l'ecran, donc on ne l'ouvre pas, donc aucune
 *  decision n'est prise et l'administration reste vide. Cette version-ci tient
 *  dans une colonne a cote de l'editeur, et se replie quand on veut ecrire.
 *
 *  Les differences avec la vue pleine sont donc toutes des consequences de la
 *  largeur disponible :
 *   - pas de panneau verbatim a demeure : le survol d'une carte remonte au
 *     parent, qui surligne le passage DANS le compte-rendu ; l'extrait de
 *     dictee se deplie carte par carte, a la demande ;
 *   - une seule colonne, les cartes l'une sous l'autre ;
 *   - pas de pile des decidees : sans annulation dans le contrat de props,
 *     une liste des decisions prises ne serait qu'un rappel sans recours.
 *     Ce que la pile prouvait — que la tache diminue — est porte ici par
 *     l'en-tete et sa barre de progression.
 *
 * ------------------------------------------------------------------
 *  CONTRAT DE PROPS
 * ------------------------------------------------------------------
 *
 *  propositions    Miroir de `PropositionAffichee` (routes_etude.py).
 *  decisions       id de proposition -> valeur de decision prise.
 *  transcription   FACULTATIVE. Fournie, chaque carte ancree peut deplier le
 *                  passage exact de la dictee. Absente, la fonction se retire
 *                  sans bruit : rien d'autre n'en depend.
 *  onDecider       Enregistre la decision cote serveur. DOIT rejeter en cas
 *                  d'echec : la carte affiche alors l'erreur et reste en place.
 *  onSurvol        La proposition visee en ce moment, ou null. C'est au parent
 *                  de surligner le passage correspondant dans le compte-rendu.
 *  replie / onReplier  Le repli est PILOTE PAR LE PARENT : la place que prend
 *                  ce panneau change la largeur de l'editeur, cette decision
 *                  ne peut donc pas se prendre ici.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Keyboard,
  ListChecks,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  grilleDe,
  LIBELLES_CAUSE_ERREUR,
  LIBELLES_DECISION,
} from "@/services/etude";
import type { CauseErreur as ValeurCause, Decision } from "@/services/etude";
import PropositionCarte from "./PropositionCarte";
import type {
  NatureCorrection,
  OptionDecisionEtendue,
  OptionsDecisionEtendues,
} from "./PropositionCarte";
import type {
  CauseErreur,
  PropositionEtude,
  TonDecision,
  TypeProposition,
} from "./RevuePanel";

/* ------------------------------------------------------------------ */
/*  Grilles — habillage local, vocabulaire du backend                  */
/* ------------------------------------------------------------------ */

interface PresentationDecision {
  ton: TonDecision;
  /**
   * Touche unique, en majuscule, qui decide la carte au clavier. Unique DANS
   * SA GRILLE : deux grilles peuvent reutiliser la meme lettre, elles ne sont
   * jamais affichees ensemble.
   */
  raccourci: string;
  aide?: string;
  saisieValeur?: boolean;
  demandeCause?: boolean;
  demandeNature?: boolean;
}

/**
 * L'habillage de chaque decision : sa couleur, sa lettre, les questions
 * qu'elle ouvre.
 *
 * La LISTE des decisions, elle, n'est pas recopiee ici : elle vient de
 * services/etude, miroir du vocabulaire backend. Une liste recopiee divergerait
 * au premier remaniement, et une decision hors grille est refusee en 400. Ce
 * Record etant exhaustif, une decision ajoutee au vocabulaire ne compile plus
 * tant qu'elle n'a pas recu son habillage.
 */
const PRESENTATION: Record<Decision, PresentationDecision> = {
  conforme: { ton: "valide", raccourci: "C", aide: "je valide tel quel" },
  corrige: {
    ton: "nuance",
    raccourci: "M",
    aide: "je reecris cette ligne",
    saisieValeur: true,
    demandeCause: true,
    demandeNature: true,
  },
  non_dicte: { ton: "rejet", raccourci: "N", demandeCause: true },
  hors_sujet: { ton: "neutre", raccourci: "H" },
  juste: { ton: "valide", raccourci: "J" },
  je_ne_sais_pas: { ton: "neutre", raccourci: "S" },
  pertinent_ajoute: { ton: "valide", raccourci: "A" },
  pertinent_non_retenu: { ton: "nuance", raccourci: "S" },
  non_pertinent: { ton: "neutre", raccourci: "N" },
};

function construireGrille(
  type: TypeProposition,
): readonly OptionDecisionEtendue[] {
  return grilleDe(type).map((valeur) => ({
    valeur,
    libelle: LIBELLES_DECISION[valeur],
    ...PRESENTATION[valeur],
  }));
}

const GRILLES: Record<TypeProposition, readonly OptionDecisionEtendue[]> = {
  restitution: construireGrille("restitution"),
  code: construireGrille("code"),
  completude: construireGrille("completude"),
};

const VALEURS_CAUSE: readonly ValeurCause[] = [
  "transcription",
  "interpretation",
];

// Les libelles viennent du backend : le depouillement doit pouvoir associer
// une reponse a un libelle exact des mois plus tard.
const CAUSES: readonly CauseErreur[] = VALEURS_CAUSE.map((valeur) => ({
  valeur,
  libelle: LIBELLES_CAUSE_ERREUR[valeur],
}));

/**
 * Les valeurs admises pour la nature, miroir de `NATURES_CORRECTION`
 * (backend/etude/vocabulaire.py).
 *
 * Ecrites ici et non dans services/etude : aucun autre ecran ne pose cette
 * question. Le type ferme la porte des la compilation, la ou une faute de
 * frappe ne se verrait autrement qu'en 400 devant le praticien.
 */
type ValeurNature = "style" | "precision" | "erreur_fond";

/** Une nature affichable : la valeur du backend, l'habillage de cet ecran. */
interface NatureLocale extends NatureCorrection {
  valeur: ValeurNature;
}

/**
 * Les trois natures de correction.
 *
 * C'est la distinction entre « l'outil s'est trompe » et « j'ecris
 * autrement ». Sans elle, toute correction compte comme une erreur du systeme
 * et le taux publie melange deux choses sans rapport. Seule la derniere ouvre
 * la question de la cause : demander pourquoi une reformulation de style a eu
 * lieu n'a pas de sens, et le backend refuse la combinaison en 400.
 */
const NATURES: readonly NatureLocale[] = [
  {
    valeur: "style",
    libelle: "Je reformule a ma main",
    aide: "le fond etait juste",
    ton: "neutre",
    demandeCause: false,
  },
  {
    valeur: "precision",
    libelle: "J'ajoute une precision",
    aide: "juste, mais incomplet",
    ton: "nuance",
    demandeCause: false,
  },
  {
    valeur: "erreur_fond",
    libelle: "C'etait faux",
    aide: "MARC s'est trompe sur le fond",
    ton: "rejet",
    demandeCause: true,
  },
];

/* ------------------------------------------------------------------ */
/*  Rythme des mouvements                                              */
/* ------------------------------------------------------------------ */

/** Duree de la sortie d'une carte. Assez pour etre lue, jamais pour attendre. */
const DUREE_SORTIE_MS = 200;

/**
 * Le praticien a demande a ne pas etre anime.
 *
 * Relu a chaque decision plutot que mis en cache : le reglage systeme peut
 * changer pendant la revue, et une carte bloquee en transition serait un
 * defaut bien pire que l'absence d'animation.
 */
function mouvementReduit(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* ------------------------------------------------------------------ */
/*  Extrait de dictee                                                  */
/* ------------------------------------------------------------------ */

/**
 * Le passage de la dictee que la proposition cite, ou null.
 *
 * Bornage defensif : on ne coupe jamais hors de la chaine. C'est le seul
 * traitement applique aux offsets — aucune recherche de texte, aucune
 * reconstruction : le serveur fait foi, et la moindre normalisation de la
 * transcription (trim, espaces, casse) decalerait toutes les positions.
 */
function extraireEmpan(
  transcription: string | undefined,
  proposition: PropositionEtude,
): string | null {
  const { empan_debut, empan_fin, ancree } = proposition;
  if (transcription === undefined || !ancree) return null;
  if (empan_debut === null || empan_fin === null) return null;
  const max = transcription.length;
  const debut = Math.max(0, Math.min(empan_debut, max));
  const fin = Math.max(debut, Math.min(empan_fin, max));
  return fin > debut ? transcription.slice(debut, fin) : null;
}

/** L'option de la grille correspondant a une decision prise. */
function optionDe(
  type: TypeProposition,
  decision: string,
): OptionDecisionEtendue | null {
  return GRILLES[type].find((option) => option.valeur === decision) ?? null;
}

/* ------------------------------------------------------------------ */
/*  PanneauLateralRevue                                                */
/* ------------------------------------------------------------------ */

export interface PanneauLateralRevueProps {
  propositions: readonly PropositionEtude[];
  decisions: Readonly<Record<string, string>>;
  /** Voir l'en-tete : facultative, elle n'active que le depliage de l'extrait. */
  transcription?: string;
  onDecider: (
    id: string,
    decision: string,
    options?: OptionsDecisionEtendues,
  ) => Promise<void>;
  onSurvol: (proposition: PropositionEtude | null) => void;
  replie: boolean;
  onReplier: (replie: boolean) => void;
}

export default function PanneauLateralRevue({
  propositions,
  decisions,
  transcription,
  onDecider,
  onSurvol,
  replie,
  onReplier,
}: PanneauLateralRevueProps) {
  const [idActif, setIdActif] = useState<string | null>(null);
  // Ids decides dont la carte glisse encore hors de la pile : elle y reste le
  // temps du mouvement, pas une image de plus.
  const [sortantes, setSortantes] = useState<readonly string[]>([]);

  const listeRef = useRef<HTMLDivElement>(null);
  const minuteries = useRef<Set<number>>(new Set());
  const survolRef = useRef(onSurvol);

  // Le nettoyage au demontage ne peut pas dependre de `onSurvol` sans se
  // rejouer a chaque rendu du parent : on garde la derniere reference a part.
  useEffect(() => {
    survolRef.current = onSurvol;
  }, [onSurvol]);

  useEffect(() => {
    const enCours = minuteries.current;
    return () => {
      // Un demontage en pleine sortie laisserait des minuteries orphelines qui
      // reveilleraient un composant disparu.
      enCours.forEach((id) => window.clearTimeout(id));
      enCours.clear();
      // Le surlignage du compte-rendu est allume par CE panneau : s'il
      // disparait pendant un survol, plus rien ne viendrait l'eteindre.
      survolRef.current(null);
    };
  }, []);

  // Replier emporte les cartes d'un coup, sans qu'aucune n'emette mouseleave
  // ni blur : le surlignage allume dans le compte-rendu n'aurait plus personne
  // pour l'eteindre, et resterait sur le texte tant que la revue est de cote.
  // Le repli pouvant etre decide par le parent, c'est le seul endroit qui le
  // rattrape a coup sur ; l'effet ne fait que rendre au parent l'etat de son
  // surlignage, sans toucher a l'etat local.
  useEffect(() => {
    if (replie) survolRef.current(null);
  }, [replie]);

  const differer = useCallback((action: () => void, delai: number): void => {
    const id = window.setTimeout(() => {
      minuteries.current.delete(id);
      action();
    }, delai);
    minuteries.current.add(id);
  }, []);

  /** Amene le praticien a la premiere carte encore a decider. */
  const focaliserSuivante = useCallback((): void => {
    const carte = listeRef.current?.querySelector<HTMLElement>(
      '[data-a-decider="true"]',
    );
    if (!carte) return;
    // preventScroll puis scrollIntoView : le navigateur sauterait sinon d'un
    // bond au lieu d'amener la carte au plus court.
    carte.focus({ preventScroll: true });
    carte.scrollIntoView({ block: "nearest" });
  }, []);

  /** Survol ou focus d'une carte : le parent surligne le passage vise. */
  const activer = useCallback(
    (id: string | null): void => {
      setIdActif(id);
      onSurvol(
        id === null ? null : (propositions.find((p) => p.id === id) ?? null),
      );
    },
    [onSurvol, propositions],
  );

  /**
   * Mettre la revue de cote, ou la ramener.
   *
   * Le repli est demande au parent — c'est lui qui rend la largeur a l'editeur
   * — mais la carte survolee au moment du clic doit s'eteindre ICI : elle va
   * disparaitre sans emettre mouseleave, et laisserait sinon un surlignage
   * orphelin dans le compte-rendu.
   */
  const replier = useCallback(
    (valeur: boolean): void => {
      if (valeur) activer(null);
      onReplier(valeur);
    },
    [activer, onReplier],
  );

  const decider = useCallback(
    async (
      id: string,
      decision: string,
      options?: OptionsDecisionEtendues,
    ): Promise<void> => {
      // La mesure part d'abord et sans attendre : une animation depend d'un
      // rendu actif, elle ne doit jamais s'interposer devant l'enregistrement.
      await onDecider(id, decision, options);

      // Le surlignage part avec la carte. Une carte qui disparait sous le
      // curseur n'emet ni mouseleave ni blur : sans cette extinction, le
      // compte-rendu resterait surligne sur une ligne deja tranchee, et la
      // carte suivante prendrait le focus sur un passage qui n'est pas le sien.
      activer(null);

      if (mouvementReduit()) {
        // Sortie instantanee : la carte est deja partie au prochain rendu.
        differer(focaliserSuivante, 0);
        return;
      }
      setSortantes((precedentes) => [...precedentes, id]);
      differer(() => {
        setSortantes((precedentes) => precedentes.filter((x) => x !== id));
        focaliserSuivante();
      }, DUREE_SORTIE_MS);
    },
    [onDecider, activer, differer, focaliserSuivante],
  );

  const enSortie = useMemo(() => new Set(sortantes), [sortantes]);

  const aDecider = useMemo(
    () =>
      propositions.filter(
        (p) => decisions[p.id] === undefined || enSortie.has(p.id),
      ),
    [propositions, decisions, enSortie],
  );

  const total = propositions.length;
  const decidees = useMemo(
    () => propositions.filter((p) => decisions[p.id] !== undefined).length,
    [propositions, decisions],
  );
  const restantes = total - decidees;

  /* ---------------------------------------------------------------- */
  /*  Replie : une lisiere, pas une disparition                        */
  /* ---------------------------------------------------------------- */

  // Deux rendus distincts plutot qu'une largeur animee : faire glisser la
  // largeur ecrase le contenu pendant toute la transition, et une colonne de
  // cartes qui se plisse coute plus cher a lire qu'un basculement net.
  if (replie) {
    return (
      <aside className="flex h-full w-12 shrink-0 flex-col border-l bg-card/30">
        <button
          type="button"
          onClick={() => replier(false)}
          title="Rouvrir la revue des propositions"
          aria-label={
            restantes > 0
              ? `Rouvrir la revue : ${restantes} proposition${restantes > 1 ? "s" : ""} a decider`
              : "Rouvrir la revue des propositions"
          }
          className="flex flex-1 flex-col items-center gap-3 px-1 py-3 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        >
          <PanelRightOpen className="h-4 w-4 shrink-0" />
          {/* Le compte reste visible replie : sans lui, mettre le panneau de
              cote revient a oublier qu'il reste des decisions a prendre. */}
          {total > 0 && (
            <span
              className={cn(
                "flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full px-1 text-[0.7rem] font-bold",
                restantes > 0
                  ? "bg-warning/15 text-warning"
                  : "bg-success/15 text-success",
              )}
            >
              {restantes > 0 ? restantes : <Check className="h-3 w-3" />}
            </span>
          )}
          <span className="text-[0.7rem] font-semibold tracking-wide [writing-mode:vertical-rl]">
            Revue
          </span>
        </button>
      </aside>
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Deploye                                                          */
  /* ---------------------------------------------------------------- */

  return (
    <aside
      aria-label="Revue des propositions"
      className="flex h-full min-h-0 w-[340px] shrink-0 flex-col overflow-hidden border-l bg-card/30 lg:w-[380px]"
    >
      <header className="flex shrink-0 flex-col gap-2.5 border-b px-3 py-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ListChecks className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold">Revue</div>
            <div className="truncate text-xs text-muted-foreground">
              MARC propose, vous decidez
            </div>
          </div>
          {/* Mettre de cote sans perdre : le praticien qui veut ecrire doit
              pouvoir liberer la largeur en un clic, et la retrouver de meme. */}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-muted-foreground"
            onClick={() => replier(true)}
            title="Mettre la revue de cote"
            aria-label="Mettre la revue de cote"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </div>

        {total > 0 && (
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {restantes > 0 ? (
                <Badge variant="warning" className="gap-1.5 text-[0.7rem]">
                  <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                  {restantes} a decider
                </Badge>
              ) : (
                // text-success : le jeton success-foreground est blanc,
                // illisible sur le fond tres clair de la pastille.
                <Badge
                  variant="success"
                  className="gap-1.5 text-[0.7rem] text-success"
                >
                  <Check className="h-3 w-3" />
                  Toutes decidees
                </Badge>
              )}
              <span className="text-[0.65rem] text-muted-foreground">
                {decidees} / {total}
              </span>
            </div>
            {/* La barre est la preuve que la tache diminue : sans elle, une
                pile de vingt cartes parait interminable. */}
            <div className="h-1.5 w-full rounded-full bg-muted">
              <div
                className="h-1.5 rounded-full bg-primary transition-all duration-500 motion-reduce:transition-none"
                style={{ width: `${(decidees / total) * 100}%` }}
              />
            </div>
          </div>
        )}
      </header>

      {restantes > 0 && (
        <p className="flex shrink-0 items-center gap-1.5 border-b bg-muted/30 px-3 py-1.5 text-[0.65rem] leading-relaxed text-muted-foreground">
          <Keyboard className="h-3 w-3 shrink-0" />
          <span className="min-w-0">
            Tab passe d'une carte a l'autre, la lettre inscrite sur un choix le
            prend.
          </span>
        </p>
      )}

      <div
        ref={listeRef}
        // overflow-x-hidden : la carte qui sort glisse vers la droite et ne
        // doit jamais faire apparaitre de barre horizontale.
        className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto overflow-x-hidden p-3 scrollbar-thin"
      >
        {total === 0 ? (
          <p className="px-1 py-6 text-center text-sm text-muted-foreground">
            Aucune proposition a decider pour ce cas.
          </p>
        ) : aDecider.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-1 py-6 text-center">
            <CheckCircle2 className="h-7 w-7 text-success" />
            <p className="text-sm font-semibold text-foreground">
              La pile est vide
            </p>
            <p className="text-xs text-muted-foreground">
              Toutes les propositions ont recu votre decision.
            </p>
          </div>
        ) : (
          aDecider.map((proposition) => (
            <PropositionCarte
              key={proposition.id}
              proposition={proposition}
              grille={GRILLES[proposition.type]}
              causes={CAUSES}
              natures={NATURES}
              // Pas de verbatim a demeure ici : l'extrait se deplie sur la
              // carte, et seulement quand un passage l'ancre vraiment.
              extraitDictee={extraireEmpan(transcription, proposition)}
              actif={idActif === proposition.id}
              sortie={
                enSortie.has(proposition.id)
                  ? optionDe(proposition.type, decisions[proposition.id])
                  : null
              }
              revenue={false}
              onActiver={activer}
              onDecider={decider}
            />
          ))
        )}
      </div>

      <footer className="shrink-0 border-t p-3">
        {restantes > 0 ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 w-full"
            onClick={focaliserSuivante}
          >
            Aller a la suivante
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        ) : (
          <div className="flex items-center gap-2.5 rounded-lg border border-success/30 bg-success/5 p-2.5">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
            <p className="min-w-0 flex-1 text-xs leading-relaxed text-foreground">
              {total === 0
                ? "Rien a decider sur ce cas."
                : "Toutes les propositions sont decidees."}
            </p>
          </div>
        )}
      </footer>
    </aside>
  );
}
