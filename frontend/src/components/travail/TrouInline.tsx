import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Trou } from "@/lib/blocsTexte";

/**
 * Un manque, comble LA OU IL MANQUE.
 *
 * Le praticien ne quitte pas sa phrase. Il lit « la lesion mesure ___ », il
 * clique dans le blanc, il ecrit ou il choisit, et la phrase se termine. Sortir
 * pour remplir un formulaire a cote obligeait a se souvenir de quoi il
 * s'agissait pendant l'aller-retour — et un trou qu'on remplit de memoire est
 * un trou qu'on remplit mal.
 *
 * DEUX FORMES, ET LE CHOIX N'EN EST PAS UN.
 *
 * Quand la liste des reponses est FERMEE (bas grade / haut grade ; saines /
 * envahies), on donne un menu : choisir est plus rapide et plus sur que
 * retaper, et il n'y a rien a inventer.
 *
 * Quand elle ne l'est pas — une taille, un compte, une phrase — on donne un
 * champ libre. On ne fabrique JAMAIS une liste plausible pour faire joli :
 * proposer trois valeurs fausses est pire que n'en proposer aucune, parce
 * qu'on choisit dans une liste sans penser a la contester.
 *
 * Le trou ne se remplit jamais tout seul, meme quand une seule valeur semble
 * possible : ce serait redevenir la machine a pre-remplir qu'on a demontee.
 */

interface TrouInlineProps {
  trou: Trou;
  /** Insere la valeur dans le compte rendu, a la place du marqueur. */
  onRemplir: (valeur: string) => void;
  /** Le praticien juge le champ sans objet ici. Le marqueur disparait. */
  onEcarter: () => void;
  /** Ouvre l'explicabilite de ce trou dans le panneau de gauche. */
  onExpliquer: () => void;
  occupe: boolean;
}

export default function TrouInline({
  trou,
  onRemplir,
  onEcarter,
  onExpliquer,
  occupe,
}: TrouInlineProps) {
  const [ouvert, setOuvert] = useState(false);
  // La saisie SURVIT a la fermeture. Sans cela, refermer par megarde effaçait
  // ce qui venait d'etre tape, et il fallait tout recommencer.
  const [saisie, setSaisie] = useState("");
  const champRef = useRef<HTMLInputElement>(null);
  const boite = useRef<HTMLSpanElement>(null);

  // Fermer en cliquant a cote, comme partout ailleurs. Sans cette sortie, le
  // seul moyen de refermer etait la croix — qui, elle, ecarte le champ.
  useEffect(() => {
    if (!ouvert) return;
    function auClicExterieur(evenement: MouseEvent) {
      if (boite.current?.contains(evenement.target as Node)) return;
      setOuvert(false);
    }
    document.addEventListener("mousedown", auClicExterieur);
    return () => document.removeEventListener("mousedown", auClicExterieur);
  }, [ouvert]);

  const aOptions = trou.options.length > 0;

  function ouvrir() {
    if (occupe) return;
    setOuvert(true);
    onExpliquer();
    // Le focus part sur le champ : cliquer un trou puis devoir cliquer encore
    // dans la boite est un geste de trop, repete a chaque champ.
    if (!aOptions) window.setTimeout(() => champRef.current?.focus(), 0);
  }

  function valider(valeur: string) {
    const propre = valeur.trim();
    if (propre === "") return;
    onRemplir(propre);
    setOuvert(false);
    setSaisie("");
  }

  if (!ouvert) {
    return (
      <button
        type="button"
        onClick={ouvrir}
        disabled={occupe}
        aria-label={`Compléter : ${trou.champ}`}
        className={cn(
          "mx-0.5 inline-flex items-baseline gap-1 rounded px-1.5 py-0.5 align-baseline",
          "border-b-2 border-dashed border-amber-500/70 bg-amber-500/10",
          "text-sm font-medium text-amber-900 dark:text-amber-200",
          "transition-colors hover:bg-amber-500/20",
          "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:opacity-50",
        )}
      >
        {trou.champ}
        {aOptions && <ChevronDown className="h-3 w-3 shrink-0 opacity-70" />}
      </button>
    );
  }

  return (
    <span ref={boite} className="relative mx-0.5 inline-block align-baseline">
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-md border border-amber-500/60",
          "bg-card px-1.5 py-0.5 shadow-sm",
        )}
      >
        {aOptions ? (
          <span className="flex flex-wrap items-center gap-1">
            {trou.options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => valider(option)}
                disabled={occupe}
                className={cn(
                  "rounded px-1.5 py-0.5 text-xs font-medium",
                  "bg-amber-500/15 text-amber-900 dark:text-amber-100",
                  "transition-colors hover:bg-amber-500/30",
                  "ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                {option}
              </button>
            ))}
            {/* Toujours la sortie libre a cote du menu : une liste fermee peut
                se tromper, et forcer un choix dedans ferait entrer une valeur
                fausse plutot qu'aucune. */}
            <input
              ref={champRef}
              value={saisie}
              onChange={(e) => setSaisie(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") valider(saisie);
                if (e.key === "Escape") setOuvert(false);
              }}
              placeholder="autre…"
              aria-label={`Autre valeur pour ${trou.champ}`}
              className="w-24 min-w-0 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            />
          </span>
        ) : (
          <input
            ref={champRef}
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") valider(saisie);
              if (e.key === "Escape") setOuvert(false);
            }}
            placeholder={trou.champ}
            aria-label={trou.champ}
            className="w-56 min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        )}

        <span className="flex shrink-0 items-center gap-0.5 border-l pl-1">
          {!aOptions && (
            <button
              type="button"
              onClick={() => valider(saisie)}
              disabled={occupe || saisie.trim() === ""}
              aria-label="Valider"
              className="rounded p-0.5 text-emerald-600 hover:bg-emerald-500/15 disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              onEcarter();
              setOuvert(false);
            }}
            disabled={occupe}
            aria-label="Sans objet ici"
            title="Sans objet ici"
            className="rounded p-0.5 text-muted-foreground hover:bg-accent disabled:opacity-40"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </span>
      </span>
    </span>
  );
}
