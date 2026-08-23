import { useRef, useState } from "react";
import { DoorOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const MOTIFS: Array<{ valeur: string; libelle: string }> = [
  { valeur: "outil_trop_lent", libelle: "L'outil est trop lent" },
  {
    valeur: "propositions_inexploitables",
    libelle: "Les propositions sont inexploitables",
  },
  { valeur: "interruption", libelle: "Je suis interrompu" },
  { valeur: "cas_trop_complexe", libelle: "Le cas est trop complexe" },
  { valeur: "autre", libelle: "Autre raison" },
];

interface BoutonAbandonProps {
  onAbandonner: (motif: string) => Promise<void>;
  className?: string;
}

/**
 * Porte de sortie de l'etude. Elle reste visible en permanence : un praticien
 * bloque qui ne peut pas sortir valide par complaisance, et l'etude devient
 * fausse tout en paraissant parfaite.
 */
export default function BoutonAbandon({
  onAbandonner,
  className,
}: BoutonAbandonProps) {
  const [ouvert, setOuvert] = useState(false);
  const [motif, setMotif] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const declencheurRef = useRef<HTMLButtonElement>(null);

  const fermer = () => {
    setOuvert(false);
    setMotif(null);
    setErreur(null);
    // Rendre le focus au declencheur : sans cela, le clavier repart du haut
    // de la page a chaque fermeture.
    declencheurRef.current?.focus();
  };

  const confirmer = async () => {
    if (!motif) return;
    setEnvoi(true);
    setErreur(null);
    try {
      await onAbandonner(motif);
      fermer();
    } catch {
      setErreur("Abandon non enregistre. Reessayez.");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div
      className={cn("relative", className)}
      onKeyDown={(e) => {
        if (e.key === "Escape" && ouvert) fermer();
      }}
    >
      <Button
        ref={declencheurRef}
        type="button"
        variant="outline"
        size="sm"
        aria-expanded={ouvert}
        onClick={() => (ouvert ? fermer() : setOuvert(true))}
        className="h-9 border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
      >
        <DoorOpen className="h-3.5 w-3.5" />
        Abandonner ce cas
      </Button>

      {ouvert && (
        <>
          {/* Clic exterieur : referme sans rien envoyer. */}
          <div
            className="fixed inset-0 z-40 bg-foreground/20 sm:bg-transparent"
            onClick={fermer}
          />
          {/* Sous 640 px, le bouton est trop pres du bord droit pour ancrer un
              popover : la liste des motifs devient une feuille centree. */}
          <div className="fixed inset-x-4 top-1/2 z-50 -translate-y-1/2 rounded-xl border bg-card p-3 shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[22rem] sm:translate-y-0">
            <p className="text-sm font-semibold text-foreground">
              Abandonner ce cas
            </p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Rien ne vous oblige a terminer. Nous dire pourquoi vous vous
              arretez nous est bien plus utile qu'une validation de complaisance.
            </p>

            <div
              role="radiogroup"
              aria-label="Motif de l'abandon"
              className="mt-2.5 space-y-1.5"
            >
              {MOTIFS.map((m, index) => {
                const choisi = motif === m.valeur;
                return (
                  <button
                    key={m.valeur}
                    type="button"
                    role="radio"
                    // Le focus entre dans le panneau des l'ouverture : Echap y
                    // repond, et le clavier n'a pas a retraverser la page.
                    autoFocus={index === 0}
                    aria-checked={choisi}
                    disabled={envoi}
                    onClick={() => setMotif(m.valeur)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50",
                      choisi
                        ? "border-destructive/40 bg-destructive/5 text-foreground"
                        : "border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border",
                        choisi ? "border-destructive" : "border-muted-foreground/50",
                      )}
                    >
                      {choisi && (
                        <span className="h-1.5 w-1.5 rounded-full bg-destructive" />
                      )}
                    </span>
                    {m.libelle}
                  </button>
                );
              })}
            </div>

            {erreur && (
              <p className="mt-2 text-xs font-medium text-destructive">
                {erreur}
              </p>
            )}

            <div className="mt-3 flex items-center justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-9"
                disabled={envoi}
                onClick={fermer}
              >
                Annuler
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                className="h-9"
                disabled={!motif || envoi}
                onClick={confirmer}
              >
                {envoi && (
                  <span className="h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-destructive-foreground/40 border-t-destructive-foreground" />
                )}
                Confirmer l'abandon
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
