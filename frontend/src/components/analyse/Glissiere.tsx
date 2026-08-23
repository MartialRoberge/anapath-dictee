import { useCallback, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * La poignee qui partage l'ecran entre l'analyse et le compte rendu.
 *
 * Le bon partage depend de ce que le praticien fait a l'instant : juger les
 * points demande de la place a gauche, ecrire en demande a droite. Aucune valeur
 * fixe ne convient aux deux, donc c'est lui qui decide.
 *
 * Utilisable au CLAVIER : les fleches deplacent la separation. Une poignee qui
 * ne repond qu'a la souris exclut une partie des utilisateurs d'une fonction
 * dont ils ont autant besoin que les autres.
 */

interface GlissiereProps {
  /** Part de largeur du panneau de gauche, entre 0 et 1. */
  part: number;
  onChange: (part: number) => void;
  /** Bornes, pour qu'aucun des deux cotes ne devienne inutilisable. */
  min?: number;
  max?: number;
  className?: string;
}

const PAS_CLAVIER = 0.04;

export default function Glissiere({
  part,
  onChange,
  min = 0.2,
  max = 0.65,
  className,
}: GlissiereProps) {
  const enCours = useRef(false);
  const conteneur = useRef<HTMLDivElement>(null);

  const borner = useCallback(
    (valeur: number) => Math.min(max, Math.max(min, valeur)),
    [min, max],
  );

  useEffect(() => {
    function deplacer(evenement: PointerEvent) {
      if (!enCours.current) return;
      const parent = conteneur.current?.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      if (rect.width === 0) return;
      onChange(borner((evenement.clientX - rect.left) / rect.width));
    }
    function relacher() {
      if (!enCours.current) return;
      enCours.current = false;
      // Le curseur et la selection sont neutralises pendant le glissement :
      // sans cela on selectionne le texte des deux panneaux en deplacant.
      document.body.style.removeProperty("cursor");
      document.body.style.removeProperty("user-select");
    }
    window.addEventListener("pointermove", deplacer);
    window.addEventListener("pointerup", relacher);
    window.addEventListener("pointercancel", relacher);
    return () => {
      window.removeEventListener("pointermove", deplacer);
      window.removeEventListener("pointerup", relacher);
      window.removeEventListener("pointercancel", relacher);
      relacher();
    };
  }, [borner, onChange]);

  function saisir() {
    enCours.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function auClavier(evenement: React.KeyboardEvent) {
    if (evenement.key === "ArrowLeft") {
      evenement.preventDefault();
      onChange(borner(part - PAS_CLAVIER));
    } else if (evenement.key === "ArrowRight") {
      evenement.preventDefault();
      onChange(borner(part + PAS_CLAVIER));
    }
  }

  return (
    <div
      ref={conteneur}
      role="separator"
      aria-orientation="vertical"
      aria-label="Largeur du panneau d'analyse"
      aria-valuenow={Math.round(part * 100)}
      aria-valuemin={Math.round(min * 100)}
      aria-valuemax={Math.round(max * 100)}
      tabIndex={0}
      onPointerDown={saisir}
      onKeyDown={auClavier}
      className={cn(
        "group relative w-2 shrink-0 cursor-col-resize touch-none select-none",
        "focus-visible:outline-none",
        className,
      )}
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:bg-primary/50 group-focus-visible:bg-primary" />
    </div>
  );
}
