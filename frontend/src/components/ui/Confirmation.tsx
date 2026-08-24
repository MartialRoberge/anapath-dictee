import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * Une demande de confirmation qui ressemble a l'application.
 *
 * `window.confirm` bloque le fil d'execution, ne se met pas au theme sombre,
 * affiche l'adresse du site en en-tete et ne laisse formuler ni un titre ni
 * trois choix. Sur les deux gestes ou il servait — creer un nouveau compte
 * rendu, supprimer un compte rendu — cela donnait une boite grise du systeme
 * au milieu d'un outil medical.
 *
 * TROIS ISSUES POSSIBLES, et c'est la raison d'etre du composant : « creer un
 * nouveau compte rendu » n'est pas une question a deux reponses. Sauvegarder
 * puis continuer, continuer sans sauvegarder, ou renoncer sont trois choses
 * differentes, et `window.confirm` n'en offrait que deux — ce qui obligeait a
 * sauvegarder pour avancer.
 */

export interface ActionConfirmation {
  libelle: string;
  onChoisir: () => void;
  /** L'action mise en avant. Une seule. */
  principale?: boolean;
  /** L'action detruit quelque chose : elle se signale. */
  destructive?: boolean;
}

interface ConfirmationProps {
  ouverte: boolean;
  titre: string;
  message?: string;
  actions: readonly ActionConfirmation[];
  /** Échap, ou clic a cote. Toujours une sortie sans consequence. */
  onAnnuler: () => void;
}

export default function Confirmation({
  ouverte,
  titre,
  message,
  actions,
  onAnnuler,
}: ConfirmationProps) {
  const boite = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ouverte) return;
    // Le focus entre dans la boite : sans cela, Échap ne fonctionne que si
    // l'on a d'abord clique dedans, et le clavier ne mene nulle part.
    boite.current?.focus();
    function auClavier(evenement: KeyboardEvent) {
      if (evenement.key === "Escape") onAnnuler();
    }
    document.addEventListener("keydown", auClavier);
    return () => document.removeEventListener("keydown", auClavier);
  }, [ouverte, onAnnuler]);

  if (!ouverte) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
      onClick={onAnnuler}
    >
      <div
        ref={boite}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={titre}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-xl border bg-card p-5 shadow-2xl outline-none"
      >
        <h2 className="text-sm font-semibold text-foreground">{titre}</h2>
        {message && (
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            {message}
          </p>
        )}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onAnnuler}
            className="rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent"
          >
            Annuler
          </button>
          {actions.map((action) => (
            <button
              key={action.libelle}
              type="button"
              onClick={action.onChoisir}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                action.destructive
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : action.principale
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "border bg-background text-foreground hover:bg-accent",
              )}
            >
              {action.libelle}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
