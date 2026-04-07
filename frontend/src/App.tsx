import { useState, useCallback, useEffect } from "react";
import {
  Moon,
  Sun,
  History,
  Shield,
  LogOut,
  Save,
  Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import HistoryPage from "./pages/HistoryPage";
import AdminPage from "./pages/AdminPage";
import RecorderPanel from "./components/RecorderPanel";
import ReportPanel from "./components/ReportPanel";
import CompletionPanel from "./components/CompletionPanel";
import { formatTranscription } from "./services/api";
import type { DonneeManquante } from "./services/api";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

type Page = "app" | "history" | "admin";

function useTheme(): { isDark: boolean; toggle: () => void } {
  const [isDark, setIsDark] = useState(true);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);
  const toggle = useCallback(() => setIsDark((p) => !p), []);
  return { isDark, toggle };
}

export default function App() {
  const { isDark, toggle } = useTheme();
  const { user, loading, login, register, logout, getToken } = useAuth();
  const [page, setPage] = useState<Page>("app");

  // Report state
  const [rawTranscription, setRawTranscription] = useState<string | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [donneesManquantes, setDonneesManquantes] = useState<DonneeManquante[]>([]);
  const [organeDetecte, setOrganeDetecte] = useState("");
  const [reformatting, setReformatting] = useState(false);
  const [dismissedFields, setDismissedFields] = useState<Set<string>>(new Set());

  // Save & feedback state
  const [savedReportId, setSavedReportId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<number>(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSent, setFeedbackSent] = useState(false);

  const handleReset = useCallback(() => {
    setRawTranscription(null);
    setReport(null);
    setDonneesManquantes([]);
    setOrganeDetecte("");
    setDismissedFields(new Set());
    setSavedReportId(null);
    setFeedbackRating(0);
    setFeedbackComment("");
    setFeedbackSent(false);
  }, []);

  const handleFormatted = useCallback(
    (newReport: string, organe: string, manquantes: DonneeManquante[]) => {
      setReport(newReport);
      setOrganeDetecte(organe);
      setDonneesManquantes(manquantes);
      setDismissedFields(new Set());
      setSavedReportId(null);
      setFeedbackSent(false);
    },
    []
  );

  const handleReformat = useCallback(
    async (text: string) => {
      if (!text.trim() || reformatting) return;
      setReformatting(true);
      try {
        const result = await formatTranscription(text, report ?? undefined);
        handleFormatted(
          result.formatted_report,
          result.organe_detecte,
          result.donnees_manquantes
        );
      } catch {
        // silent
      } finally {
        setReformatting(false);
      }
    },
    [reformatting, report, handleFormatted]
  );

  const handleDismissField = useCallback((champ: string) => {
    setDismissedFields((prev) => new Set(prev).add(champ));
  }, []);

  // Save report to DB
  const handleSave = useCallback(async () => {
    if (!report || !rawTranscription || saving) return;
    const token = getToken();
    if (!token) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/reports`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          raw_transcription: rawTranscription,
          structured_report: report,
          organe_detecte: organeDetecte,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSavedReportId(data.id);
      }
    } catch {
      // silent
    } finally {
      setSaving(false);
    }
  }, [report, rawTranscription, organeDetecte, saving, getToken]);

  // Send feedback
  const handleFeedback = useCallback(async () => {
    if (!savedReportId || feedbackRating === 0) return;
    const token = getToken();
    if (!token) return;
    try {
      await fetch(`${API_BASE}/reports/${savedReportId}/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          rating: feedbackRating,
          comment: feedbackComment,
        }),
      });
      setFeedbackSent(true);
    } catch {
      // silent
    }
  }, [savedReportId, feedbackRating, feedbackComment, getToken]);

  // Loading state
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
      </div>
    );
  }

  // Not logged in
  if (!user) {
    return <LoginPage onLogin={login} onRegister={register} />;
  }

  // Sub-pages
  if (page === "history") {
    return (
      <HistoryPage
        token={getToken()}
        onBack={() => setPage("app")}
        onOpenReport={() => setPage("app")}
      />
    );
  }

  if (page === "admin") {
    return <AdminPage token={getToken()} onBack={() => setPage("app")} />;
  }

  const hasCompletionData = donneesManquantes.length > 0 || report !== null;

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      {/* Header */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-5">
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-bold tracking-tight">Lexia</h1>
          <span className="text-xs text-muted-foreground">
            {user.name}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {/* Save + New */}
          {report && (
            <>
              {!savedReportId ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSave}
                  disabled={saving}
                >
                  <Save className="h-3.5 w-3.5" />
                  {saving ? "..." : "Sauvegarder"}
                </Button>
              ) : (
                <Badge variant="success" className="text-xs">
                  Sauvegarde
                </Badge>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (!savedReportId && report) {
                    handleSave().then(() => handleReset());
                  } else {
                    handleReset();
                  }
                }}
              >
                Nouveau CR
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPage("history")}
            title="Historique"
          >
            <History className="h-4 w-4" />
          </Button>
          {user.role === "admin" && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setPage("admin")}
              title="Administration"
            >
              <Shield className="h-4 w-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={toggle}>
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={logout} title="Deconnexion">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {/* Main 3-column layout */}
      <main className="flex flex-1 overflow-hidden">
        <section className="w-[340px] shrink-0 overflow-y-auto border-r p-4 scrollbar-thin">
          <RecorderPanel
            rawTranscription={rawTranscription}
            report={report}
            onTranscription={setRawTranscription}
            onFormatted={handleFormatted}
            onReset={handleReset}
            onRawChange={setRawTranscription}
            onReformat={handleReformat}
            reformatting={reformatting}
          />
        </section>

        <section className="flex-1 overflow-y-auto p-5 scrollbar-thin">
          <ReportPanel
            report={report}
            onReportChange={setReport}
            donneesManquantes={donneesManquantes}
            organeDetecte={organeDetecte}
          />

          {/* Feedback section - shown after save */}
          {savedReportId && !feedbackSent && (
            <div className="mx-auto mt-6 max-w-[860px] rounded-lg border bg-card p-4">
              <p className="text-sm font-semibold">
                Votre avis sur ce compte-rendu
              </p>
              <div className="mt-2 flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    onClick={() => setFeedbackRating(n)}
                    className="p-0.5"
                  >
                    <Star
                      className={`h-6 w-6 transition-colors ${
                        n <= feedbackRating
                          ? "fill-warning text-warning"
                          : "text-muted-foreground/30"
                      }`}
                    />
                  </button>
                ))}
              </div>
              <textarea
                placeholder="Commentaire (optionnel) — qu'est-ce qui pourrait etre ameliore ?"
                value={feedbackComment}
                onChange={(e) => setFeedbackComment(e.target.value)}
                className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                rows={2}
              />
              <Button
                size="sm"
                className="mt-2"
                onClick={handleFeedback}
                disabled={feedbackRating === 0}
              >
                Envoyer le feedback
              </Button>
            </div>
          )}

          {feedbackSent && (
            <div className="mx-auto mt-6 max-w-[860px] rounded-lg border border-success/30 bg-success/5 p-3 text-center text-sm text-success">
              Merci pour votre retour !
            </div>
          )}
        </section>

        {hasCompletionData && (
          <section className="w-[300px] shrink-0 overflow-y-auto border-l p-4 scrollbar-thin">
            <CompletionPanel
              donneesManquantes={donneesManquantes}
              organeDetecte={organeDetecte}
              report={report ?? ""}
              onDismiss={handleDismissField}
              dismissedFields={dismissedFields}
            />
          </section>
        )}
      </main>

      <footer className="flex h-7 shrink-0 items-center justify-center border-t bg-card px-4">
        <p className="text-[0.6rem] text-muted-foreground/60">
          Lexia est un outil de productivite pour la mise en forme de comptes rendus. Il ne constitue pas un dispositif medical au sens du reglement (UE) 2017/745. Le praticien reste seul responsable du contenu medical.
        </p>
      </footer>
    </div>
  );
}
