import { useState, useEffect, useCallback } from "react";
import { ArrowLeft, Star, FileText, Clock, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

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

export default function HistoryPage({
  token,
  onBack,
  onOpenReport,
}: HistoryPageProps) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchReports = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/reports`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setReports(await res.json());
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const formatDate = (iso: string): string => {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b px-5">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-base font-bold">Historique des comptes-rendus</h1>
        <Button variant="ghost" size="icon" onClick={fetchReports} className="ml-auto">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </header>

      <main className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-3xl space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-primary" />
              <span className="ml-3 text-sm">Chargement...</span>
            </div>
          ) : reports.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-20 text-center">
              <FileText className="h-10 w-10 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">
                Aucun compte-rendu sauvegarde.
              </p>
            </div>
          ) : (
            reports.map((r) => (
              <button
                key={r.id}
                onClick={() => onOpenReport(r.id)}
                className="flex w-full items-start gap-3 rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent/50"
              >
                <FileText className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="default" className="text-[0.65rem]">
                      {r.organe_detecte}
                    </Badge>
                    <Badge variant="outline" className="text-[0.65rem]">
                      {r.status}
                    </Badge>
                    {r.rating && (
                      <div className="flex items-center gap-0.5">
                        {Array.from({ length: r.rating }).map((_, i) => (
                          <Star
                            key={i}
                            className="h-3 w-3 fill-warning text-warning"
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <p className="mt-1 truncate text-sm text-foreground">
                    {r.excerpt || "Compte-rendu sans conclusion"}
                  </p>
                  <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {formatDate(r.created_at)}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
