import { useRef, useState, type KeyboardEvent } from "react";
import {
  AudioLines,
  Check,
  ChevronRight,
  CircleSlash,
  MapPin,
  SearchX,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type {
  CauseErreur,
  OptionDecision,
  OptionsDecision,
  PropositionEtude,
  TonDecision,
  TypeProposition,
} from "./RevuePanel";

/* ------------------------------------------------------------------ */
/*  Grammaire visuelle                                                 */
/* ------------------------------------------------------------------ */

const TYPE_LIBELLE: Record<TypeProposition, string> = {
  restitution: "Restitution",
  code: "Codage",
  completude: "Completude",
};

// Bleu = ce qui a ete dit, ocre = ce qui manque, neutre = le codage : meme
// grammaire de couleur que le reste de l'application.
const TYPE_BARRE: Record<TypeProposition, string> = {
  restitution: "bg-primary/70",
  code: "bg-muted-foreground/60",
  completude: "bg-warning/70",
};

const TYPE_TEXTE: Record<TypeProposition, string> = {
  restitution: "text-primary",
  code: "text-muted-foreground",
  completude: "text-warning",
};

const CLASSES_TON: Record<TonDecision, string> = {
  valide: "border-success/40 text-success hover:bg-success/10 hover:text-success",
  nuance: "border-warning/40 text-warning hover:bg-warning/10 hover:text-warning",
  rejet:
    "border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive",
  neutre: "border-border text-muted-foreground",
};

const TEXTE_TON: Record<TonDecision, string> = {
  valide: "text-success",
  nuance: "text-warning",
  rejet: "text-destructive",
  neutre: "text-muted-foreground",
};

// Un choix de nature RETENU est rempli, pas seulement borde : c'est la seule
// reponse obligatoire du second temps, et en colonne etroite une bordure de
// plus ne se distingue pas du bouton d'a cote.
const CLASSES_NATURE_RETENUE: Record<TonDecision, string> = {
  valide:
    "border-success/50 bg-success/10 text-success hover:bg-success/15 hover:text-success",
  nuance:
    "border-warning/50 bg-warning/10 text-warning hover:bg-warning/15 hover:text-warning",
  rejet:
    "border-destructive/50 bg-destructive/10 text-destructive hover:bg-destructive/15 hover:text-destructive",
  neutre: "border-foreground/25 bg-muted text-foreground hover:bg-muted",
};

/* ------------------------------------------------------------------ */
/*  Nature d'une correction — ce qui separe l'erreur de l'ecriture     */
/* ------------------------------------------------------------------ */

/**
 * Ce que le praticien a change en corrigeant.
 *
 * Sans cette distinction, « je reformule a ma main » et « c'etait faux »
 * comptent pour la meme chose, et le taux publie melange une erreur de l'outil
 * avec le style d'un redacteur — deux mesures sans rapport.
 */
export interface NatureCorrection {
  /** Valeur envoyee au backend : hors grille, il refuse en 400. */
  valeur: string;
  libelle: string;
  /** La phrase du praticien, pas la definition : elle doit se lire sans effort. */
  aide: string;
  ton: TonDecision;
  /**
   * Seule une erreur de FOND appelle la question de la cause : demander la
   * cause d'une reformulation de style n'a pas de sens, et le backend refuse
   * cette combinaison en 400.
   */
  demandeCause: boolean;
}

/** Une option de grille, elargie a la question de la nature. */
export interface OptionDecisionEtendue extends OptionDecision {
  /**
   * Ouvre la question de la nature en tete du second temps. Laisse a faux, la
   * carte se comporte exactement comme avant : la vue plein ecran ne pose pas
   * cette question, le panneau lateral si.
   */
  demandeNature?: boolean;
}

/** Les options d'une decision, elargies a la nature de la correction. */
export interface OptionsDecisionEtendues extends OptionsDecision {
  natureCorrection?: string;
}

/* ------------------------------------------------------------------ */
/*  La confiance est un decompte, jamais un score                      */
/* ------------------------------------------------------------------ */

interface Decompte {
  pour: number;
  total: number;
}

/**
 * Le decompte des relecteurs, borne sur lui-meme.
 *
 * Nul quand le college n'a pas ete depouille : mieux vaut ne rien afficher
 * qu'un « 0 sur 0 » que personne ne sait interpreter.
 */
function decompteVoix(proposition: PropositionEtude): Decompte | null {
  const { voix_pour, voix_total } = proposition;
  if (voix_pour === null || voix_total === null || voix_total <= 0) return null;
  return {
    pour: Math.max(0, Math.min(voix_pour, voix_total)),
    total: voix_total,
  };
}

/**
 * Le decompte en toutes lettres.
 *
 * Jamais un pourcentage : « deux relecteurs sur trois ont retrouve ce passage »
 * se verifie en relisant la dictee, un 0,73 ne se verifie pas.
 */
function phraseVoix(compte: Decompte): string {
  if (compte.pour === 0) {
    return compte.total === 1
      ? "Le relecteur n'a pas retrouve ce passage dans votre dictee"
      : `Aucun des ${compte.total} relecteurs n'a retrouve ce passage dans votre dictee`;
  }
  if (compte.pour === 1) {
    return `1 relecteur sur ${compte.total} a retrouve ce passage dans votre dictee`;
  }
  return `${compte.pour} relecteurs sur ${compte.total} ont retrouve ce passage dans votre dictee`;
}

/**
 * Ce que dit une proposition qu'aucun passage de la dictee ne soutient.
 *
 * Pour une completude, l'absence est le SUJET : elle signale un element qui
 * manque, il serait absurde de le lui reprocher. Pour une restitution ou un
 * code, c'est une candidate hallucination : la question posee au praticien
 * n'est plus « est-ce fidele ? » mais « l'avez-vous dit ? ».
 */
function texteSansAppui(
  type: TypeProposition,
  compte: Decompte | null,
): string {
  if (type === "completude") {
    return "Cette proposition porte sur un element ABSENT de la dictee : c'est ce qu'elle vous signale, pas un defaut.";
  }
  if (compte) {
    return `${phraseVoix({ pour: 0, total: compte.total })} : l'avez-vous dit ?`;
  }
  return "Aucun passage de votre dictee ne soutient cette proposition : l'avez-vous dit ?";
}

/* ------------------------------------------------------------------ */
/*  Second temps : valeur retenue et cause (facultative)               */
/* ------------------------------------------------------------------ */

interface EtapeJustification {
  option: OptionDecisionEtendue;
  valeur: string;
  /** Nature de la correction, nulle tant que le praticien ne l'a pas dite. */
  nature: string | null;
  cause: string | null;
  /** Horodatage d'ouverture : sert a mesurer le temps de justification. */
  ouvertA: number;
}

interface PropositionCarteProps {
  proposition: PropositionEtude;
  /** La grille du type de cette proposition. Les trois sont etanches. */
  grille: readonly OptionDecisionEtendue[];
  causes: readonly CauseErreur[];
  /**
   * Les natures de correction proposees. Absentes, la question n'est jamais
   * posee : seule une grille qui porte `demandeNature` la declenche.
   */
  natures?: readonly NatureCorrection[];
  /**
   * Le passage exact de la dictee, pour un appelant qui n'affiche PAS le
   * verbatim en permanence. Nul quand rien n'ancre la proposition : la carte
   * le dit deja, il n'y a alors rien a deplier.
   */
  extraitDictee?: string | null;
  /** Vrai quand c'est cette carte qui pilote le surlignage du verbatim. */
  actif: boolean;
  /**
   * Non nul pendant la sortie : la carte quitte la pile avec cette decision.
   * Une carte deja rangee n'est plus rendue ici, elle vit dans PileDecidees.
   */
  sortie: OptionDecision | null;
  /** Vrai juste apres une annulation : la carte vient de revenir dans la pile. */
  revenue: boolean;
  onActiver: (id: string | null) => void;
  onDecider: (
    id: string,
    decision: string,
    options?: OptionsDecisionEtendues,
  ) => Promise<void>;
  /** Telemetrie du depliage des motifs : tous les appelants ne la mesurent pas. */
  onJustificationOuverte?: (id: string) => void;
}

/**
 * Une proposition et les boutons de SA grille. Le survol comme le focus
 * clavier remontent l'identifiant pour surligner l'empan correspondant, et une
 * lettre suffit a decider sans quitter le clavier.
 */
export default function PropositionCarte({
  proposition,
  grille,
  causes,
  natures,
  extraitDictee,
  actif,
  sortie,
  revenue,
  onActiver,
  onDecider,
  onJustificationOuverte,
}: PropositionCarteProps) {
  const [etape, setEtape] = useState<EtapeJustification | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [motifsOuverts, setMotifsOuverts] = useState(false);
  const [extraitOuvert, setExtraitOuvert] = useState(false);
  const carteRef = useRef<HTMLDivElement>(null);
  const champRef = useRef<HTMLTextAreaElement>(null);

  const compte = decompteVoix(proposition);
  const sansAppui = !proposition.ancree;
  const suspecte = sansAppui && proposition.type !== "completude";
  const partante = sortie !== null;

  // La question de la nature n'existe que si l'appelant l'a fournie ET que
  // l'option la demande : une grille sans natures se comporte comme avant.
  const natureRequise =
    etape !== null &&
    etape.option.demandeNature === true &&
    natures !== undefined &&
    natures.length > 0;
  const natureRetenue =
    etape === null
      ? null
      : (natures?.find((n) => n.valeur === etape.nature) ?? null);
  // La cause ne se pose que si la nature choisie l'appelle. Hors nature, on
  // retombe sur le comportement d'origine : l'option seule decide.
  const causeVisible =
    etape !== null &&
    etape.option.demandeCause === true &&
    (!natureRequise || natureRetenue?.demandeCause === true);

  const envoyer = async (valeur: string, options?: OptionsDecisionEtendues) => {
    setEnvoi(true);
    setErreur(null);
    try {
      await onDecider(proposition.id, valeur, options);
      setEtape(null);
    } catch {
      setErreur("Decision non enregistree. Reessayez.");
    } finally {
      setEnvoi(false);
    }
  };

  const choisir = (option: OptionDecisionEtendue) => {
    const ouvreNature =
      option.demandeNature === true &&
      natures !== undefined &&
      natures.length > 0;
    if (option.saisieValeur || option.demandeCause || ouvreNature) {
      setErreur(null);
      setEtape({
        option,
        // Pre-remplir evite de retaper une proposition juste sur le fond.
        valeur: option.saisieValeur ? proposition.valeur_proposee : "",
        nature: null,
        cause: null,
        ouvertA: Date.now(),
      });
      return;
    }
    void envoyer(option.valeur);
  };

  const choisirNature = (nature: NatureCorrection) => {
    if (!etape) return;
    setEtape({
      ...etape,
      nature: nature.valeur,
      // Passer de « c'etait faux » a « je reformule » doit OUBLIER la cause :
      // laissee en place, elle partirait avec une nature qui ne l'admet pas et
      // le backend refuserait la decision en 400.
      cause: nature.demandeCause ? etape.cause : null,
    });
    // Le geste suivant est d'ecrire la valeur retenue : y amener le curseur
    // evite un Tab a l'aveugle dans une colonne etroite.
    if (etape.option.saisieValeur) champRef.current?.focus();
  };

  const validerEtape = () => {
    if (!etape) return;
    const valeur = etape.valeur.trim();
    if (etape.option.saisieValeur && valeur.length === 0) return;
    // La nature n'est pas facultative : sans elle, la correction retombe dans
    // le tas indistinct que cet ecran est justement la pour separer.
    if (natureRequise && etape.nature === null) return;
    void envoyer(etape.option.valeur, {
      ...(etape.option.saisieValeur ? { valeurRetenue: valeur } : {}),
      ...(etape.nature !== null ? { natureCorrection: etape.nature } : {}),
      // La cause ne part que si la question a REELLEMENT ete posee a l'ecran.
      ...(causeVisible && etape.cause ? { causeErreur: etape.cause } : {}),
      // « Ouverte » = le second temps a bien ete presente au praticien ; la
      // duree mesure le temps qu'il y a passe, cause laissee vide ou non.
      justifOuverte: true,
      justifDureeMs: Date.now() - etape.ouvertA,
    });
  };

  /**
   * Referme le second temps et rend le focus a la carte.
   *
   * Sans ce retour, le focus tombe sur le corps de page avec le champ qui
   * disparait, et le praticien doit retraverser l'ecran a la souris.
   */
  const fermerEtape = () => {
    setEtape(null);
    carteRef.current?.focus({ preventScroll: true });
  };

  const basculerMotifs = () => {
    const ouverture = !motifsOuverts;
    setMotifsOuverts(ouverture);
    // Chaque ouverture est un evenement : c'est elle que la telemetrie compte,
    // pas l'etat courant du depliage.
    if (ouverture) onJustificationOuverte?.(proposition.id);
  };

  const surTouche = (evenement: KeyboardEvent<HTMLDivElement>) => {
    if (partante || envoi) return;
    // Echap est traite avant tout : c'est la seule touche qui n'ecrit rien, et
    // le second temps ouvre justement le focus DANS le champ de saisie.
    if (evenement.key === "Escape") {
      if (!etape) return;
      evenement.preventDefault();
      fermerEtape();
      return;
    }
    // Une frappe dans un champ de saisie appartient au champ, jamais a la
    // grille : sinon on ne peut plus ecrire « Conforme » dans une correction.
    const cible = evenement.target as HTMLElement;
    if (cible.tagName === "TEXTAREA" || cible.tagName === "INPUT") return;
    if (etape) return;
    if (evenement.metaKey || evenement.ctrlKey || evenement.altKey) return;
    const option = grille.find(
      (o) => o.raccourci === evenement.key.toUpperCase(),
    );
    if (!option) return;
    evenement.preventDefault();
    choisir(option);
  };

  return (
    <div
      ref={carteRef}
      // Le panneau parent s'appuie sur ces attributs pour amener le praticien
      // a la premiere carte non decidee, et pour ramener le focus sur une
      // carte revenue apres annulation.
      data-a-decider={partante ? undefined : "true"}
      data-proposition-id={proposition.id}
      role="group"
      aria-label={`Proposition ${TYPE_LIBELLE[proposition.type]}`}
      tabIndex={partante ? -1 : 0}
      onMouseEnter={() => onActiver(proposition.id)}
      onMouseLeave={() => onActiver(null)}
      onFocus={() => onActiver(proposition.id)}
      onBlur={() => onActiver(null)}
      onKeyDown={surTouche}
      className={cn(
        "rounded-lg border p-3 outline-none transition-all duration-200 ease-out",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "motion-reduce:transition-none",
        // Sans appui dans la dictee : le trait discontinu se voit avant meme
        // d'avoir lu le bandeau.
        sansAppui && "border-dashed",
        suspecte && "border-warning/60 bg-warning/[0.05]",
        actif && "border-primary/40 bg-primary/[0.03]",
        // Retour dans la pile : la carte se pose en evidence puis se calme.
        revenue &&
          "animate-fade-in border-primary bg-primary/[0.07] shadow-sm [animation-duration:200ms] motion-reduce:animate-none",
        // Sortie : elle part sur le cote, vers la pile des rangees.
        partante && "pointer-events-none translate-x-8 scale-[0.98] opacity-0",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "flex min-w-0 items-center gap-2 text-[0.7rem] font-bold uppercase tracking-wide",
            TYPE_TEXTE[proposition.type],
          )}
        >
          <span
            className={cn(
              "h-3.5 w-1 shrink-0 rounded-full",
              TYPE_BARRE[proposition.type],
            )}
          />
          <span className="truncate">{TYPE_LIBELLE[proposition.type]}</span>
        </span>
        {proposition.sous_type && (
          <Badge
            variant="secondary"
            className="shrink-0 px-1.5 py-0 text-[0.6rem]"
          >
            {proposition.sous_type}
          </Badge>
        )}
      </div>

      <p className="mt-1.5 break-words text-sm font-medium leading-relaxed text-foreground">
        {proposition.valeur_proposee}
      </p>

      {proposition.chemin && (
        <div className="mt-1.5 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
          <MapPin className="h-3 w-3 shrink-0" />
          <span className="truncate" title={proposition.chemin}>
            {proposition.chemin}
          </span>
        </div>
      )}

      {sansAppui ? (
        <div
          className={cn(
            "mt-2 flex items-start gap-1.5 rounded-md px-2 py-1.5 text-[0.7rem] leading-relaxed",
            suspecte
              ? "bg-warning/10 text-warning-foreground"
              : "bg-muted/60 text-muted-foreground",
          )}
        >
          {suspecte ? (
            <SearchX className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
          ) : (
            <CircleSlash className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          )}
          <span className="min-w-0">
            {texteSansAppui(proposition.type, compte)}
          </span>
        </div>
      ) : (
        compte && (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.7rem] text-muted-foreground">
            {/* Le decompte se lit d'un coup d'oeil avant meme la phrase. */}
            <span className="flex shrink-0 items-center gap-1">
              <Users className="h-3 w-3 shrink-0" />
              <span className="flex items-center gap-0.5" aria-hidden="true">
                {Array.from({ length: compte.total }, (_, rang) => (
                  <span
                    key={rang}
                    className={cn(
                      "h-1.5 w-1.5 rounded-full bg-current",
                      rang >= compte.pour && "opacity-25",
                    )}
                  />
                ))}
              </span>
            </span>
            <span className="min-w-0">{phraseVoix(compte)}</span>
          </div>
        )
      )}

      {/* Le passage dicte, a la demande. Un appelant qui montre deja le
          verbatim en permanence ne passe pas `extraitDictee` : le repeter sous
          la carte ferait lire deux fois la meme phrase. Ferme par defaut, car
          la question posee porte sur la proposition, pas sur la dictee. */}
      {!partante && extraitDictee && (
        <div className="mt-2">
          <button
            type="button"
            aria-expanded={extraitOuvert}
            onClick={() => setExtraitOuvert(!extraitOuvert)}
            className="inline-flex items-center gap-1 rounded-sm text-[0.7rem] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <ChevronRight
              className={cn(
                "h-3 w-3 shrink-0 transition-transform duration-150 motion-reduce:transition-none",
                extraitOuvert && "rotate-90",
              )}
            />
            <AudioLines className="h-3 w-3 shrink-0" />
            Ce que vous avez dicte
          </button>
          {extraitOuvert && (
            // Meme surlignage que le verbatim plein ecran : le praticien
            // reconnait le passage sans reapprendre un code couleur.
            <p className="mt-1.5 rounded-md bg-primary/[0.07] px-2.5 py-2 text-[0.7rem] leading-relaxed text-foreground ring-1 ring-primary/20">
              {extraitDictee}
            </p>
          )}
        </div>
      )}

      {/* Rien de focalisable dans une carte qui part : le focus s'y perdrait
          au moment meme ou elle disparait. */}
      {!partante && proposition.justifications.length > 0 && (
        <div className="mt-2">
          {/* Ferme par defaut : ouvert, le motif des relecteurs noierait la
              decision sous du texte que le praticien n'a pas demande. */}
          <button
            type="button"
            aria-expanded={motifsOuverts}
            onClick={basculerMotifs}
            className="inline-flex items-center gap-1 rounded-sm text-[0.7rem] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <ChevronRight
              className={cn(
                "h-3 w-3 shrink-0 transition-transform duration-150 motion-reduce:transition-none",
                motifsOuverts && "rotate-90",
              )}
            />
            Pourquoi cette proposition vous est soumise
          </button>
          {motifsOuverts && (
            <ul className="mt-1.5 space-y-1 rounded-md border border-border/60 bg-muted/30 px-2.5 py-2">
              {proposition.justifications.map((motif, rang) => (
                <li
                  key={rang}
                  className="flex items-start gap-1.5 text-[0.7rem] leading-relaxed text-muted-foreground"
                >
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" />
                  <span className="min-w-0 break-words">{motif}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {sortie ? (
        // La carte part en montrant ce qui vient d'etre enregistre : c'est la
        // derniere chose que le praticien lit avant qu'elle se range.
        <div className="mt-2.5 flex items-center gap-1.5 rounded-md bg-card px-2.5 py-2 text-xs">
          <Check className={cn("h-3.5 w-3.5 shrink-0", TEXTE_TON[sortie.ton])} />
          <span className="min-w-0 truncate font-semibold text-foreground">
            {sortie.libelle}
          </span>
        </div>
      ) : etape ? (
        <div className="mt-2.5 space-y-2.5 rounded-md border border-border/60 bg-card p-2.5">
          <p className="text-xs font-semibold text-foreground">
            {etape.option.libelle}
          </p>

          {/* La nature vient EN TETE : c'est elle qui decide de la suite du
              second temps, et elle seule est obligatoire. */}
          {natureRequise && natures && (
            <div className="space-y-1.5 rounded-md border border-border/60 bg-muted/40 p-2">
              <span className="block text-xs font-medium text-foreground">
                Qu'avez-vous change&nbsp;?
              </span>
              <div className="flex flex-col gap-1.5">
                {natures.map((nature, rang) => {
                  const retenue = etape.nature === nature.valeur;
                  return (
                    <Button
                      key={nature.valeur}
                      type="button"
                      variant="outline"
                      size="sm"
                      // La premiere prend le focus a l'ouverture : sans cela il
                      // filerait dans le champ de texte et la question serait
                      // sautee par tout praticien au clavier.
                      autoFocus={rang === 0}
                      aria-pressed={retenue}
                      disabled={envoi}
                      onClick={() => choisirNature(nature)}
                      className={cn(
                        "h-auto w-full flex-col items-start gap-0.5 whitespace-normal px-2.5 py-2 text-left text-xs",
                        retenue
                          ? CLASSES_NATURE_RETENUE[nature.ton]
                          : CLASSES_TON[nature.ton],
                      )}
                    >
                      <span className="font-semibold">{nature.libelle}</span>
                      <span className="font-normal opacity-75">
                        {nature.aide}
                      </span>
                    </Button>
                  );
                })}
              </div>
              {/* Dire pourquoi on demande : sans cette phrase, la question
                  passe pour une formalite de plus et se repond au hasard. */}
              <p className="text-[0.65rem] leading-relaxed text-muted-foreground">
                Sans cette precision, une reformulation de votre main serait
                comptee comme une erreur de MARC.
              </p>
            </div>
          )}

          {etape.option.saisieValeur && (
            <label className="block space-y-1">
              <span className="text-xs text-muted-foreground">
                Valeur retenue
              </span>
              <Textarea
                ref={champRef}
                autoFocus={!natureRequise}
                rows={2}
                value={etape.valeur}
                disabled={envoi}
                onChange={(e) => setEtape({ ...etape, valeur: e.target.value })}
                onKeyDown={(e) => {
                  // Raccourci de validation : la frappe reste dans le champ.
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    validerEtape();
                  }
                }}
                className="min-h-[60px]"
              />
            </label>
          )}

          {causeVisible && (
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">
                Pourquoi&nbsp;? (facultatif)
              </span>
              <div className="flex flex-wrap gap-1.5">
                {causes.map((cause) => {
                  const choisie = etape.cause === cause.valeur;
                  return (
                    <Button
                      key={cause.valeur}
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-pressed={choisie}
                      disabled={envoi}
                      onClick={() =>
                        setEtape({
                          ...etape,
                          cause: choisie ? null : cause.valeur,
                        })
                      }
                      className={cn(
                        "h-9 whitespace-normal px-3 text-xs",
                        choisie
                          ? "border-primary/50 bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                          : "text-muted-foreground",
                      )}
                    >
                      {cause.libelle}
                    </Button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-9"
              disabled={envoi}
              onClick={fermerEtape}
            >
              Annuler
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-9"
              disabled={
                envoi ||
                (etape.option.saisieValeur && etape.valeur.trim().length === 0) ||
                (natureRequise && etape.nature === null)
              }
              onClick={validerEtape}
            >
              {envoi && (
                <span className="h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground" />
              )}
              Enregistrer
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {grille.map((option) => (
            <Button
              key={option.valeur}
              type="button"
              variant="outline"
              size="sm"
              disabled={envoi}
              title={option.aide}
              aria-keyshortcuts={option.raccourci}
              onClick={() => choisir(option)}
              className={cn(
                "h-9 whitespace-normal px-3 text-xs",
                CLASSES_TON[option.ton],
              )}
            >
              {option.libelle}
              {/* Le raccourci s'affiche sur le bouton : un raccourci qu'il faut
                  aller chercher dans une aide n'est jamais appris. Il est dit
                  aux lecteurs d'ecran par aria-keyshortcuts, pas par ce
                  caractere isole qui ne s'enonce pas. */}
              <span
                aria-hidden="true"
                className="rounded-sm border border-current px-1 text-[0.6rem] font-bold leading-tight opacity-60"
              >
                {option.raccourci}
              </span>
            </Button>
          ))}
          {/* Une decision directe part sans second temps : le dire evite de
              cliquer deux fois quand le reseau prend une seconde. */}
          {envoi && (
            <span className="inline-flex items-center gap-1.5 self-center text-xs text-muted-foreground">
              <span className="h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-muted border-t-primary" />
              Enregistrement...
            </span>
          )}
        </div>
      )}

      {erreur && (
        <p className="mt-2 text-xs font-medium text-destructive">{erreur}</p>
      )}
    </div>
  );
}
