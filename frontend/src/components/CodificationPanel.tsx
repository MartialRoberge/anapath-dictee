import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, RefreshCw, Hash } from "lucide-react";
import { Button } from "./ui/button";
import { getCodification, type CodificationResult } from "../services/api";

interface CodificationPanelProps {
  report: string;
  organe: string;
}

/** Bouton de copie compact avec retour visuel. */
function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard indisponible : ignore */
    }
  }, [value]);
  return (
    <button
      type="button"
      onClick={copy}
      title={`Copier ${label}`}
      aria-label={`Copier ${label}`}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-success" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

function CodeRow({
  label,
  code,
  display,
}: {
  label: string;
  code: string;
  display?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 last:border-0">
      <div className="min-w-0">
        <div className="text-[0.65rem] uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-semibold">{code}</span>
          {display && (
            <span className="truncate text-xs text-muted-foreground">
              {display}
            </span>
          )}
        </div>
      </div>
      <CopyButton value={code} label={`${label} ${code}`} />
    </div>
  );
}

export default function CodificationPanel({
  report,
  organe,
}: CodificationPanelProps) {
  const [codes, setCodes] = useState<CodificationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchCodes = useCallback(async () => {
    if (!report.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getCodification(report, organe || "non_determine");
      setCodes(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de codification");
    } finally {
      setLoading(false);
    }
  }, [report, organe]);

  // Auto-génération à l'apparition du rapport et après édition (débounce).
  useEffect(() => {
    if (!report.trim()) {
      setCodes(null);
      return;
    }
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(fetchCodes, 900);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [report, organe, fetchCodes]);

  if (!report.trim()) return null;

  const combined = codes
    ? [
        `ADICAP : ${codes.adicap.code}`,
        `SNOMED Topographie : ${codes.snomed.topography.code} (${codes.snomed.topography.display})`,
        `SNOMED Morphologie : ${codes.snomed.morphology.code} (${codes.snomed.morphology.display})`,
      ].join("\n")
    : "";

  return (
    <div className="mx-auto mt-4 max-w-[860px] rounded-md border bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between pb-3">
        <div className="flex items-center gap-2">
          <Hash className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold tracking-tight">
            Codification
          </h3>
          <span className="text-[0.65rem] text-muted-foreground">
            ADICAP · SNOMED CT
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {codes && (
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(combined);
                } catch {
                  /* ignore */
                }
              }}
              title="Copier toute la codification"
            >
              <Copy className="h-3.5 w-3.5" />
              Tout copier
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={fetchCodes}
            disabled={loading}
            title="Recalculer les codes"
            aria-label="Recalculer les codes"
          >
            <RefreshCw
              className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
            />
          </Button>
        </div>
      </div>

      {error && (
        <p className="py-2 text-xs text-destructive">{error}</p>
      )}

      {loading && !codes && (
        <p className="py-2 text-xs text-muted-foreground">
          Calcul des codes…
        </p>
      )}

      {codes && (
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">
                ADICAP
              </span>
              <CopyButton value={codes.adicap.code} label="code ADICAP" />
            </div>
            <div className="mb-2 rounded bg-muted/60 px-2 py-1 font-mono text-base font-bold tracking-wider">
              {codes.adicap.code}
            </div>
            <CodeRow
              label="Prélèvement"
              code={codes.adicap.prelevement_code}
              display={codes.adicap.prelevement}
            />
            <CodeRow
              label="Technique"
              code={codes.adicap.technique_code}
              display={codes.adicap.technique}
            />
            <CodeRow
              label="Organe"
              code={codes.adicap.organe_code}
              display={codes.adicap.organe}
            />
            <CodeRow
              label="Lésion"
              code={codes.adicap.lesion_code}
              display={codes.adicap.lesion}
            />
            {codes.adicap.confidence &&
              codes.adicap.confidence !== "haute" && (
                <p className="mt-1 rounded bg-warning/10 px-2 py-1 text-[0.65rem] leading-snug text-warning">
                  Code lésionnel non certain — à préciser par le pathologiste (le
                  système ne devine pas pour éviter toute erreur).
                </p>
              )}
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground">
                SNOMED CT
              </span>
            </div>
            <CodeRow
              label="Topographie"
              code={codes.snomed.topography.code}
              display={codes.snomed.topography.display}
            />
            <CodeRow
              label="Morphologie"
              code={codes.snomed.morphology.code}
              display={codes.snomed.morphology.display}
            />
          </div>
        </div>
      )}

      <p className="mt-3 text-[0.65rem] leading-relaxed text-muted-foreground">
        Codes suggérés automatiquement à partir du compte-rendu — à vérifier
        avant validation.
      </p>
    </div>
  );
}
