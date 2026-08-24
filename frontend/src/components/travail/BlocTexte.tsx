import { useEffect, useRef, useState } from "react";
import { Check, HelpCircle, Pencil, Undo2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import TrouInline from "./TrouInline";
import MarkdownEnLigne from "./MarkdownEnLigne";
import type { Bloc, NatureBloc, Trou } from "@/lib/blocsTexte";
import type { ActionPoint } from "@/lib/pointsATraiter";

/**
 * Une phrase du compte rendu, et tout ce qu'on peut en faire.
 *
 * LES DECISIONS SONT ICI, sur la phrase, et nulle part ailleurs. Le panneau
 * d'analyse a cote explique ; il ne commande pas. Decider a gauche ce qu'on lit
 * a droite oblige a tenir les deux en tete pendant l'aller-retour, et c'est
 * pendant cet aller-retour qu'on accepte sans relire.
 *
 * LE FOND DIT LA NATURE, ET IL EST DISCRET EXPRES.
 *
 * Une phrase dictee ne porte AUCUNE couleur. C'est le cas de loin le plus
 * frequent : la teinter ferait un compte rendu bariole ou plus rien ne
 * ressort, et le praticien cesserait de regarder les couleurs — donc aussi
 * celles qui comptent.
 *
 * Le liseré est a GAUCHE et le fond uni : la version precedente cumulait un
 * bord colore et un en-tete teinte, ce qui dessinait un decrochement disgracieux
 * a la jonction des deux.
 */

const FONDS: Readonly<Record<NatureBloc, string>> = {
  // Rien. Ce que le praticien a dit se lit comme un compte rendu normal.
  dicte: "border-transparent",
  propose:
    "border-sky-500/70 bg-sky-500/[0.07] hover:bg-sky-500/[0.11]",
  verifier:
    "border-rose-500/70 bg-rose-500/[0.07] hover:bg-rose-500/[0.11]",
  libre: "border-transparent",
};

/**
 * Ce que la couleur veut dire, en une phrase, dans les mots du praticien.
 *
 * PAS DE VOCABULAIRE D'AGENTS. « Relecteur litteraliste », « le college a
 * vote » : personne n'a a savoir comment MARC est construit pour s'en servir.
 * On dit le POURQUOI, jamais la mecanique.
 */
/**
 * Ce que dit un bouton, en un ou deux mots.
 *
 * Les libelles du protocole (« Je n'ai pas dit ca », « Pertinent, mais je ne le
 * mets pas ») restent la MESURE et ne bougent pas : c'est eux qui partent dans
 * la grille de l'etude. Mais empiles sous chaque phrase, ils transformaient le
 * compte rendu en formulaire. Le praticien lit un mot, l'etude enregistre la
 * mesure exacte.
 */
const COURT: Readonly<Record<string, string>> = {
  conforme: "Oui",
  corrige: "Corriger",
  non_dicte: "Pas dit",
  hors_sujet: "Hors sujet",
  juste: "Juste",
  je_ne_sais_pas: "?",
  pertinent_ajoute: "Ajouter",
  pertinent_non_retenu: "Pertinent, non retenu",
  non_pertinent: "Sans objet",
};

const SENS: Readonly<Record<NatureBloc, string | null>> = {
  dicte: null,
  propose: "Découle de ce que vous avez dicté, sans que vous l'ayez dit.",
  verifier: "Rien dans votre dictée ne soutient ce passage.",
  libre: null,
};

interface BlocTexteProps {
  bloc: Bloc;
  /** Decision deja prise sur ce bloc, pour l'afficher au lieu des boutons. */
  decision: string | null;
  eclaire: boolean;
  occupe: boolean;
  onDecider: (action: ActionPoint, valeur?: string) => Promise<void>;
  onRemplirTrou: (trou: Trou, valeur: string) => void;
  onEcarterTrou: (trou: Trou) => void;
  /** Ouvre l'explicabilite de ce bloc a gauche. Consultation, pas decision. */
  onExpliquer: () => void;
  /** Premier affichage REEL a l'ecran. Jamais au montage. */
  onVu: () => void;
}

export default function BlocTexte({
  bloc,
  decision,
  eclaire,
  occupe,
  onDecider,
  onRemplirTrou,
  onEcarterTrou,
  onExpliquer,
  onVu,
}: BlocTexteProps) {
  const [correction, setCorrection] = useState<string | null>(null);
  /** Le praticien rouvre une decision deja prise pour la changer. */
  const [redecider, setRedecider] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const conteneur = useRef<HTMLDivElement>(null);
  const dejaVu = useRef(false);

  // L'AFFICHAGE REEL, pas le montage. Un bloc rendu hors ecran n'a ete vu de
  // personne, et le compter comme vu rendrait « non vu » impossible a mesurer.
  useEffect(() => {
    const cible = conteneur.current;
    if (cible === null || bloc.point === null || dejaVu.current) return;
    const observateur = new IntersectionObserver(
      (entrees) => {
        for (const entree of entrees) {
          if (!entree.isIntersecting || dejaVu.current) continue;
          dejaVu.current = true;
          onVu();
          observateur.disconnect();
        }
      },
      { threshold: 0.6 },
    );
    observateur.observe(cible);
    return () => observateur.disconnect();
  }, [bloc.point, onVu]);

  async function decider(action: ActionPoint, valeur?: string) {
    setErreur(null);
    try {
      await onDecider(action, valeur);
      setCorrection(null);
      setRedecider(false);
    } catch (e) {
      // Le bloc RESTE a decider : effacer la demande sur un echec reseau
      // ferait croire la decision enregistree alors qu'elle est perdue.
      setErreur(e instanceof Error ? e.message : "Décision non enregistrée.");
    }
  }

  const sens = SENS[bloc.nature];
  void sens;
  const aDecider = bloc.point !== null && (decision === null || redecider);

  return (
    <div
      ref={conteneur}
      data-bloc={bloc.id}
      onClick={bloc.point !== null ? onExpliquer : undefined}
      role={bloc.point !== null ? "button" : undefined}
      tabIndex={bloc.point !== null ? 0 : undefined}
      onKeyDown={(e) => {
        if (bloc.point === null) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onExpliquer();
        }
      }}
      className={cn(
        "group -mx-2 rounded-md border-l-[3px] px-2 py-1 transition-colors",
        FONDS[bloc.nature],
        bloc.point !== null && "cursor-pointer",
        // L'ECLAIRAGE VA DANS LES DEUX SENS : selectionner a gauche allume ici,
        // cliquer ici allume a gauche. Sans le retour visuel, on ne sait jamais
        // de quelle phrase l'explication parle.
        eclaire && "ring-2 ring-ring/50 ring-offset-1 ring-offset-background",
      )}
    >
      <p
        className={cn(
          "text-[0.95rem] leading-relaxed text-foreground",
          bloc.puce && "relative pl-4 before:absolute before:left-1 before:content-['•']",
        )}
      >
        {segments(bloc).map((segment, rang) =>
          typeof segment === "string" ? (
            <MarkdownEnLigne key={rang} texte={segment} />
          ) : (
            <TrouInline
              key={rang}
              trou={segment}
              occupe={occupe}
              onRemplir={(valeur) => onRemplirTrou(segment, valeur)}
              onEcarter={() => onEcarterTrou(segment)}
              onExpliquer={onExpliquer}
            />
          ),
        )}
      </p>

      {erreur && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {erreur}
        </p>
      )}

      {correction !== null && (
        <div className="mt-1.5 flex items-start gap-1.5">
          <textarea
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            rows={Math.min(8, Math.max(3, Math.ceil(correction.length / 60)))}
            aria-label="Votre formulation"
            className="flex-1 resize-y rounded-md border bg-background px-2 py-1 text-sm"
          />
          <button
            type="button"
            disabled={occupe || correction.trim() === ""}
            onClick={() =>
              void decider(
                { verbe: "modifier", libelle: "À corriger", decision: "corrige" },
                correction,
              )
            }
            className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            Remplacer
          </button>
        </div>
      )}

      {aDecider && correction === null && (
        <div
          className="mt-1 flex flex-wrap items-center gap-1"
          onClick={(e) => e.stopPropagation()}
        >
          {bloc.point?.actions.map((action) => (
            <button
              key={action.libelle}
              type="button"
              disabled={occupe}
              onClick={() =>
                action.saisie
                  ? setCorrection(bloc.texte.trim())
                  : void decider(action)
              }
              className={cn(
                "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium",
                "transition-colors disabled:opacity-50",
                "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                action.verbe === "accepter" &&
                  "bg-emerald-500/15 text-emerald-700 hover:bg-emerald-500/25 dark:text-emerald-300",
                action.verbe === "modifier" &&
                  "bg-muted text-foreground hover:bg-accent",
                action.verbe === "ecarter" &&
                  "bg-rose-500/10 text-rose-700 hover:bg-rose-500/20 dark:text-rose-300",
              )}
            >
              {action.verbe === "accepter" && <Check className="h-3 w-3" />}
              {action.verbe === "modifier" && <Pencil className="h-3 w-3" />}
              {action.verbe === "ecarter" && <X className="h-3 w-3" />}
              {COURT[action.decision] ?? action.libelle}
            </button>
          ))}
          <button
            type="button"
            onClick={onExpliquer}
            aria-label="Pourquoi cette proposition"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <HelpCircle className="h-3 w-3" />
            Pourquoi ?
          </button>
        </div>
      )}

      {/* UNE DECISION PRISE NE DISPARAIT PAS. Le praticien doit pouvoir
          revenir sur ce qu'il vient de trancher : un point qui s'evapore
          empeche de revoir son propre parcours, et donne l'impression d'avoir
          perdu quelque chose. */}
      {decision !== null && !redecider && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setRedecider(true);
          }}
          title="Revenir sur cette décision"
          className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[0.65rem] font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Check className="h-2.5 w-2.5" />
          {COURT[decision] ?? decision}
          <Undo2 className="h-2.5 w-2.5 opacity-60" />
        </button>
      )}
    </div>
  );
}

/** Le texte du bloc, coupe autour de ses trous. */
function segments(bloc: Bloc): (string | Trou)[] {
  if (bloc.trous.length === 0) return [bloc.texte];
  const morceaux: (string | Trou)[] = [];
  let curseur = 0;
  for (const trou of bloc.trous) {
    if (trou.debut > curseur) morceaux.push(bloc.texte.slice(curseur, trou.debut));
    morceaux.push(trou);
    curseur = trou.fin;
  }
  if (curseur < bloc.texte.length) morceaux.push(bloc.texte.slice(curseur));
  return morceaux;
}
