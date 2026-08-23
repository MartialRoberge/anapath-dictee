import { useState } from "react";
import { Archive, ChevronDown, Undo2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { CarteRangee, TonDecision } from "./RevuePanel";

/** Une pastille de la couleur du ton : le regard trie la pile sans la lire. */
const PASTILLE_TON: Record<TonDecision, string> = {
  valide: "bg-success",
  nuance: "bg-warning",
  rejet: "bg-destructive",
  neutre: "bg-muted-foreground/50",
};

interface PileDecideesProps {
  /** Les cartes rangees, la derniere decidee en tete. */
  cartes: readonly CarteRangee[];
  /** Id de la carte dont l'annulation est en cours d'enregistrement. */
  annulationEnCours: string | null;
  erreur: string | null;
  onAnnuler: (id: string) => void;
  className?: string;
}

/**
 * La zone des propositions deja decidees : les cartes s'y rangent au lieu de
 * disparaitre, et chacune reste annulable.
 *
 * Deux raisons de la garder deployee par defaut plutot que refermee : c'est
 * la seule preuve visible que la pile active diminue vraiment, et c'est le seul
 * endroit d'ou revenir sur un clic de travers. Le repli reste possible pour un
 * dossier a trente propositions.
 */
export default function PileDecidees({
  cartes,
  annulationEnCours,
  erreur,
  onAnnuler,
  className,
}: PileDecideesProps) {
  const [ouverte, setOuverte] = useState(true);

  return (
    <aside
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-lg border border-border/60 bg-muted/30",
        className,
      )}
    >
      <button
        type="button"
        aria-expanded={ouverte}
        onClick={() => setOuverte(!ouverte)}
        className="flex shrink-0 items-center gap-2 px-2.5 py-2 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <Archive className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground">
          Rangees ({cartes.length})
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-150 motion-reduce:transition-none",
            !ouverte && "-rotate-90",
          )}
        />
      </button>

      {ouverte && (
        <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto overflow-x-hidden px-2 pb-2 scrollbar-thin">
          {cartes.map((carte) => {
            const enCours = annulationEnCours === carte.id;
            return (
              <li
                key={carte.id}
                className="animate-fade-in rounded-md border border-border/60 bg-card px-2 py-1.5 [animation-duration:200ms] motion-reduce:animate-none"
              >
                <div className="flex items-start gap-1.5">
                  <span
                    className={cn(
                      "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                      PASTILLE_TON[carte.ton],
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[0.7rem] font-semibold text-foreground">
                      {carte.libelleDecision}
                    </p>
                    <p
                      className="truncate text-[0.7rem] text-muted-foreground"
                      title={carte.valeurProposee}
                    >
                      {carte.valeurProposee}
                    </p>
                    {carte.valeurRetenue && (
                      <p
                        className="truncate text-[0.7rem] text-muted-foreground"
                        title={carte.valeurRetenue}
                      >
                        Retenu : {carte.valeurRetenue}
                      </p>
                    )}
                    {carte.libelleCause && (
                      <p className="truncate text-[0.65rem] text-muted-foreground/80">
                        {carte.libelleCause}
                      </p>
                    )}
                  </div>
                  {/* Sans ce retour en arriere, un clic de travers est
                      definitif : la peur de se tromper ralentit alors chaque
                      decision de la pile. */}
                  <Button
                    type="button"
                    variant="link"
                    size="sm"
                    disabled={enCours}
                    aria-label={`Annuler la decision : ${carte.libelleDecision}`}
                    onClick={() => onAnnuler(carte.id)}
                    className="h-auto shrink-0 gap-1 p-0 text-[0.7rem] text-muted-foreground hover:text-primary"
                  >
                    {enCours ? (
                      <span className="h-3 w-3 animate-spin-slow rounded-full border-2 border-muted border-t-primary" />
                    ) : (
                      <Undo2 className="h-3 w-3" />
                    )}
                    Annuler
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {erreur && (
        <p className="shrink-0 px-2.5 pb-2 text-[0.7rem] font-medium text-destructive">
          {erreur}
        </p>
      )}
    </aside>
  );
}
