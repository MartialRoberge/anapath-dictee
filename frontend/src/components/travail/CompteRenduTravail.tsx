import { useCallback, useEffect, useRef } from "react";
import BlocTexte from "./BlocTexte";
import type { Bloc, Trou } from "@/lib/blocsTexte";
import type { ActionPoint } from "@/lib/pointsATraiter";

/**
 * Le compte rendu comme SURFACE DE TRAVAIL.
 *
 * Le praticien lit son texte et le termine dedans : il valide une phrase
 * proposee, il en refuse une autre, il comble un trou, il choisit dans une
 * liste. Il ne remplit pas un formulaire a cote qui, ensuite, ecrirait le
 * texte a sa place.
 *
 * LE TEXTE EST LA SOURCE DE VERITE, pas le decoupage. Les blocs sont une
 * lecture du texte, refaite a chaque changement. C'est pour cela que remplir un
 * trou modifie le TEXTE et non un etat parallele : deux sources de verite
 * finiraient par diverger, et c'est le texte qui part dans le dossier du
 * patient.
 */

interface CompteRenduTravailProps {
  blocs: readonly Bloc[];
  /** Identifiant de bloc -> decision enregistree, pour ne rien faire disparaitre. */
  decisions: Readonly<Record<string, string>>;
  /** Le bloc dont l'explication est ouverte a gauche. */
  eclaire: string | null;
  occupe: boolean;
  onDecider: (bloc: Bloc, action: ActionPoint, valeur?: string) => Promise<void>;
  onRemplirTrou: (bloc: Bloc, trou: Trou, valeur: string) => void;
  onEcarterTrou: (bloc: Bloc, trou: Trou) => void;
  onExpliquer: (bloc: Bloc, trou: Trou | null) => void;
  onVu: (bloc: Bloc) => void;
  /** Demande de defilement vers un bloc, depuis la checklist de gauche. */
  allerA: string | null;
}

export default function CompteRenduTravail({
  blocs,
  decisions,
  eclaire,
  occupe,
  onDecider,
  onRemplirTrou,
  onEcarterTrou,
  onExpliquer,
  onVu,
  allerA,
}: CompteRenduTravailProps) {
  const conteneur = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (allerA === null || conteneur.current === null) return;
    const cible = conteneur.current.querySelector(`[data-bloc="${allerA}"]`);
    cible?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [allerA]);

  const expliquer = useCallback(
    (bloc: Bloc, trou: Trou | null) => onExpliquer(bloc, trou),
    [onExpliquer],
  );

  return (
    <div ref={conteneur} className="space-y-0.5">
      {blocs.map((bloc) => {
        // Un en-tete de section garde son role de reperage : il se lit, il ne
        // se decide pas. Le passer par BlocTexte lui donnerait des boutons.
        if (bloc.nature === "libre" && bloc.trous.length === 0) {
          return (
            <p
              key={bloc.id}
              data-bloc={bloc.id}
              className="whitespace-pre-wrap pt-2 text-[0.95rem] font-semibold leading-relaxed text-foreground first:pt-0"
            >
              {bloc.texte}
            </p>
          );
        }
        return (
          <BlocTexte
            key={bloc.id}
            bloc={bloc}
            decision={decisions[bloc.id] ?? null}
            eclaire={eclaire === bloc.id}
            occupe={occupe}
            onDecider={(action, valeur) => onDecider(bloc, action, valeur)}
            onRemplirTrou={(trou, valeur) => onRemplirTrou(bloc, trou, valeur)}
            onEcarterTrou={(trou) => onEcarterTrou(bloc, trou)}
            onExpliquer={() => expliquer(bloc, null)}
            onVu={() => onVu(bloc)}
          />
        );
      })}
    </div>
  );
}
