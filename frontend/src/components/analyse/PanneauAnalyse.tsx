import type React from "react";
import { useMemo } from "react";
import { CheckCircle2, ShieldCheck, Tags } from "lucide-react";
import { cn } from "@/lib/utils";
import PointCarte from "./PointCarte";
import type { ActionPoint, PointATraiter } from "@/lib/pointsATraiter";

/**
 * L'analyse MARC, a gauche du compte rendu.
 *
 * UNE SEULE FILE. Propositions, champs obligatoires, codes, incoherences : tout
 * arrive ici, dans le meme ordre de gravite, avec les memes gestes. Avant, ces
 * quatre choses vivaient dans trois panneaux differents et le praticien ne
 * sentait jamais avancer — il voyait des panneaux, jamais une tache qui se
 * termine.
 *
 * LE COMPTEUR DESCEND. C'est le seul ressort d'un parcours : savoir combien il
 * reste et le voir diminuer. Les points traites ne disparaissent pas, ils se
 * rangent en dessous, replies — pour pouvoir revenir sur un geste sans le
 * craindre.
 *
 * En bas, ce qui ne demande AUCUNE action : les points deja verifies et la
 * codification. Les melanger a la file les ferait chercher parmi des choses a
 * faire, et diluerait le compteur.
 */

export interface PointVerifie {
  libelle: string;
  detail?: string;
}

export interface CodeAffiche {
  position: string;
  code: string;
  libelle: string;
}

interface PanneauAnalyseProps {
  points: PointATraiter[];
  /** Identifiant de point -> decision prise. */
  traites: Readonly<Record<string, string>>;
  pointActif: string | null;
  occupe: boolean;
  verifies: PointVerifie[];
  codes: CodeAffiche[];
  onDecider: (
    point: PointATraiter,
    action: ActionPoint,
    valeur?: string,
    nature?: string,
  ) => void;
  onSurvol: (point: PointATraiter | null) => void;
  onOuvrirPourquoi: (point: PointATraiter) => void;
  className?: string;
  /** Largeur imposee par la glissiere du parent. */
  style?: React.CSSProperties;
}

export default function PanneauAnalyse({
  points,
  traites,
  pointActif,
  occupe,
  verifies,
  codes,
  onDecider,
  onSurvol,
  onOuvrirPourquoi,
  className,
  style,
}: PanneauAnalyseProps) {
  const { restants, faits } = useMemo(() => {
    const restants = points.filter((point) => !(point.id in traites));
    const faits = points.filter((point) => point.id in traites);
    return { restants, faits };
  }, [points, traites]);

  const total = points.length;
  const avancement = total === 0 ? 0 : Math.round((faits.length / total) * 100);

  return (
    <section
      style={style}
      className={cn(
        "flex min-h-0 min-w-0 shrink-0 flex-col overflow-hidden rounded-xl border bg-muted/30",
        className,
      )}
    >
      <header className="shrink-0 border-b bg-card px-3.5 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-semibold">Analyse MARC</h2>
          <span className="text-xs tabular-nums text-muted-foreground">
            {restants.length === 0
              ? "tout est traité"
              : `${restants.length} à traiter`}
          </span>
        </div>
        {/* La barre est le seul retour immediat sur l'avancement. Elle ne sert
            a rien d'autre : pas de pourcentage affiche, qui ferait viser un
            chiffre plutot que juger. */}
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500 motion-reduce:transition-none"
            style={{ width: `${avancement}%` }}
          />
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3 scrollbar-thin">
        {restants.length > 0 ? (
          <div className="space-y-2">
            {restants.map((point) => (
              <PointCarte
                key={point.id}
                point={point}
                actif={point.id === pointActif}
                occupe={occupe}
                onDecider={(action, valeur, nature) =>
                  onDecider(point, action, valeur, nature)
                }
                onSurvol={onSurvol}
                onOuvrirPourquoi={onOuvrirPourquoi}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed px-3 py-6 text-center">
            <CheckCircle2 className="mx-auto h-6 w-6 text-primary/70" />
            <p className="mt-2 text-sm font-medium">
              {total === 0
                ? "Rien à vérifier sur ce compte rendu"
                : "Tous les points sont traités"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {total === 0
                ? "Les relecteurs sont d'accord sur tout ce qui a été écrit."
                : "Vous pouvez valider le compte rendu."}
            </p>
          </div>
        )}

        {faits.length > 0 && (
          <details className="rounded-lg border bg-card/60">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
              {faits.length} point{faits.length > 1 ? "s" : ""} traité
              {faits.length > 1 ? "s" : ""}
            </summary>
            <ul className="space-y-1 px-3 pb-2.5">
              {faits.map((point) => (
                <li
                  key={point.id}
                  className="flex items-baseline gap-2 text-xs text-muted-foreground"
                >
                  <CheckCircle2 className="h-3 w-3 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate">{point.detail}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      {/* Ce qui ne demande AUCUNE action, en bas, hors de la file. */}
      {(verifies.length > 0 || codes.length > 0) && (
        <footer className="shrink-0 space-y-2.5 border-t bg-card px-3.5 py-3">
          {verifies.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-[0.68rem] font-medium uppercase tracking-wide text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" />
                Points vérifiés
              </p>
              <ul className="mt-1.5 space-y-1">
                {verifies.map((point) => (
                  <li key={point.libelle} className="text-xs text-muted-foreground">
                    <span className="text-foreground">{point.libelle}</span>
                    {point.detail ? ` — ${point.detail}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {codes.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-[0.68rem] font-medium uppercase tracking-wide text-muted-foreground">
                <Tags className="h-3.5 w-3.5" />
                Codification
              </p>
              <ul className="mt-1.5 space-y-1">
                {codes.map((code) => (
                  <li key={code.position + code.code} className="text-xs">
                    <span className="font-mono text-foreground">{code.code}</span>
                    <span className="text-muted-foreground"> — {code.libelle}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </footer>
      )}
    </section>
  );
}