/**
 * Revue des propositions : le verbatim, le compte-rendu propose, et la pile de
 * decisions du praticien.
 *
 * ------------------------------------------------------------------
 *  CONTRAT DE PROPS
 * ------------------------------------------------------------------
 *
 *  transcription         La chaine EXACTE envoyee au backend. Les empans sont
 *                        des offsets dedans : ne jamais la normaliser.
 *  crPropose             Le compte-rendu redige par MARC, en lecture seule.
 *  propositions          Miroir de `PropositionAffichee` (routes_etude.py).
 *  decisions             id de proposition -> valeur de decision prise. Le
 *                        parent ne stocke QUE la valeur ; le detail saisi
 *                        (valeur retenue, cause) est memorise ici, le temps de
 *                        la revue, pour l'afficher sur la carte rangee.
 *  onDecider             Enregistre la decision cote serveur. DOIT rejeter en
 *                        cas d'echec : la carte affiche alors l'erreur et reste
 *                        dans la pile. Aucune animation n'attend cet appel.
 *  onAnnuler             Retire la decision : le parent l'ote de `decisions`,
 *                        la carte revient dans la pile active. Un changement
 *                        d'avis n'est pas un incident, c'est une mesure : le
 *                        parent est libre de le journaliser.
 *  onJustificationOuverte  Le praticien a deplie les motifs des relecteurs.
 *                        Evenement de telemetrie pur, sans effet sur l'ecran.
 *  onAbandonner          La porte de sortie de l'etude.
 *  sousExtraction        Le dossier produit trop peu a valider : on le dit.
 *
 * ------------------------------------------------------------------
 *  CE QUE CE PANNEAU GARANTIT
 * ------------------------------------------------------------------
 *
 *  - Une decision fait PARTIR la carte : elle glisse hors de la pile active et
 *    va se ranger dans la zone des decidees. La pile diminue a vue d'oeil,
 *    sinon la tache parait interminable.
 *  - Toute decision est annulable depuis la carte rangee. Sans retour en
 *    arriere, la peur du clic de travers ralentit tout le monde.
 *  - Le clavier suffit : une lettre par choix, et le focus saute a la carte
 *    suivante des que la precedente est partie.
 *  - L'enregistrement serveur part AVANT l'animation, jamais apres : on anime
 *    l'affichage, jamais la mesure.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  CheckCircle2,
  ChevronRight,
  FileText,
  Info,
  Keyboard,
  ListChecks,
  Lock,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import BoutonAbandon from "./BoutonAbandon";
import PileDecidees from "./PileDecidees";
import PropositionCarte from "./PropositionCarte";
import VerbatimPanel from "./VerbatimPanel";

/* ------------------------------------------------------------------ */
/*  Types — miroir du contrat /etude/dossiers                          */
/* ------------------------------------------------------------------ */

export type TypeProposition = "restitution" | "code" | "completude";

export interface PropositionEtude {
  id: string;
  type: TypeProposition;
  sous_type: string | null;
  valeur_proposee: string;
  /** Offset de caractere dans la transcription. Nul si rien ne l'ancre. */
  empan_debut: number | null;
  /** Offset de caractere dans la transcription. Nul si rien ne l'ancre. */
  empan_fin: number | null;
  /**
   * Faux quand aucun passage de la dictee ne soutient l'assertion. Ce sont les
   * CANDIDATES HALLUCINATIONS, les propositions les plus precieuses de l'etude.
   * L'interface doit le dire franchement au lieu de faire comme si l'empan
   * avait ete perdu.
   */
  ancree: boolean;
  chemin: string | null;
  /**
   * Nombre de relecteurs ayant retrouve le passage, sur le nombre de
   * relecteurs. C'est la confiance AFFICHABLE : un decompte se verifie, un
   * 0,73 ne se verifie pas. Nul quand le college n'a pas ete depouille.
   */
  voix_pour: number | null;
  voix_total: number | null;
  /**
   * Les motifs REELLEMENT ecrits par les relecteurs, une phrase par lentille.
   * Ils ne sont pas rediges pour le praticien : c'est la trace du jugement.
   */
  justifications: readonly string[];
}

export interface OptionsDecision {
  valeurRetenue?: string;
  causeErreur?: string;
  justifOuverte?: boolean;
  justifDureeMs?: number;
}

export type TonDecision = "valide" | "nuance" | "rejet" | "neutre";

export interface OptionDecision {
  /** Valeur envoyee au backend : hors grille, il refuse en 400. */
  valeur: string;
  libelle: string;
  aide?: string;
  ton: TonDecision;
  /**
   * Touche unique, en majuscule, qui decide la carte au clavier. Choisie
   * mnemonique et distincte DANS SA GRILLE : deux grilles peuvent reutiliser
   * la meme lettre, elles ne sont jamais affichees ensemble.
   */
  raccourci: string;
  /** Ouvre un champ pour recueillir la valeur retenue. */
  saisieValeur?: boolean;
  /** Ouvre la question facultative sur la cause de l'erreur. */
  demandeCause?: boolean;
}

export interface CauseErreur {
  valeur: string;
  libelle: string;
}

/** Une carte deja decidee, telle que la pile laterale l'affiche. */
export interface CarteRangee {
  id: string;
  valeurProposee: string;
  libelleDecision: string;
  ton: TonDecision;
  /** Valeur corrigee saisie par le praticien, quand il y en a une. */
  valeurRetenue: string | null;
  /** Libelle de la cause d'erreur choisie, quand il y en a une. */
  libelleCause: string | null;
}

export interface RevuePanelProps {
  transcription: string;
  crPropose: string;
  propositions: readonly PropositionEtude[];
  decisions: Readonly<Record<string, string>>;
  onDecider: (
    id: string,
    decision: string,
    options?: OptionsDecision,
  ) => Promise<void>;
  onAnnuler: (id: string) => Promise<void>;
  onJustificationOuverte: (id: string) => void;
  onAbandonner: (motif: string) => Promise<void>;
  sousExtraction: boolean;
}

/* ------------------------------------------------------------------ */
/*  Les trois grilles de decision                                      */
/* ------------------------------------------------------------------ */

// Les trois grilles sont etanches : melanger leurs valeurs fausserait un taux
// publie, c'est pourquoi elles sont indexees par le type de la proposition et
// jamais fusionnees. Les raccourcis suivent le mot du libelle (Conforme,
// Modifier, Non dit, Hors sujet...) pour se retenir sans les relire.
const GRILLES: Record<TypeProposition, readonly OptionDecision[]> = {
  restitution: [
    {
      valeur: "conforme",
      libelle: "Conforme",
      aide: "je valide tel quel",
      ton: "valide",
      raccourci: "C",
    },
    {
      valeur: "corrige",
      libelle: "A corriger",
      aide: "juste sur le fond",
      ton: "nuance",
      raccourci: "M",
      saisieValeur: true,
      demandeCause: true,
    },
    {
      valeur: "non_dicte",
      libelle: "Je n'ai pas dit ca",
      ton: "rejet",
      raccourci: "N",
      demandeCause: true,
    },
    {
      valeur: "hors_sujet",
      libelle: "Hors sujet",
      ton: "neutre",
      raccourci: "H",
    },
  ],
  code: [
    { valeur: "juste", libelle: "Code juste", ton: "valide", raccourci: "J" },
    {
      valeur: "corrige",
      libelle: "A corriger",
      ton: "nuance",
      raccourci: "M",
      saisieValeur: true,
      demandeCause: true,
    },
    {
      valeur: "je_ne_sais_pas",
      libelle: "Je ne sais pas",
      ton: "neutre",
      raccourci: "S",
    },
  ],
  completude: [
    {
      valeur: "pertinent_ajoute",
      libelle: "Pertinent, je l'ajoute",
      ton: "valide",
      raccourci: "A",
    },
    {
      valeur: "pertinent_non_retenu",
      libelle: "Pertinent, mais je ne le mets pas",
      ton: "nuance",
      raccourci: "S",
    },
    {
      valeur: "non_pertinent",
      libelle: "Pas pertinent ici",
      ton: "neutre",
      raccourci: "N",
    },
  ],
};

const CAUSES: readonly CauseErreur[] = [
  { valeur: "transcription", libelle: "La transcription a mal compris" },
  { valeur: "interpretation", libelle: "L'interpretation est fausse" },
];

/* ------------------------------------------------------------------ */
/*  Rythme des mouvements                                              */
/* ------------------------------------------------------------------ */

/** Duree de la sortie d'une carte. Assez pour etre lue, jamais pour attendre. */
const DUREE_SORTIE_MS = 200;

/** Duree du signal d'une carte revenue dans la pile apres annulation. */
const DUREE_RETOUR_MS = 900;

/**
 * Le praticien a demande a ne pas etre anime.
 *
 * Relu a chaque decision plutot que mis en cache : le reglage systeme peut
 * changer pendant la revue, et une carte qui reste bloquee en transition
 * serait un defaut bien pire que l'absence d'animation.
 */
function mouvementReduit(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* ------------------------------------------------------------------ */
/*  Detail d'une decision, memorise le temps de la revue                */
/* ------------------------------------------------------------------ */

interface DetailDecision {
  valeurRetenue: string | null;
  causeErreur: string | null;
  /** Ordre de rangement : la derniere decidee se pose en haut de la pile. */
  rang: number;
}

/** L'option de la grille correspondant a une decision prise. */
function optionDe(
  type: TypeProposition,
  decision: string,
): OptionDecision | null {
  return GRILLES[type].find((option) => option.valeur === decision) ?? null;
}

/** La ligne affichee dans la pile des decidees. */
function construireRangee(
  proposition: PropositionEtude,
  decision: string,
  detail: DetailDecision | null,
): CarteRangee {
  const option = optionDe(proposition.type, decision);
  const cause = CAUSES.find((c) => c.valeur === detail?.causeErreur);
  return {
    id: proposition.id,
    valeurProposee: proposition.valeur_proposee,
    libelleDecision: option?.libelle ?? decision,
    ton: option?.ton ?? "neutre",
    valeurRetenue: detail?.valeurRetenue ?? null,
    libelleCause: cause?.libelle ?? null,
  };
}

/* ------------------------------------------------------------------ */
/*  Compte-rendu propose — lecture seule                               */
/* ------------------------------------------------------------------ */

/**
 * Les titres de section du CR sont ecrits **__TITRE__** : on les ramene a des
 * titres Markdown pour que la revue n'affiche jamais de marqueurs bruts.
 */
function preparerCr(md: string): string {
  return md
    .replace(/\*\*__(.+?)__\*\*/g, "\n\n## $1\n")
    .replace(/__(.+?)__/g, "\n\n## $1\n")
    .replace(/([^\n])\n(#{1,3} )/g, "$1\n\n$2");
}

function PanneauCr({ crPropose }: { crPropose: string }) {
  const contenu = useMemo(() => preparerCr(crPropose), [crPropose]);

  return (
    <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm">
      <header className="flex shrink-0 items-center gap-2.5 border-b px-4 py-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FileText className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">Compte-rendu propose</div>
          <div className="truncate text-xs text-muted-foreground">
            Ce que MARC a redige a partir de la dictee
          </div>
        </div>
      </header>
      <div className="max-h-[22rem] flex-1 overflow-auto px-4 py-3 scrollbar-thin xl:max-h-none">
        {crPropose.trim() ? (
          <div className="report-typography">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{contenu}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Aucun compte-rendu propose pour ce cas.
          </p>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  RevuePanel                                                         */
/* ------------------------------------------------------------------ */

export default function RevuePanel({
  transcription,
  crPropose,
  propositions,
  decisions,
  onDecider,
  onAnnuler,
  onJustificationOuverte,
  onAbandonner,
  sousExtraction,
}: RevuePanelProps) {
  const [idActif, setIdActif] = useState<string | null>(null);
  // Ids decides dont la carte glisse encore hors de la pile active : elle y
  // reste le temps du mouvement, pas une image de plus.
  const [sortantes, setSortantes] = useState<readonly string[]>([]);
  const [revenue, setRevenue] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, DetailDecision>>({});
  const [annulationEnCours, setAnnulationEnCours] = useState<string | null>(null);
  const [erreurAnnulation, setErreurAnnulation] = useState<string | null>(null);

  const listeRef = useRef<HTMLDivElement>(null);
  const rangCourant = useRef(0);
  const minuteries = useRef<Set<number>>(new Set());

  // Un demontage en pleine sortie laisserait des minuteries orphelines qui
  // reveilleraient un composant disparu.
  useEffect(() => {
    const enCours = minuteries.current;
    return () => {
      enCours.forEach((id) => window.clearTimeout(id));
      enCours.clear();
    };
  }, []);

  const differer = useCallback((action: () => void, delai: number): void => {
    const id = window.setTimeout(() => {
      minuteries.current.delete(id);
      action();
    }, delai);
    minuteries.current.add(id);
  }, []);

  /** Donne le focus a la premiere carte repondant au selecteur. */
  const focaliser = useCallback((selecteur: string): void => {
    const carte = listeRef.current?.querySelector<HTMLElement>(selecteur);
    if (!carte) return;
    // preventScroll puis scrollIntoView : le navigateur sauterait sinon d'un
    // bond au lieu d'amener la carte au plus court.
    carte.focus({ preventScroll: true });
    carte.scrollIntoView({ block: "nearest" });
  }, []);

  const focaliserSuivante = useCallback((): void => {
    focaliser('[data-a-decider="true"]');
  }, [focaliser]);

  // Une carte qui revient reprend le focus : sans cela il retombe sur le corps
  // de page, et le praticien doit retraverser l'ecran a la souris.
  useEffect(() => {
    if (revenue === null) return;
    focaliser(`[data-proposition-id="${revenue}"]`);
  }, [revenue, focaliser]);

  const decider = useCallback(
    async (
      id: string,
      decision: string,
      options?: OptionsDecision,
    ): Promise<void> => {
      // La mesure part d'abord et sans attendre : une animation depend d'un
      // rendu actif, elle ne doit jamais s'interposer devant l'enregistrement.
      await onDecider(id, decision, options);

      rangCourant.current += 1;
      const rang = rangCourant.current;
      setDetails((precedents) => ({
        ...precedents,
        [id]: {
          valeurRetenue: options?.valeurRetenue ?? null,
          causeErreur: options?.causeErreur ?? null,
          rang,
        },
      }));

      if (mouvementReduit()) {
        // Sortie instantanee : la carte est deja rangee au prochain rendu.
        differer(focaliserSuivante, 0);
        return;
      }
      setSortantes((precedentes) => [...precedentes, id]);
      differer(() => {
        setSortantes((precedentes) => precedentes.filter((x) => x !== id));
        focaliserSuivante();
      }, DUREE_SORTIE_MS);
    },
    [onDecider, differer, focaliserSuivante],
  );

  const annuler = useCallback(
    async (id: string): Promise<void> => {
      setAnnulationEnCours(id);
      setErreurAnnulation(null);
      try {
        await onAnnuler(id);
        setDetails((precedents) => {
          const suite = { ...precedents };
          delete suite[id];
          return suite;
        });
        setRevenue(id);
        differer(
          () => setRevenue((courant) => (courant === id ? null : courant)),
          DUREE_RETOUR_MS,
        );
      } catch {
        setErreurAnnulation("Annulation non enregistree. Reessayez.");
      } finally {
        setAnnulationEnCours(null);
      }
    },
    [onAnnuler, differer],
  );

  const enSortie = useMemo(() => new Set(sortantes), [sortantes]);

  const aDecider = useMemo(
    () =>
      propositions.filter(
        (p) => decisions[p.id] === undefined || enSortie.has(p.id),
      ),
    [propositions, decisions, enSortie],
  );

  const rangees = useMemo<CarteRangee[]>(() => {
    const decidees = propositions.filter(
      (p) => decisions[p.id] !== undefined && !enSortie.has(p.id),
    );
    // La derniere rangee se pose en haut : le praticien voit ou sa carte a
    // atterri au lieu de la chercher au milieu de la liste.
    decidees.sort(
      (a, b) => (details[b.id]?.rang ?? 0) - (details[a.id]?.rang ?? 0),
    );
    return decidees.map((p) =>
      construireRangee(p, decisions[p.id], details[p.id] ?? null),
    );
  }, [propositions, decisions, enSortie, details]);

  const total = propositions.length;
  const decidees = useMemo(
    () => propositions.filter((p) => decisions[p.id] !== undefined).length,
    [propositions, decisions],
  );
  const restantes = total - decidees;
  const verrouille = restantes > 0;

  const active = useMemo(
    () => propositions.find((p) => p.id === idActif) ?? null,
    [propositions, idActif],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto scrollbar-thin xl:overflow-hidden">
      <header className="flex shrink-0 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-base font-bold tracking-tight">
              Revue des propositions
            </h2>
            {total > 0 &&
              (verrouille ? (
                <Badge variant="warning" className="gap-1.5 text-[0.7rem]">
                  <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                  {restantes} a decider
                </Badge>
              ) : (
                // text-success : le jeton success-foreground est blanc, illisible
                // sur le fond tres clair de la pastille.
                <Badge
                  variant="success"
                  className="gap-1.5 text-[0.7rem] text-success"
                >
                  <Check className="h-3 w-3" />
                  Toutes decidees
                </Badge>
              ))}
          </div>
          <BoutonAbandon onAbandonner={onAbandonner} />
        </div>

        {total > 0 && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[0.65rem] text-muted-foreground">
              <span>
                {decidees} / {total} decidee{decidees > 1 ? "s" : ""}
              </span>
              <span>{Math.round((decidees / total) * 100)}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted">
              <div
                className="h-1.5 rounded-full bg-primary transition-all duration-500 motion-reduce:transition-none"
                style={{ width: `${(decidees / total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Sous-extraction : ce n'est pas une panne a dramatiser, mais taire la
            brievete de la liste laisserait croire que tout a ete verifie. */}
        {sousExtraction && (
          <div className="flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              Peu d'elements ont pu etre extraits de cette dictee : la liste
              ci-dessous ne couvre pas tout le compte-rendu. Relisez-le en
              entier, l'absence de proposition ne vaut pas verification.
            </span>
          </div>
        )}
      </header>

      {/* Les trois panneaux restent visibles ensemble : comparer sans rien
          perdre de vue est la condition pour decider au lieu de valider en bloc. */}
      <div className="grid min-w-0 gap-4 lg:grid-cols-2 xl:min-h-0 xl:flex-1 xl:grid-cols-3">
        <VerbatimPanel
          className="min-h-0"
          transcription={transcription}
          // Les offsets partent tels quels, sans coercition : c'est `visee`
          // qui distingue "aucune carte survolee" de "carte survolee mais non
          // ancree". Forcer les offsets a zero melangeait les deux etats.
          visee={active !== null}
          empanDebut={active?.empan_debut ?? null}
          empanFin={active?.empan_fin ?? null}
        />

        <PanneauCr crPropose={crPropose} />

        <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm lg:col-span-2 xl:col-span-1">
          <header className="flex shrink-0 items-center gap-2.5 border-b px-4 py-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ListChecks className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">
                Propositions{total > 0 && ` (${total})`}
              </div>
              <div className="truncate text-xs text-muted-foreground">
                MARC propose, vous decidez
              </div>
            </div>
          </header>

          {restantes > 0 && (
            <p className="flex shrink-0 items-center gap-1.5 border-b bg-muted/30 px-4 py-1.5 text-[0.65rem] leading-relaxed text-muted-foreground">
              <Keyboard className="h-3 w-3 shrink-0" />
              <span className="min-w-0">
                Tab passe d'une carte a l'autre, la lettre inscrite sur un choix
                le prend.
              </span>
            </p>
          )}

          {/* Sous xl, la section occupe toute la largeur : la pile des rangees
              se met vraiment sur le cote. En colonne etroite elle passe
              dessous, toujours repliable. */}
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 md:flex-row xl:flex-col">
            <div
              ref={listeRef}
              // overflow-x-hidden : la carte qui sort glisse vers la droite et
              // ne doit jamais faire apparaitre de barre horizontale.
              className="grid max-h-[30rem] flex-1 content-start items-start gap-2.5 overflow-y-auto overflow-x-hidden scrollbar-thin lg:grid-cols-2 xl:max-h-none xl:grid-cols-1"
            >
              {total === 0 ? (
                <p className="px-1 py-6 text-center text-sm text-muted-foreground lg:col-span-2 xl:col-span-1">
                  Aucune proposition a decider pour ce cas.
                </p>
              ) : aDecider.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-1 py-6 text-center lg:col-span-2 xl:col-span-1">
                  <CheckCircle2 className="h-7 w-7 text-success" />
                  <p className="text-sm font-semibold text-foreground">
                    La pile est vide
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Toutes les propositions sont rangees. Vous pouvez encore
                    revenir sur chacune d'elles.
                  </p>
                </div>
              ) : (
                aDecider.map((proposition) => (
                  <PropositionCarte
                    key={proposition.id}
                    proposition={proposition}
                    grille={GRILLES[proposition.type]}
                    causes={CAUSES}
                    actif={idActif === proposition.id}
                    sortie={
                      enSortie.has(proposition.id)
                        ? optionDe(proposition.type, decisions[proposition.id])
                        : null
                    }
                    revenue={revenue === proposition.id}
                    onActiver={setIdActif}
                    onDecider={decider}
                    onJustificationOuverte={onJustificationOuverte}
                  />
                ))
              )}
            </div>

            {rangees.length > 0 && (
              <PileDecidees
                className="max-h-[14rem] shrink-0 md:max-h-[30rem] md:w-60 xl:max-h-[14rem] xl:w-full"
                cartes={rangees}
                annulationEnCours={annulationEnCours}
                erreur={erreurAnnulation}
                onAnnuler={(id) => void annuler(id)}
              />
            )}
          </div>

          <footer className="shrink-0 border-t p-3">
            {verrouille ? (
              <div className="flex flex-wrap items-center gap-2.5 rounded-lg border border-warning/30 bg-warning/5 p-2.5">
                <Lock className="h-4 w-4 shrink-0 text-warning" />
                <p className="min-w-0 flex-1 text-xs leading-relaxed text-foreground">
                  Export verrouille : {restantes} proposition
                  {restantes > 1 ? "s" : ""} attend
                  {restantes > 1 ? "ent" : ""} votre decision.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-9"
                  onClick={focaliserSuivante}
                >
                  Voir la suivante
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2.5 rounded-lg border border-success/30 bg-success/5 p-2.5">
                <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                <p className="min-w-0 flex-1 text-xs leading-relaxed text-foreground">
                  {total === 0
                    ? "Rien a decider : l'export du compte-rendu est ouvert."
                    : "Toutes les propositions sont decidees : l'export du compte-rendu est debloque."}
                </p>
              </div>
            )}
          </footer>
        </section>
      </div>
    </div>
  );
}
