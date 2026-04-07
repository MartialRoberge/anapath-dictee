import { useState, useEffect, useCallback } from "react";
import {
  ArrowLeft,
  Star,
  FileText,
  Users,
  MessageSquare,
  GitCompare,
  BarChart3,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

interface AdminStats {
  total_reports: number;
  total_users: number;
  average_rating: number | null;
  reports_with_feedback: number;
  reports_with_corrections: number;
  reports_by_organ: Record<string, number>;
}

interface AdminReport {
  id: string;
  user_name: string;
  user_email: string;
  organe_detecte: string;
  status: string;
  created_at: string;
  rating: number | null;
  feedback_comment: string | null;
  correction_count: number;
}

interface AdminCorrection {
  report_id: string;
  user_name: string;
  organe: string;
  timestamp: string;
  before_excerpt: string;
  after_excerpt: string;
}

type Tab = "stats" | "reports" | "corrections";

interface AdminPageProps {
  token: string | null;
  onBack: () => void;
}

export default function AdminPage({ token, onBack }: AdminPageProps) {
  const [tab, setTab] = useState<Tab>("stats");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [corrections, setCorrections] = useState<AdminCorrection[]>([]);
  const [loading, setLoading] = useState(true);

  const headers: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, reportsRes, correctionsRes] = await Promise.all([
        fetch(`${API_BASE}/admin/stats`, { headers }),
        fetch(`${API_BASE}/admin/reports`, { headers }),
        fetch(`${API_BASE}/admin/corrections`, { headers }),
      ]);
      if (statsRes.ok) setStats(await statsRes.json());
      if (reportsRes.ok) setReports(await reportsRes.json());
      if (correctionsRes.ok) setCorrections(await correctionsRes.json());
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b px-5">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-base font-bold">Administration</h1>
        <Button variant="ghost" size="icon" onClick={fetchData} className="ml-auto">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </header>

      {/* Tab bar */}
      <div className="flex border-b">
        {(
          [
            { key: "stats", label: "Dashboard", icon: BarChart3 },
            { key: "reports", label: "CR & Feedbacks", icon: MessageSquare },
            { key: "corrections", label: "Corrections", icon: GitCompare },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 text-sm font-medium transition-colors",
              tab === key
                ? "border-b-2 border-primary text-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <main className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-4xl">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-primary" />
            </div>
          ) : (
            <>
              {tab === "stats" && stats && <StatsTab stats={stats} />}
              {tab === "reports" && <ReportsTab reports={reports} />}
              {tab === "corrections" && <CorrectionsTab corrections={corrections} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function StatsTab({ stats }: { stats: AdminStats }) {
  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard
          icon={FileText}
          label="Total CR"
          value={stats.total_reports.toString()}
        />
        <KpiCard
          icon={Users}
          label="Utilisateurs"
          value={stats.total_users.toString()}
        />
        <KpiCard
          icon={Star}
          label="Note moyenne"
          value={stats.average_rating ? `${stats.average_rating}/5` : "-"}
        />
        <KpiCard
          icon={MessageSquare}
          label="Feedbacks"
          value={stats.reports_with_feedback.toString()}
        />
      </div>

      {/* Reports by organ */}
      <div className="rounded-lg border bg-card p-4">
        <h3 className="mb-3 text-sm font-semibold">CR par organe</h3>
        <div className="space-y-2">
          {Object.entries(stats.reports_by_organ)
            .sort(([, a], [, b]) => b - a)
            .map(([organe, count]) => (
              <div key={organe} className="flex items-center gap-3">
                <span className="w-32 truncate text-sm text-muted-foreground">
                  {organe}
                </span>
                <div className="flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{
                        width: `${Math.max(
                          (count / Math.max(...Object.values(stats.reports_by_organ))) * 100,
                          5
                        )}%`,
                      }}
                    />
                  </div>
                </div>
                <span className="text-sm font-medium tabular-nums">{count}</span>
              </div>
            ))}
        </div>
      </div>

      {/* Corrections count */}
      <div className="rounded-lg border bg-card p-4">
        <p className="text-sm text-muted-foreground">
          <span className="font-bold text-foreground">
            {stats.reports_with_corrections}
          </span>{" "}
          CR modifies par les praticiens (corrections disponibles pour amelioration continue)
        </p>
      </div>
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

function ReportsTab({ reports }: { reports: AdminReport[] }) {
  return (
    <div className="space-y-2">
      {reports.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aucun CR enregistre.
        </p>
      ) : (
        reports.map((r) => (
          <div key={r.id} className="rounded-lg border bg-card p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{r.user_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {r.user_email}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <Badge variant="default" className="text-[0.65rem]">
                    {r.organe_detecte}
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
                  {r.correction_count > 0 && (
                    <Badge variant="outline" className="gap-1 text-[0.65rem]">
                      <GitCompare className="h-3 w-3" />
                      {r.correction_count} correction
                      {r.correction_count > 1 ? "s" : ""}
                    </Badge>
                  )}
                </div>
              </div>
              <span className="text-xs text-muted-foreground">
                {new Date(r.created_at).toLocaleDateString("fr-FR")}
              </span>
            </div>
            {r.feedback_comment && (
              <p className="mt-2 rounded bg-muted/50 px-3 py-2 text-sm italic text-muted-foreground">
                "{r.feedback_comment}"
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function CorrectionsTab({
  corrections,
}: {
  corrections: AdminCorrection[];
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Modifications faites par les praticiens sur les CR generes. Chaque correction
        est une opportunite d'amelioration du prompt.
      </p>
      {corrections.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aucune correction enregistree.
        </p>
      ) : (
        corrections.map((c, idx) => (
          <div key={idx} className="rounded-lg border bg-card p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{c.user_name}</span>
              <Badge variant="outline" className="text-[0.6rem]">
                {c.organe}
              </Badge>
              <span>{c.timestamp ? new Date(c.timestamp).toLocaleDateString("fr-FR") : ""}</span>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div className="rounded bg-destructive/5 p-2">
                <p className="mb-1 text-[0.6rem] font-semibold text-destructive">
                  AVANT
                </p>
                <p className="text-xs text-muted-foreground">
                  {c.before_excerpt}
                </p>
              </div>
              <div className="rounded bg-success/5 p-2">
                <p className="mb-1 text-[0.6rem] font-semibold text-success">
                  APRES
                </p>
                <p className="text-xs text-muted-foreground">
                  {c.after_excerpt}
                </p>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
