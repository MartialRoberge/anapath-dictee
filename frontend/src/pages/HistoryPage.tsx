import { useState, useEffect, useCallback } from "react";
import { Star, FileText, Clock, RefreshCw, Calendar, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { IrisLogo } from "../components/IrisLogo";
import { useToast } from "../components/Toast";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

interface ReportSummary {
  id: string;
  organe_detecte: string;
  status: string;
  created_at: string;
  excerpt: string;
  has_feedback: boolean;
  rating: number | null;
}

interface HistoryPageProps {
  token: string | null;
  onBack: () => void;
  onOpenReport: (reportId: string) => void;
}

const ORGANE_LABELS: Record<string, string> = {
  poumon: "Poumon",
  sein: "Sein",
  colon_rectum: "Colon-Rectum",
  prostate: "Prostate",
  canal_anal: "Canal anal",
  thyroide: "Thyroide",
  melanome: "Melanome",
  estomac: "Estomac",
  rein: "Rein",
  vessie: "Vessie",
  foie: "Foie",
  pancreas: "Pancreas",
  oesophage: "Oesophage",
  ovaire: "Ovaire",
  endometre: "Endometre",
  col_uterin: "Col uterin",
  testicule: "Testicule",
  lymphome: "Lymphome",
  sarcome: "Sarcome",
  non_determine: "Non determine",
};

function formatOrgane(key: string): string {
  return ORGANE_LABELS[key] ?? key.replace(/_/g, " ");
}

function formatDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function formatTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function relativeDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Aujourd'hui";
  if (diffDays === 1) return "Hier";
  if (diffDays < 7) return `Il y a ${diffDays} jours`;
  return formatDate(iso);
}

// Group reports by relative date
function groupByDate(reports: ReportSummary[]): Map<string, ReportSummary[]> {
  const groups = new Map<string, ReportSummary[]>();
  for (const r of reports) {
    const key = relativeDate(r.created_at);
    const list = groups.get(key) ?? [];
    list.push(r);
    groups.set(key, list);
  }
  return groups;
}

export default function HistoryPage({
  token,
  onBack,
  onOpenReport,
}: HistoryPageProps) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const fetchReports = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/reports`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setReports(await res.json());
      } else {
        toast("Erreur lors du chargement de l'historique", "error");
      }
    } catch {
      toast("Impossible de charger l'historique", "error");
    } finally {
      setLoading(false);
    }
  }, [token, toast]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  void onBack;

  const grouped = groupByDate(reports);

  return (
    <div className="h-full">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-tight">Historique</h2>
          <p className="text-xs text-muted-foreground">
            {reports.length} compte{reports.length !== 1 ? "s" : ""}-rendu{reports.length !== 1 ? "s" : ""} sauvegarde{reports.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchReports} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Actualiser
        </Button>
      </div>

      {/* Content */}
      {loading && reports.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-20 text-muted-foreground">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-iris-500" />
          <span className="text-sm">Chargement...</span>
        </div>
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-20 text-center">
          <IrisLogo size={48} className="opacity-20" />
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              Aucun compte-rendu sauvegarde
            </p>
            <p className="mt-1 text-xs text-muted-foreground/60">
              Les comptes-rendus sauvegardes apparaitront ici
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {Array.from(grouped.entries()).map(([dateLabel, groupReports]) => (
            <div key={dateLabel}>
              {/* Date header */}
              <div className="mb-2 flex items-center gap-2">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {dateLabel}
                </span>
                <div className="flex-1 border-t" />
              </div>

              {/* Reports */}
              <div className="space-y-2">
                {groupReports.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => onOpenReport(r.id)}
                    className="group flex w-full items-start gap-4 rounded-xl border bg-card p-4 text-left transition-all hover:border-iris-300 hover:shadow-sm"
                  >
                    {/* Icon */}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-iris-50 text-iris-600 dark:bg-iris-950/30 dark:text-iris-400">
                      <FileText className="h-5 w-5" />
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      {/* Top row: organ + status + rating */}
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">
                          {formatOrgane(r.organe_detecte)}
                        </span>
                        <Badge variant="outline" className="text-[0.6rem] capitalize">
                          {r.status === "draft" ? "Brouillon" : r.status}
                        </Badge>
                        {r.rating && (
                          <div className="flex items-center gap-0.5">
                            {Array.from({ length: r.rating }).map((_, i) => (
                              <Star key={i} className="h-3 w-3 fill-warning text-warning" />
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Excerpt */}
                      <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                        {r.excerpt || "Compte-rendu en cours de redaction"}
                      </p>

                      {/* Meta */}
                      <div className="mt-2 flex items-center gap-3 text-[0.65rem] text-muted-foreground/70">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatTime(r.created_at)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Tag className="h-3 w-3" />
                          {r.organe_detecte.replace(/_/g, " ")}
                        </span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
