import { useEffect, useMemo, useRef } from "react";
import { AudioLines, MousePointerClick, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";

interface VerbatimPanelProps {
  /**
   * Chaine EXACTE envoyee au backend : les offsets d'empan sont calcules
   * dessus. On ne la normalise jamais (trim, collapse d'espaces, casse...),
   * la moindre retouche decalerait toutes les positions.
   */
  transcription: string;
  /**
   * Une proposition est-elle visee en ce moment ? Ce booleen est DISTINCT des
   * offsets, et c'est necessaire : une proposition non ancree arrive avec des
   * offsets nuls, exactement comme l'absence de survol. Sans ce drapeau, les
   * deux etats seraient indiscernables a l'ecran — et c'est justement le plus
   * important des deux qui disparaitrait.
   */
  visee: boolean;
  /** Offset de debut de l'empan, null si la proposition visee n'est pas ancree. */
  empanDebut: number | null;
  /** Offset de fin de l'empan, null si la proposition visee n'est pas ancree. */
  empanFin: number | null;
  className?: string;
}

/**
 * Panneau de gauche : la dictee telle qu'elle a ete transcrite, avec le
 * passage de la proposition survolee surligne et ramene sous les yeux.
 */
export default function VerbatimPanel({
  transcription,
  visee,
  empanDebut,
  empanFin,
  className,
}: VerbatimPanelProps) {
  const zoneRef = useRef<HTMLDivElement>(null);
  const marqueRef = useRef<HTMLElement>(null);

  // Bornage defensif : on ne coupe jamais hors de la chaine. C'est le seul
  // traitement applique aux offsets — aucune recherche de texte, aucune
  // reconstruction : le serveur fait foi.
  const empan = useMemo<{ debut: number; fin: number } | null>(() => {
    if (empanDebut === null || empanFin === null) return null;
    const max = transcription.length;
    const debut = Math.max(0, Math.min(empanDebut, max));
    const fin = Math.max(debut, Math.min(empanFin, max));
    return fin > debut ? { debut, fin } : null;
  }, [empanDebut, empanFin, transcription.length]);

  // Une proposition est visee, mais AUCUN passage de la dictee ne la soutient.
  // C'est l'etat le plus important de l'ecran : la question posee au praticien
  // n'est plus "est-ce fidele ?" mais "l'avez-vous dit ?". Le laisser ressembler
  // a un survol rate reviendrait a cacher la mesure centrale de l'etude.
  const sansPassage = visee && empan === null;

  // Sans ce recentrage, un empan hors champ rendrait le survol inutile :
  // le praticien devrait chercher lui-meme, et la revue reprendrait 30 s.
  // Deplacement immediat et non anime : une animation depend d'un rendu actif
  // (onglet masque, mouvement reduit) et peut ne jamais aboutir — le passage
  // doit etre sous les yeux a coup sur, et sans attente.
  useEffect(() => {
    const zone = zoneRef.current;
    const marque = marqueRef.current;
    if (!zone || !marque) return;
    const cible =
      marque.offsetTop - zone.clientHeight / 2 + marque.offsetHeight / 2;
    zone.scrollTop = Math.max(0, cible);
  }, [empan]);

  return (
    <section
      className={cn(
        "flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm",
        className,
      )}
    >
      <header className="flex shrink-0 items-center gap-2.5 border-b px-4 py-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <AudioLines className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">Dictee — verbatim</div>
          <div className="truncate text-xs text-muted-foreground">
            Transcription brute, non modifiable
          </div>
        </div>
      </header>

      <div
        ref={zoneRef}
        className="relative max-h-[22rem] flex-1 overflow-y-auto px-4 py-3 scrollbar-thin xl:max-h-none"
      >
        {sansPassage && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs leading-relaxed text-amber-900 dark:text-amber-200">
            <SearchX className="mt-px h-4 w-4 shrink-0" />
            <span>
              <strong className="font-semibold">
                Rien dans votre dictee ne soutient cette proposition.
              </strong>{" "}
              Il n'y a donc pas de passage a surligner. La question devient
              simplement : l'avez-vous dit ?
            </span>
          </div>
        )}
        {transcription.length > 0 ? (
          <p
            className={cn(
              "whitespace-pre-wrap break-words text-sm leading-relaxed transition-colors",
              // Le texte alentour s'estompe pour que l'empan ressorte seul.
              empan ? "text-muted-foreground/70" : "text-foreground",
            )}
          >
            {empan ? (
              <>
                {transcription.slice(0, empan.debut)}
                <mark
                  ref={marqueRef}
                  className="rounded-[3px] bg-primary/15 px-0.5 font-medium text-foreground ring-1 ring-primary/40 [-webkit-box-decoration-break:clone] [box-decoration-break:clone]"
                >
                  {transcription.slice(empan.debut, empan.fin)}
                </mark>
                {transcription.slice(empan.fin)}
              </>
            ) : (
              transcription
            )}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Aucune transcription pour ce cas.
          </p>
        )}
      </div>

      <footer className="shrink-0 border-t px-4 py-2 text-xs leading-relaxed text-muted-foreground">
        {sansPassage ? (
          "Aucun passage de la dictee ne soutient cette proposition."
        ) : empan ? (
          "Passage correspondant a la proposition visee."
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <MousePointerClick className="h-3.5 w-3.5 shrink-0" />
            Survolez une proposition — ou atteignez-la au clavier — pour situer
            son passage.
          </span>
        )}
      </footer>
    </section>
  );
}
