import { useState, useCallback, useEffect, useRef } from "react";
import {
  Mic,
  FileText,
  History,
  Shield,
  LogOut,
  Save,
  Star,
  ChevronRight,
  ListChecks,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { IrisLogo, IrisWordmark } from "./components/IrisLogo";
import { useToast } from "./components/Toast";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import HistoryPage from "./pages/HistoryPage";
import AdminPage from "./pages/AdminPage";
import RecorderPanel from "./components/RecorderPanel";
import ReportPanel from "./components/ReportPanel";
import CompletionPanel from "./components/CompletionPanel";
import { formatTranscription } from "./services/api";
import type { FormatResult, Marker } from "./services/api";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

type Page = "app" | "history" | "admin";
type AppView = "record" | "report";

/* ------------------------------------------------------------------ */
/*  Theme                                                              */
/* ------------------------------------------------------------------ */

function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    const stored = localStorage.getItem("iris_theme");
    return stored ? stored === "dark" : false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
    localStorage.setItem("iris_theme", isDark ? "dark" : "light");
  }, [isDark]);

  const toggle = useCallback(() => setIsDark((p) => !p), []);
  return { isDark, toggle };
}

/* ------------------------------------------------------------------ */
/*  Sidebar                                                            */
/* ------------------------------------------------------------------ */

function Sidebar({
  page,
  setPage,
  activeView,
  setActiveView,
  hasReport,
  isAdmin,
  onLogout,
  completionCount,
  onOpenDrawer,
}: {
  page: Page;
  setPage: (p: Page) => void;
  activeView: AppView;
  setActiveView: (v: AppView) => void;
  hasReport: boolean;
  isAdmin: boolean;
  onLogout: () => void;
  completionCount: number;
  onOpenDrawer: () => void;
}) {
  const items = [
    {
      icon: Mic,
      label: "Dicter",
      active: page === "app" && activeView === "record",
      onClick: () => { setPage("app"); setActiveView("record"); },
    },
    {
      icon: FileText,
      label: "Rapport",
      active: page === "app" && activeView === "report",
      onClick: () => { setPage("app"); setActiveView("report"); },
      disabled: !hasReport,
    },
    {
      icon: ListChecks,
      label: "Champs",
      active: false,
      onClick: onOpenDrawer,
      disabled: !hasReport,
      badge: completionCount > 0 ? completionCount : undefined,
    },
    {
      icon: History,
      label: "Historique",
      active: page === "history",
      onClick: () => setPage("history"),
    },
  ];

  return (
    <aside className="iris-sidebar flex flex-col items-center border-r bg-card/50 py-4 hide-mobile">
      {/* Logo */}
      <button
        onClick={() => { setPage("app"); setActiveView("record"); }}
        className="mb-6 transition-transform hover:scale-110"
        title="Iris"
      >
        <IrisLogo size={28} />
      </button>

      {/* Nav items */}
      <nav className="flex flex-1 flex-col items-center gap-1">
        {items.map((item) => (
          <button
            key={item.label}
            onClick={item.onClick}
            disabled={item.disabled}
            title={item.label}
            className={`
              relative flex h-10 w-10 items-center justify-center rounded-lg transition-all
              ${item.active
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }
              ${item.disabled ? "opacity-30 pointer-events-none" : ""}
            `}
          >
            <item.icon className="h-[18px] w-[18px]" />
            {item.badge !== undefined && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-warning px-1 text-[10px] font-bold text-warning-foreground">
                {item.badge}
              </span>
            )}
          </button>
        ))}

        {isAdmin && (
          <button
            onClick={() => setPage("admin")}
            title="Administration"
            className={`
              flex h-10 w-10 items-center justify-center rounded-lg transition-all
              ${page === "admin"
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }
            `}
          >
            <Shield className="h-[18px] w-[18px]" />
          </button>
        )}
      </nav>

      {/* Bottom actions */}
      <div className="flex flex-col items-center gap-1 pt-2">
        <button
          onClick={onLogout}
          title="Deconnexion"
          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-all hover:bg-accent hover:text-destructive"
        >
          <LogOut className="h-[18px] w-[18px]" />
        </button>
      </div>
    </aside>
  );
}

/* ------------------------------------------------------------------ */
/*  Mobile bottom tabs                                                 */
/* ------------------------------------------------------------------ */

function MobileNav({
  activeView,
  setActiveView,
  hasReport,
  completionCount,
  onOpenDrawer,
  page,
  setPage,
}: {
  activeView: AppView;
  setActiveView: (v: AppView) => void;
  hasReport: boolean;
  completionCount: number;
  onOpenDrawer: () => void;
  page: Page;
  setPage: (p: Page) => void;
}) {
  const tabs = [
    { icon: Mic, label: "Dicter", view: "record" as AppView, onClick: () => { setPage("app"); setActiveView("record"); } },
    { icon: FileText, label: "Rapport", view: "report" as AppView, onClick: () => { setPage("app"); setActiveView("report"); }, disabled: !hasReport },
    { icon: ListChecks, label: "Champs", view: null, onClick: onOpenDrawer, disabled: !hasReport, badge: completionCount },
    { icon: History, label: "Historique", view: null, onClick: () => setPage("history") },
  ];

  return (
    <nav className="iris-mobile-tabs fixed bottom-0 left-0 right-0 z-30 border-t bg-card/95 backdrop-blur-sm">
      <div className="flex items-center justify-around px-2 py-1.5">
        {tabs.map((tab) => (
          <button
            key={tab.label}
            onClick={tab.onClick}
            disabled={tab.disabled}
            className={`
              relative flex flex-col items-center gap-0.5 rounded-lg px-3 py-1.5 text-[10px] font-medium transition-all
              ${(page === "app" && tab.view === activeView)
                ? "text-primary"
                : "text-muted-foreground"
              }
              ${tab.disabled ? "opacity-30 pointer-events-none" : ""}
            `}
          >
            <tab.icon className="h-5 w-5" />
            {tab.label}
            {tab.badge !== undefined && tab.badge > 0 && (
              <span className="absolute right-1 top-0 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-warning px-0.5 text-[8px] font-bold text-warning-foreground">
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/*  Feedback panel                                                     */
/* ------------------------------------------------------------------ */

function FeedbackPanel({
  savedReportId,
  feedbackSent,
  getToken,
  onSent,
}: {
  savedReportId: string;
  feedbackSent: boolean;
  getToken: () => string | null;
  onSent: () => void;
}) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const { toast } = useToast();

  const handleSubmit = async () => {
    if (rating === 0) return;
    const token = getToken();
    if (!token) return;
    try {
      await fetch(`${API_BASE}/reports/${savedReportId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ rating, comment }),
      });
      onSent();
      toast("Merci pour votre retour", "success");
    } catch {
      toast("Erreur lors de l'envoi du feedback", "error");
    }
  };

  if (feedbackSent) {
    return (
      <div className="mx-auto mt-4 max-w-3xl rounded-lg border border-success/20 bg-success/5 p-3 text-center text-sm text-success">
        Merci pour votre retour
      </div>
    );
  }

  return (
    <div className="mx-auto mt-4 max-w-3xl rounded-xl border bg-card p-5">
      <p className="text-sm font-semibold">Votre avis sur ce compte-rendu</p>
      <div className="mt-2.5 flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} onClick={() => setRating(n)} className="p-0.5">
            <Star
              className={`h-6 w-6 transition-colors ${
                n <= rating ? "fill-warning text-warning" : "text-muted-foreground/30"
              }`}
            />
          </button>
        ))}
      </div>
      <textarea
        placeholder="Commentaire optionnel"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        className="mt-2 w-full rounded-lg border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        rows={2}
      />
      <Button size="sm" className="mt-2" onClick={handleSubmit} disabled={rating === 0}>
        Envoyer
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main App                                                           */
/* ------------------------------------------------------------------ */

export default function App() {
  useTheme();
  const { user, loading, login, register, logout, getToken } = useAuth();
  const { toast } = useToast();
  const [page, setPage] = useState<Page>("app");
  const [activeView, setActiveView] = useState<AppView>("record");

  // Report state
  const [rawTranscription, setRawTranscription] = useState<string | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [markers, setMarkers] = useState<Marker[]>([]);
  const [organeDetecte, setOrganeDetecte] = useState("");
  const [reformatting, setReformatting] = useState(false);
  const [dismissedFields, setDismissedFields] = useState<Set<string>>(new Set());

  // Save & feedback
  const [savedReportId, setSavedReportId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  // Completion drawer
  const [drawerOpen, setDrawerOpen] = useState(false);

  const activeFieldCount = markers.filter(
    (m) => m.severity === "error" && !dismissedFields.has(m.field)
  ).length;

  // --- Autosave dans localStorage ---
  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!report || !rawTranscription) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      localStorage.setItem("iris_autosave", JSON.stringify({
        report,
        rawTranscription,
        organeDetecte,
        timestamp: Date.now(),
      }));
    }, 2000);
    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  }, [report, rawTranscription, organeDetecte]);

  // Restaurer l'autosave au chargement
  useEffect(() => {
    const saved = localStorage.getItem("iris_autosave");
    if (!saved || report) return;
    try {
      const data = JSON.parse(saved);
      const age = Date.now() - (data.timestamp ?? 0);
      if (age < 24 * 60 * 60 * 1000 && data.report) {
        setReport(data.report);
        setRawTranscription(data.rawTranscription ?? null);
        setOrganeDetecte(data.organeDetecte ?? "");
        setActiveView("report");
        toast("Brouillon restaure automatiquement", "info");
      }
    } catch { /* ignore corrupt autosave */ }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleReset = useCallback(() => {
    setRawTranscription(null);
    setReport(null);
    setMarkers([]);
    setOrganeDetecte("");
    setDismissedFields(new Set());
    setSavedReportId(null);
    setFeedbackSent(false);
    setActiveView("record");
    localStorage.removeItem("iris_autosave");
  }, []);

  const handleFormatted = useCallback((result: FormatResult) => {
    setReport(result.formatted_report);
    setOrganeDetecte(result.classification.top.organe);
    setMarkers(result.markers);
    setDismissedFields(new Set());
    setSavedReportId(null);
    setFeedbackSent(false);
    setActiveView("report");
  }, []);

  const handleReformat = useCallback(
    async (text: string) => {
      if (!text.trim() || reformatting) return;
      setReformatting(true);
      try {
        const result = await formatTranscription(text);
        handleFormatted(result);
      } catch {
        toast("Erreur lors du formatage", "error");
      } finally {
        setReformatting(false);
      }
    },
    [reformatting, report, handleFormatted, toast]
  );

  const handleDismissField = useCallback((field: string) => {
    setDismissedFields((prev) => new Set(prev).add(field));
  }, []);

  const handleSave = useCallback(async () => {
    if (!report || !rawTranscription || saving) return;
    const token = getToken();
    if (!token) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          raw_transcription: rawTranscription,
          structured_report: report,
          organe_detecte: organeDetecte,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSavedReportId(data.id);
        toast("Compte-rendu sauvegarde", "success");
      } else {
        toast("Erreur lors de la sauvegarde", "error");
      }
    } catch {
      toast("Erreur lors de la sauvegarde", "error");
    } finally {
      setSaving(false);
    }
  }, [report, rawTranscription, organeDetecte, saving, getToken, toast]);

  // --- Raccourcis clavier globaux ---
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      switch (e.key) {
        case "s":
          e.preventDefault();
          if (report && !savedReportId) handleSave();
          break;
        case "e":
          e.preventDefault();
          if (report) setActiveView("report");
          break;
        case "d":
          e.preventDefault();
          setActiveView("record");
          break;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [report, savedReportId, handleSave]);

  // Loading
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <IrisLogo size={40} className="animate-breathe" />
          <span className="text-sm text-muted-foreground">Chargement...</span>
        </div>
      </div>
    );
  }

  // Login
  if (!user) {
    return <LoginPage onLogin={login} onRegister={register} />;
  }

  // Admin stays as separate page
  if (page === "admin") {
    return <AdminPage token={getToken()} onBack={() => setPage("app")} />;
  }

  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <Sidebar
        page={page}
        setPage={setPage}
        activeView={activeView}
        setActiveView={setActiveView}
        hasReport={report !== null}
        isAdmin={user.role === "admin"}
        onLogout={logout}
        completionCount={activeFieldCount}
        onOpenDrawer={() => setDrawerOpen(true)}
      />

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card/30 px-5">
          <div className="flex items-center gap-3">
            <IrisWordmark className="text-lg show-mobile-only" />
            <div className="flex items-center gap-2 hide-mobile">
              <h2 className="text-sm font-semibold">
                {activeView === "record" ? "Dictee" : "Compte-rendu"}
              </h2>
              {organeDetecte && organeDetecte !== "non_determine" && (
                <Badge variant="default" className="text-[10px] font-mono uppercase tracking-wider">
                  {organeDetecte.replace(/_/g, " ")}
                </Badge>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {report && (
              <>
                {!savedReportId ? (
                  <Button variant="outline" size="sm" onClick={handleSave} disabled={saving}>
                    <Save className="h-3.5 w-3.5" />
                    <span className="hide-mobile">{saving ? "..." : "Sauvegarder"}</span>
                  </Button>
                ) : (
                  <Badge variant="success" className="text-xs">Sauvegarde</Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (!savedReportId && report) {
                      if (window.confirm("Sauvegarder avant de creer un nouveau CR ?")) {
                        handleSave().then(() => handleReset());
                      } else {
                        handleReset();
                      }
                    } else {
                      handleReset();
                    }
                  }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span className="hide-mobile">Nouveau CR</span>
                </Button>
              </>
            )}
            {report && (
              <Button
                variant="ghost"
                size="sm"
                className="hide-mobile"
                onClick={() => setDrawerOpen(true)}
              >
                <ListChecks className="h-3.5 w-3.5" />
                Champs obligatoires
                {activeFieldCount > 0 && (
                  <span className="ml-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-warning px-1 text-[10px] font-bold text-warning-foreground">
                    {activeFieldCount}
                  </span>
                )}
              </Button>
            )}
          </div>
        </header>

        {/* Content area */}
        <main className="flex flex-1 overflow-hidden">
          {page === "history" ? (
            <section className="flex-1 overflow-y-auto p-6 scrollbar-thin">
              <HistoryPage token={getToken()} onBack={() => setPage("app")} onOpenReport={() => setPage("app")} />
            </section>
          ) : (
          <>
          {/* Left: Recorder */}
          <section className="w-[380px] shrink-0 overflow-y-auto border-r p-4 scrollbar-thin max-md:hidden">
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

          {/* Center: Report */}
          <section className="flex-1 overflow-y-auto p-5 scrollbar-thin">
            <ReportPanel
              report={report}
              onReportChange={setReport}
              markers={markers}
              organeDetecte={organeDetecte}
            />

            {savedReportId && (
              <FeedbackPanel
                savedReportId={savedReportId}
                feedbackSent={feedbackSent}
                getToken={getToken}
                onSent={() => setFeedbackSent(true)}
              />
            )}
          </section>

          {/* Mobile: show active view only */}
          <div className="hidden max-md:flex max-md:flex-1 max-md:flex-col max-md:overflow-hidden">
            {activeView === "record" ? (
              <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
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
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
                <ReportPanel
                  report={report}
                  onReportChange={setReport}
                  markers={markers}
                  organeDetecte={organeDetecte}
                />
              </div>
            )}
          </div>
          </>
          )}
        </main>

        {/* Footer */}
        <footer className="flex h-7 shrink-0 items-center justify-center border-t px-4">
          <p className="text-[0.55rem] text-muted-foreground/50">
            Iris est un outil de productivite. Il ne constitue pas un dispositif medical (UE 2017/745). Le praticien reste seul responsable du contenu.
          </p>
        </footer>
      </div>

      {/* Completion drawer */}
      <div
        className={`iris-drawer-overlay ${drawerOpen ? "open" : ""}`}
        onClick={() => setDrawerOpen(false)}
      />
      <div className={`iris-drawer border-l bg-card shadow-2xl ${drawerOpen ? "open" : ""}`}>
        <div className="flex h-full flex-col overflow-y-auto p-4 scrollbar-thin">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Champs obligatoires</h3>
            <button
              onClick={() => setDrawerOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <CompletionPanel
            markers={markers}
            organeDetecte={organeDetecte}
            onDismiss={handleDismissField}
            dismissedFields={dismissedFields}
          />
        </div>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav
        activeView={activeView}
        setActiveView={setActiveView}
        hasReport={report !== null}
        completionCount={activeFieldCount}
        onOpenDrawer={() => setDrawerOpen(true)}
        page={page}
        setPage={setPage}
      />
    </div>
  );
}
