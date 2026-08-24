import { useCallback, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import BlocTexte from "./BlocTexte";
import type { Bloc, Trou } from "@/lib/blocsTexte";
import type { ActionPoint } from "@/lib/pointsATraiter";
import { cn } from "@/lib/utils";

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
  /** Remplace le texte d'un bloc dans le compte rendu. */
  onEditer: (bloc: Bloc, texte: string) => void;
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
  onEditer,
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
          // Titres et tableaux se rendent EN BLOC, avec le rendu Markdown
          // complet. Les afficher tels quels laissait leurs etoiles et leurs
          // barres verticales a l'ecran, et un tableau se lisait comme une
          // suite de paragraphes.
          return (
            <div
              key={bloc.id}
              data-bloc={bloc.id}
              className={cn(
                "prose-marc pt-2 text-[0.95rem] leading-relaxed first:pt-0",
                "[&_h1]:text-base [&_h1]:font-bold [&_h2]:text-[0.95rem] [&_h2]:font-semibold",
                "[&_p]:font-semibold",
                "[&_table]:w-full [&_table]:border-collapse [&_table]:text-xs",
                "[&_th]:border [&_th]:bg-muted/50 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left",
                "[&_td]:border [&_td]:px-2 [&_td]:py-1",
              )}
            >
              <div className="overflow-x-auto">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  disallowedElements={["a", "img"]}
                  unwrapDisallowed
                >
                  {bloc.texte}
                </ReactMarkdown>
              </div>
            </div>
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
            onEditer={(texte) => onEditer(bloc, texte)}
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
