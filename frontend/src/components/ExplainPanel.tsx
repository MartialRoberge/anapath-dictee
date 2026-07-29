import { useState } from "react";
import { Brain, ChevronDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  ReportTrace,
  CoherenceVerdict,
  Signalement,
} from "../services/api";

interface ExplainPanelProps {
  trace: ReportTrace;
  warnings: string[];
  coherence: CoherenceVerdict;
}

const GRAVITE_RANK: Record<string, number> = { haute: 0, moyenne: 1, basse: 2 };
const CATEGORIE_LABEL: Record<string, string> = {
  fidelite: "Fidélité",
  manque: "Donnée manquante",
  incertitude: "À vérifier",
  coherence: "Cohérence",
};

/** Warnings des garde-fous déterministes utiles au praticien (on écarte le bruit
 *  interne « N marqueur(s) retiré(s) » et les signalements déjà dans la trace). */
function usefulSecurityWarnings(warnings: string[]): string[] {
  return warnings.filter(
    (w) =>
      !w.startsWith("Relecture —") &&
      !/marqueur\(s\) hors-contexte|champ\(s\) deja present|retire\(s\) des suggestions/i.test(
        w,
      ),
  );
}

export default function ExplainPanel({
  trace,
  warnings,
  coherence,
}: ExplainPanelProps) {
  const [open, setOpen] = useState(true);

  const comp = trace.comprehension ?? {};
  const signalements: Signalement[] = [...(trace.signalements ?? [])].sort(
    (a, b) =>
      (GRAVITE_RANK[a.gravite ?? "moyenne"] ?? 1) -
      (GRAVITE_RANK[b.gravite ?? "moyenne"] ?? 1),
  );
  const securityWarnings = usefulSecurityWarnings(warnings);
  const coherenceIssues = coherence.ok ? [] : coherence.issues;

  const hasComprehension =
    (comp.organes && comp.organes.length > 0) ||
    (comp.entites && comp.entites.length > 0) ||
    !!comp.resume;
  const nbPoints =
    signalements.length + securityWarnings.length + coherenceIssues.length;

  // Rien à expliquer (moteur mono-passe sans signalement) → panneau masqué.
  if (!hasComprehension && nbPoints === 0) return null;

  return (
    <div className="mx-auto mb-4 max-w-[860px] overflow-hidden rounded-xl border bg-card shadow-sm">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-accent/30"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Brain className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">Analyse de MARC</div>
          {comp.resume && (
            <div className="truncate text-xs text-muted-foreground">
              {comp.resume}
            </div>
          )}
        </div>
        {nbPoints > 0 && (
          <span className="shrink-0 rounded-full bg-warning/15 px-2 py-0.5 text-[0.7rem] font-semibold text-warning">
            {nbPoints} point{nbPoints > 1 ? "s" : ""} à vérifier
          </span>
        )}
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="space-y-4 border-t px-4 py-4">
          {/* Ce que MARC a compris */}
          {hasComprehension && (
            <div>
              <div className="mb-1.5 text-[0.7rem] font-bold uppercase tracking-wide text-primary">
                Compris depuis la dictée
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(comp.organes ?? []).map((o) => (
                  <Chip key={`o-${o}`} tone="primary">
                    {o}
                  </Chip>
                ))}
                {comp.type_prelevement && (
                  <Chip tone="muted">{comp.type_prelevement}</Chip>
                )}
                {(comp.entites ?? []).map((e) => (
                  <Chip key={`e-${e}`} tone="muted">
                    {e}
                  </Chip>
                ))}
              </div>
            </div>
          )}

          {/* Points de relecture */}
          {signalements.length > 0 && (
            <div>
              <div className="mb-1.5 text-[0.7rem] font-bold uppercase tracking-wide text-muted-foreground">
                Relecture — à vérifier (MARC signale, vous décidez)
              </div>
              <ul className="space-y-1.5">
                {signalements.map((s, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <AlertTriangle
                      className={cn(
                        "mt-0.5 h-3.5 w-3.5 shrink-0",
                        s.gravite === "haute"
                          ? "text-destructive"
                          : "text-warning",
                      )}
                    />
                    <span>
                      <span className="font-medium text-muted-foreground">
                        {CATEGORIE_LABEL[s.categorie] ?? s.categorie} ·{" "}
                      </span>
                      {s.message}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Contrôles de sécurité déterministes */}
          {securityWarnings.length > 0 && (
            <div>
              <div className="mb-1.5 text-[0.7rem] font-bold uppercase tracking-wide text-destructive">
                Contrôles de sécurité
              </div>
              <ul className="space-y-1.5">
                {securityWarnings.map((w, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Cohérence */}
          {coherenceIssues.length > 0 ? (
            <div>
              <div className="mb-1.5 text-[0.7rem] font-bold uppercase tracking-wide text-muted-foreground">
                Cohérence
              </div>
              <ul className="space-y-1.5">
                {coherenceIssues.map((c, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                    <span>{c.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            nbPoints === 0 && (
              <div className="flex items-center gap-2 text-sm text-success">
                <CheckCircle2 className="h-4 w-4" />
                Aucun point signalé.
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}

function Chip({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "primary" | "muted";
}) {
  return (
    <span
      className={cn(
        "rounded-md px-2 py-0.5 text-xs font-medium",
        tone === "primary"
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
