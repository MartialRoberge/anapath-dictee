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

/**
 * LE FOND DIT LA NATURE, ET IL N'ACCUSE PAS.
 *
 * Le rouge disait « rien dans votre dictee ne soutient cette phrase » — et
 * c'etait un contresens : si MARC ecrit une phrase, c'est qu'il a une raison,
 * et une raison se justifie, elle ne s'alarme pas. Le rouge faisait passer une
 * PROPOSITION pour une FAUTE, alors que le praticien doit simplement juger si
 * l'interpretation tient.
 *
 * Deux teintes suffisent, et la difference porte sur la NATURE du geste
 * attendu : bleu = une proposition a valider, ambre = une interpellation, une
 * chose que MARC a deduite et sur laquelle il attire l'attention.
 */
const FONDS: Readonly<Record<NatureBloc, string>> = {
  // Rien. Ce que le praticien a dit se lit comme un compte rendu normal.
  dicte: "border-transparent",
  propose: "border-sky-500/70 bg-sky-500/[0.06] hover:bg-sky-500/[0.10]",
  verifier: "border-amber-500/70 bg-amber-500/[0.06] hover:bg-amber-500/[0.10]",
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
  corrige: "Corrigé",
  // « Je n'ai pas dit ca » se lisait comme une accusation, et « pas dit »
  // comme une erreur. Ni l'un ni l'autre : une phrase que le praticien n'a pas
  // dictee peut etre juste et utile — il la garde alors. Ce bouton-ci sert
  // quand elle ne doit PAS figurer, et le libelle le dit sans juger.
  non_dicte: "Retirer",
  hors_sujet: "Pas ici",
  juste: "Juste",
  je_ne_sais_pas: "?",
  pertinent_ajoute: "Ajouter",
  pertinent_non_retenu: "Pertinent, non retenu",
  non_pertinent: "Sans objet",
};

const SENS: Readonly<Record<NatureBloc, string | null>> = {
  dicte: null,
  propose: "Proposition",
  verifier: "Interpellation",
  libre: null,
};

interface BlocTexteProps {
  bloc: Bloc;
  /** Decision deja prise sur ce bloc, pour l'afficher au lieu des boutons. */
  decision: string | null;
  eclaire: boolean;
  occupe: boolean;
  onDecider: (action: ActionPoint, valeur?: string) => Promise<void>;
  /** Remplace le texte de CE bloc dans le compte rendu. */
  onEditer: (texte: string) => void;
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
  onEditer,
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
  const champEdition = useRef<HTMLTextAreaElement>(null);
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

  /**
   * L'edition en place s'enregistre a la sortie du champ.
   *
   * Un texte inchange n'est PAS une correction : l'enregistrer ferait compter
   * une modification a chaque fois que le praticien clique dans une phrase et
   * en ressort, et le taux de correction publie serait faux.
   */
  async function enregistrerEdition() {
    const nouveau = (correction ?? "").trim();
    setCorrection(null);
    if (nouveau === "" || nouveau === bloc.texte.trim()) return;
    onEditer(nouveau);
    const action = bloc.point?.actions.find((a) => a.decision === "corrige");
    if (action) await decider(action, nouveau);
  }

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
      {correction !== null ? (
        <textarea
          ref={champEdition}
          value={correction}
          onChange={(e) => setCorrection(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === "Escape") setCorrection(null);
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void enregistrerEdition();
          }}
          onBlur={() => void enregistrerEdition()}
          aria-label="Modifier cette phrase"
          className={cn(
            // MEME typographie que le texte : on continue d'ecrire son compte
            // rendu, on ne remplit pas un formulaire a cote.
            "w-full resize-none bg-transparent text-[0.95rem] leading-relaxed text-foreground",
            "rounded-sm outline-none ring-1 ring-ring/40",
          )}
          rows={Math.max(1, Math.ceil(correction.length / 70))}
        />
      ) : (
      <p
        onDoubleClick={(e) => {
          // Double-clic = j'ecris ici. Le geste attendu partout ailleurs.
          e.stopPropagation();
          if (!occupe) setCorrection(bloc.texte);
        }}
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
      )}

      {erreur && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {erreur}
        </p>
      )}

      {aDecider && correction === null && (
        <div
          className="mt-1 flex flex-wrap items-center gap-1"
          onClick={(e) => e.stopPropagation()}
        >
          {/* « Corriger » n'est plus un bouton : on modifie la phrase
              directement, par double-clic. Un bouton qui ouvre un second champ
              de texte au-dessus du texte demandait de retaper ce qu'on avait
              deja sous les yeux. */}
          {bloc.point?.actions
            .filter((action) => action.decision !== "corrige")
            .map((action) => (
            <button
              key={action.libelle}
              type="button"
              disabled={occupe}
              onClick={() => void decider(action)}
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
