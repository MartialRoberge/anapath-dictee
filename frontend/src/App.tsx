import { useState, useCallback, useEffect, useMemo, useRef } from "react";
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
  LayoutPanelLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MarcLogo, MarcWordmark } from "./components/MarcLogo";
import { useToast } from "./components/toast-context";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import HistoryPage from "./pages/HistoryPage";
import AdminPage from "./pages/AdminPage";
import RecorderPanel from "./components/RecorderPanel";
import CompletionPanel from "./components/CompletionPanel";
import { formatTranscription, getReport, iterateReport, saveReport, sendFeedback } from "./services/api";
import { useEtudeDossier } from "./hooks/useEtudeDossier";
import PanneauExplicabilite from "./components/travail/PanneauExplicabilite";
import CompteRenduTravail from "./components/travail/CompteRenduTravail";
import ReportPanel from "./components/ReportPanel";
import CodificationPanel from "./components/CodificationPanel";
import Confirmation from "./components/ui/Confirmation";
import { signalerVues } from "./services/etude";
import {
  decouperEnBlocs,
  remplacerTexteDuBloc,
  remplirTrou,
} from "./lib/blocsTexte";
import type { Bloc, Trou } from "./lib/blocsTexte";
import type { AjoutContexte } from "./components/analyse/BarreAjout";
import Glissiere from "./components/analyse/Glissiere";
import BarreAjout from "./components/analyse/BarreAjout";
import { useDicteeAppoint } from "./hooks/useDicteeAppoint";
import { useNavigationInterne } from "./hooks/useNavigationInterne";
import { construirePoints, type ActionPoint, type PointATraiter } from "./lib/pointsATraiter";
import { useHorlogeEtude } from "./hooks/useHorlogeEtude";
import { useMesureErgonomie } from "./hooks/useMesureErgonomie";
import Questionnaire from "./components/questionnaire/Questionnaire";
import type {
  FormatResult,
  Marker,
  ReportTrace,
  CoherenceVerdict,
  DonneeManquante,
} from "./services/api";
import ExplainPanel from "./components/ExplainPanel";
import { computeCompletion } from "./lib/completion";
import {
  createDraftId,
  loadLatestDraft,
  removeDraft,
  saveDraft,
} from "./lib/drafts";
// v3 backend: FormatResult has formatted_report, organe_detecte, markers (adapted from donnees_manquantes)

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
  setActiveView,
  isAdmin,
  onLogout,
}: {
  page: Page;
  setPage: (p: Page) => void;
  setActiveView: (v: AppView) => void;
  isAdmin: boolean;
  onLogout: () => void;
}) {
  // Espace de travail unifié : un seul point d'entrée « Atelier »
  // (le recorder et le compte-rendu cohabitent dans la même vue).
  const items: {
    icon: typeof LayoutPanelLeft;
    label: string;
    active: boolean;
    onClick: () => void;
    disabled?: boolean;
    badge?: number;
  }[] = [
    {
      icon: LayoutPanelLeft,
      label: "Atelier",
      active: page === "app",
      onClick: () => { setPage("app"); setActiveView("record"); },
    },
    // « À compléter » n'est plus un panneau a part : la meme liste vit dans
    // l'analyse, a cote du texte, et deux listes identiques a deux endroits
    // faisaient croire a deux choses differentes.
    {
      icon: History,
      label: "Historique",
      active: page === "history",
      onClick: () => setPage("history"),
    },
  ];

  return (
    <aside className="iris-sidebar flex flex-col items-center border-r bg-card/50 py-4 hide-mobile">
      {/* Logo unique dans le header : pas de doublon ici. */}
      {/* Nav items */}
      <nav className="mt-1 flex flex-1 flex-col items-center gap-1">
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
  // Espace de travail unifié : un seul bouton contextuel qui bascule
  // entre la dictée et le compte-rendu (ou ramène à l'atelier).
  let contextual: { icon: typeof Mic; label: string; active: boolean; onClick: () => void };
  if (page !== "app") {
    contextual = { icon: LayoutPanelLeft, label: "Atelier", active: false, onClick: () => setPage("app") };
  } else if (activeView === "report") {
    contextual = { icon: Mic, label: "Dicter", active: false, onClick: () => setActiveView("record") };
  } else if (hasReport) {
    contextual = { icon: FileText, label: "Voir le CR", active: false, onClick: () => setActiveView("report") };
  } else {
    contextual = { icon: Mic, label: "Dicter", active: true, onClick: () => setActiveView("record") };
  }

  const tabs: Array<{
    icon: typeof Mic;
    label: string;
    active: boolean;
    onClick: () => void;
    disabled?: boolean;
    badge?: number;
  }> = [
    contextual,
    { icon: ListChecks, label: "Champs", active: false, onClick: onOpenDrawer, disabled: !hasReport, badge: completionCount },
    { icon: History, label: "Historique", active: page === "history", onClick: () => setPage("history") },
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
              ${tab.active ? "text-primary" : "text-muted-foreground"}
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
      await sendFeedback(savedReportId, rating, comment);
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
  // Le retour arriere du navigateur reste dans MARC : sortir du site en pleine
  // redaction ferait disparaitre le compte rendu en cours.
  useNavigationInterne(page, setPage);
  const [activeView, setActiveView] = useState<AppView>("record");

  // Report state
  const [rawTranscription, setRawTranscription] = useState<string | null>(null);
  // La dictee d'APPOINT : completer un compte rendu deja redige. Elle est
  // distincte de la dictee initiale, qui le produit.
  const dicteeAppoint = useDicteeAppoint();

  /** Les alertes TELLES QUELLES : c'est d'elles que viennent declencheur,
   *  raison et options. Les `markers` les ont deja aplaties. */
  const [manquants, setManquants] = useState<DonneeManquante[]>([]);
  /** Le bloc dont l'explication est ouverte a gauche, et le trou vise. */
  const [selection, setSelection] = useState<string | null>(null);
  const [trouSelectionne, setTrouSelectionne] = useState<Trou | null>(null);
  /** Demande de defilement vers un bloc, depuis la checklist. */
  const [allerA, setAllerA] = useState<string | null>(null);
  /**
   * Deux modes sur le MEME texte : travailler, ou ecrire.
   *
   * La surface a blocs sert a trancher ce que MARC propose. Elle ne remplace
   * pas l'ecriture libre — un compte rendu se retouche partout, tout le temps,
   * et n'avoir que des boutons obligeait a passer par « corriger » puis a
   * retaper la phrase entiere pour changer un mot.
   *
   * Un seul texte derriere les deux : basculer ne perd rien.
   */
  const [modeEdition, setModeEdition] = useState(false);
  /** La demande de confirmation avant de repartir sur un nouveau compte rendu. */
  const [confirmerNouveau, setConfirmerNouveau] = useState(false);
  /** Ce qui a ete verse au contexte, du plus recent au plus ancien. */
  const [historiqueAjouts, setHistoriqueAjouts] = useState<AjoutContexte[]>([]);

  // L'instrumentation de l'etude. Elle n'a aucun pouvoir sur la generation :
  // si elle echoue, le praticien redige quand meme. On ne bloque jamais un
  // compte rendu pour une mesure.
  const etude = useEtudeDossier();

  // L'horloge deduit les interruptions du temps de revision. Sans elle, le
  // temps mesure est celui du fauteuil, pas celui du travail.
  const horloge = useHorlogeEtude(etude.dossierId);

  // Ce que le praticien regarde, ou il clique, jusqu'ou il fait defiler. En
  // interne : brancher un traceur etranger sur un outil medical annulerait
  // l'argument de souverainete.
  useMesureErgonomie(etude.dossierId);

  // Le questionnaire a poser MAINTENANT. Le par-cas suit chaque validation ; le
  // periodique tombe tous les cinq comptes rendus et c'est le SERVEUR qui le
  // dit — un compteur tenu par le client deriverait d'un poste a l'autre.
  const [questionnaireDu, setQuestionnaireDu] = useState<
    "par_cas" | "periodique" | null
  >(null);
  const [dossierQuestionne, setDossierQuestionne] = useState<string | null>(null);

  // Partage de l'ecran entre l'analyse et le compte rendu. Aucune valeur fixe
  // ne convient : juger des points demande de la place a gauche, ecrire en
  // demande a droite. Le praticien arbitre, et son choix survit au dossier
  // suivant.
  const [partAnalyse, setPartAnalyse] = useState<number>(() => {
    const garde = Number(localStorage.getItem("marc_part_analyse"));
    return Number.isFinite(garde) && garde > 0.15 && garde < 0.7 ? garde : 0.38;
  });
  useEffect(() => {
    localStorage.setItem("marc_part_analyse", String(partAnalyse));
  }, [partAnalyse]);

  // Ce qui a deja ete traite, et le point survole. Le survol pilote le
  // surlignage du passage dans le compte rendu.
  const [pointsTraites, setPointsTraites] = useState<Record<string, string>>({});

  // La transcription est aussi tenue dans une ref : le panneau appelle
  // onTranscription puis onFormatted dans le meme tour de rendu, et l'etat
  // n'est pas encore a jour quand le second s'execute.
  const transcriptionRef = useRef<string | null>(null);
  const noterTranscription = useCallback((brut: string | null) => {
    transcriptionRef.current = brut;
    setRawTranscription(brut);
  }, []);
  const [report, setReport] = useState<string | null>(null);
  const [markers, setMarkers] = useState<Marker[]>([]);
  // Texte sur lequel les marqueurs ont ete calcules : des que le CR change
  // (edition, reouverture depuis l'historique), ils sont perimes et
  // l'interface ne doit plus affirmer que tout est complet.
  const [markersReport, setMarkersReport] = useState<string | null>(null);
  const [organeDetecte, setOrganeDetecte] = useState("");
  const [explication, setExplication] = useState<{
    trace: ReportTrace;
    warnings: string[];
    coherence: CoherenceVerdict;
  } | null>(null);
  const [reformatting, setReformatting] = useState(false);
  const [dismissedFields, setDismissedFields] = useState<Set<string>>(new Set());

  // Save & feedback
  const [savedReportId, setSavedReportId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  // Completion drawer
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Source de verite unique des trois indicateurs de completude.
  const completion = useMemo(
    () =>
      computeCompletion({
        report,
        markers,
        dismissedFields,
        organeDetecte,
        markersMatchReport: markersReport !== null && markersReport === report,
      }),
    [report, markers, dismissedFields, organeDetecte, markersReport],
  );

  // --- Autosave dans localStorage (un brouillon par dossier) ---
  const [draftId, setDraftId] = useState<string | null>(null);
  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!report || !rawTranscription || !draftId) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      saveDraft(draftId, {
        report,
        rawTranscription,
        organeDetecte,
        explication,
        markers,
        manquants,
        timestamp: Date.now(),
      });
    }, 2000);
    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  }, [draftId, report, rawTranscription, organeDetecte, explication, markers, manquants]);

  // Restaurer le brouillon le plus recent au chargement
  useEffect(() => {
    const latest = loadLatestDraft();
    if (!latest || report) return;
    setDraftId(latest.id);
    setReport(latest.draft.report);
    setRawTranscription(latest.draft.rawTranscription);
    setOrganeDetecte(latest.draft.organeDetecte);
    setExplication(latest.draft.explication);
    setMarkers(latest.draft.markers ?? []);
    setManquants(latest.draft.manquants ?? []);
    // Le CR de reference des marqueurs, sans quoi la completude se croit
    // calculee sur un autre texte et se vide.
    setMarkersReport(latest.draft.report);
    setActiveView("report");
    toast("Brouillon restaure automatiquement", "info");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleReset = useCallback(() => {
    if (draftId) removeDraft(draftId);
    setDraftId(null);
    setRawTranscription(null);
    setReport(null);
    setMarkers([]);
    setMarkersReport(null);
    setOrganeDetecte("");
    setExplication(null);
    setDismissedFields(new Set());
    setSavedReportId(null);
    setFeedbackSent(false);
    setActiveView("record");
  }, [draftId]);

  const pointsATraiter = useMemo(() => {
    // Le college rend ses verdicts par ASSERTION, l'etude par identifiant de
    // proposition : on les rapproche sur le texte, qui est le seul point commun
    // et qui vient du meme decoupage serveur.
    const soumissions = explication?.trace?.college?.soumissions ?? [];
    const parAssertion = new Map(soumissions.map((s) => [s.assertion.trim(), s]));

    const justifications: Record<string, string[]> = {};
    const citations: Record<string, string> = {};
    const voix: Record<string, { pour: number; total: number }> = {};

    for (const proposition of etude.propositions) {
      const soumission = parAssertion.get(proposition.valeur_proposee.trim());
      if (!soumission) continue;
      justifications[proposition.id] = soumission.justifications;
      voix[proposition.id] = {
        pour: soumission.voix_pour,
        total: soumission.voix_total,
      };
      if (
        rawTranscription &&
        soumission.empan_debut !== null &&
        soumission.empan_fin !== null
      ) {
        citations[proposition.id] = rawTranscription.slice(
          soumission.empan_debut,
          soumission.empan_fin,
        );
      }
    }

    return construirePoints({
      propositions: etude.propositions,
      justifications,
      citations,
      voix,
      marqueurs: completion.pending.map((champ) => champ.marker),
      coherence: explication?.coherence?.issues ?? [],
    });
  }, [etude.propositions, explication, completion.pending, rawTranscription]);

  /** Ce que MARC a verifie sans rien demander : rassurant, donc hors de la file. */
  const pointsVerifies = useMemo(
    () =>
      (explication?.trace?.signalements ?? [])
        .filter((signalement) => signalement.categorie === "coherence")
        .map((signalement) => ({ libelle: signalement.message })),
    [explication],
  );

  /**
   * Les codes proposes, en lecture seule : ceux qui demandent une decision sont
   * dans la file, pas ici. La liste vient des propositions de type "code" deja
   * tranchees — afficher un code non encore juge en bas de panneau le ferait
   * passer pour acquis.
   */
  const codesAffiches = useMemo(
    () =>
      etude.propositions
        .filter((p) => p.type === "code" && p.id in pointsTraites)
        .map((p) => ({
          position: p.sous_type ?? "ADICAP",
          code: p.valeur_proposee,
          libelle: p.chemin ?? "",
        })),
    [etude.propositions, pointsTraites],
  );

  /**
   * Le complement d'un trou, retrouve par le nom du champ.
   *
   * On rapproche sur le NOM parce que c'est le seul lien entre le marqueur
   * ecrit dans le texte — « [A COMPLETER: taille] » — et l'alerte qui explique
   * pourquoi il est attendu. Deux trous du meme nom partagent donc la meme
   * explication, ce qui est correct : c'est la meme question posee deux fois.
   */
  const renseignerTrou = useCallback(
    (champ: string) => {
      const cle = champ.trim().toLowerCase();
      const trouve = manquants.find(
        (m) => m.champ.trim().toLowerCase() === cle,
      );
      if (!trouve) return undefined;
      return {
        declencheur: trouve.declencheur ?? null,
        raison: trouve.raison ?? null,
        options: trouve.options ?? [],
      };
    },
    [manquants],
  );

  /** Le compte rendu decoupe en surface de travail. Refait a chaque frappe :
   *  le TEXTE est la source de verite, le decoupage n'en est qu'une lecture. */
  const blocs = useMemo(
    () => decouperEnBlocs({ cr: report ?? "", points: pointsATraiter, renseignerTrou }),
    [report, pointsATraiter, renseignerTrou],
  );

  /** Decisions indexees par BLOC : le bloc est ce que le praticien voit. */
  const decisionsParBloc = useMemo(() => {
    const table: Record<string, string> = {};
    for (const bloc of blocs) {
      if (bloc.point === null) continue;
      const prise = pointsTraites[bloc.point.id];
      if (prise === undefined) continue;
      const action = bloc.point.actions.find((a) => a.decision === prise);
      table[bloc.id] = action?.libelle ?? prise;
    }
    return table;
  }, [blocs, pointsTraites]);

  /** Ce qui reste a verifier, pour que le bouton de validation le dise. */
  const pointsRestants = useMemo(
    () => pointsATraiter.filter((point) => !(point.id in pointsTraites)).length,
    [pointsATraiter, pointsTraites],
  );

  const deciderPoint = useCallback(
    async (
      point: PointATraiter,
      action: ActionPoint,
      valeur?: string,
      nature?: string,
    ) => {
      // On enregistre AVANT de marquer traite : marquer d'abord ferait
      // disparaitre le point de la file meme si l'envoi echoue, et le praticien
      // croirait avoir decide.
      const proposition = etude.propositions.find((p) => p.id === point.id);
      if (proposition) {
        const resultat = await etude.decider(
          proposition,
          action.decision as never,
          {
            ...(valeur ? { valeur_retenue: valeur } : {}),
            // La nature separe "le systeme s'est trompe" de "j'ecris
            // autrement". Sans elle, le taux publie melange les deux.
            ...(nature ? { nature_correction: nature } : {}),
          },
        );
        if (resultat === null) return;
      }
      setPointsTraites((actuel) => ({ ...actuel, [point.id]: action.decision }));
      setSelection(null);
      setTrouSelectionne(null);
    },
    [etude],
  );

  /* ---------------- Les gestes, tous faits DANS le texte -------------- */

  const deciderBloc = useCallback(
    async (bloc: Bloc, action: ActionPoint, valeur?: string) => {
      if (bloc.point === null) return;
      // On laisse remonter l'echec : le bloc affiche l'erreur et RESTE a
      // decider. L'avaler ferait croire la decision enregistree alors qu'elle
      // est perdue, et l'etude compterait un blanc pour un jugement.
      await deciderPoint(bloc.point, action, valeur);
    },
    // deciderPoint est defini plus haut ; la dependance est explicite.
    [deciderPoint],
  );

  /**
   * Combler un trou MODIFIE LE TEXTE, et enregistre la mesure.
   *
   * Les deux, et dans cet ordre. Le texte est ce qui part dans le dossier du
   * patient ; la mesure est ce qui alimente l'etude. N'ecrire que le texte
   * perdrait la completude ; n'enregistrer que la mesure laisserait le trou
   * beant sous les yeux du praticien.
   */
  /** Modifier une phrase EN PLACE : le texte du compte rendu change, et
   *  c'est tout. La decision « corrige » part de son cote, depuis le bloc. */
  const editerBloc = useCallback((bloc: Bloc, texte: string) => {
    setReport((actuel) =>
      actuel ? remplacerTexteDuBloc(actuel, bloc, texte) : actuel,
    );
  }, []);

  const remplirTrouDuBloc = useCallback(
    (bloc: Bloc, trou: Trou, valeur: string) => {
      setReport((actuel) => (actuel ? remplirTrou(actuel, bloc, trou, valeur) : actuel));
      const point = pointsATraiter.find(
        (p) =>
          p.origine === "champ_manquant" &&
          p.detail.trim().toLowerCase().includes(trou.champ.trim().toLowerCase()),
      );
      if (point) {
        const action = point.actions.find((a) => a.decision === "pertinent_ajoute");
        if (action) void deciderPoint(point, action, valeur);
      }
    },
    [pointsATraiter, deciderPoint],
  );

  /** Le champ ne s'applique pas ici : le marqueur disparait du texte, et
   *  l'etude enregistre un FAUX POSITIF de completude — c'est une mesure
   *  precieuse, pas un abandon. */
  const ecarterTrouDuBloc = useCallback(
    (bloc: Bloc, trou: Trou) => {
      setReport((actuel) => (actuel ? remplirTrou(actuel, bloc, trou, "") : actuel));
      const point = pointsATraiter.find(
        (p) =>
          p.origine === "champ_manquant" &&
          p.detail.trim().toLowerCase().includes(trou.champ.trim().toLowerCase()),
      );
      if (point) {
        const action = point.actions.find((a) => a.decision === "non_pertinent");
        if (action) void deciderPoint(point, action);
      }
    },
    [pointsATraiter, deciderPoint],
  );

  /**
   * Consulter l'explicabilite. C'EST UNE MESURE, pas un simple affichage :
   * l'etude compare les decisions prises apres consultation du motif a celles
   * prises sans. Le signal part sur un acte DELIBERE — un clic — jamais au
   * survol, qui porterait le taux a 100 % et le rendrait inexploitable.
   */
  /**
   * L'AFFICHAGE REEL D'UN BLOC, groupe puis envoye.
   *
   * Sans ce signal, toutes les propositions restent « non vu » et l'etude
   * publie un faux : elle ne peut plus distinguer un bloc qui n'a jamais paru
   * d'un bloc que le praticien a vu et laisse.
   *
   * On accumule et on envoie par paquets : un observateur de defilement voit
   * entrer plusieurs blocs d'un coup, et un appel par bloc perdrait des
   * signaux au premier ralentissement reseau — ces blocs seraient alors
   * comptes non vus alors qu'ils l'ont bien ete.
   */
  const enAttenteDeVue = useRef<Set<string>>(new Set());
  const minuterieVue = useRef<number | null>(null);

  const signalerBlocVu = useCallback(
    (bloc: Bloc) => {
      const dossier = etude.dossierId;
      if (bloc.point === null || dossier === null) return;
      enAttenteDeVue.current.add(bloc.point.id);
      if (minuterieVue.current !== null) return;
      minuterieVue.current = window.setTimeout(() => {
        const lot = [...enAttenteDeVue.current];
        enAttenteDeVue.current.clear();
        minuterieVue.current = null;
        void signalerVues(dossier, lot);
      }, 400);
    },
    [etude.dossierId],
  );

  const expliquerBloc = useCallback((bloc: Bloc, trou: Trou | null) => {
    setSelection(bloc.id);
    setTrouSelectionne(trou);
  }, []);

  const handleFormatted = useCallback((result: FormatResult) => {
    setReport(result.formatted_report);
    setOrganeDetecte(result.organe_detecte);
    setMarkers(result.markers);
    setManquants(result.manquants);
    setMarkersReport(result.formatted_report);
    // Un nouveau formatage prolonge le dossier en cours : meme brouillon.
    setDraftId((prev) => prev ?? createDraftId());
    setExplication({
      trace: result.trace,
      warnings: result.warnings,
      coherence: result.coherence,
    });
    setDismissedFields(new Set());
    setSavedReportId(null);
    setFeedbackSent(false);
    setActiveView("report");

    // Le dossier d'etude s'ouvre ICI, au moment ou le praticien voit le compte
    // rendu : c'est cet instant qui date l'affichage des propositions, donc
    // toutes les latences. L'ouvrir plus tot mesurerait le temps de calcul du
    // serveur au lieu du temps de lecture.
    const transcription = transcriptionRef.current;
    if (transcription) {
      void etude.ouvrir({
        transcription,
        cr_propose: result.formatted_report,
        organe: result.organe_detecte || null,
        alertes: result.markers.map((marqueur) => ({
          champ: marqueur.field,
          description: marqueur.message,
          section: marqueur.section,
        })),
      });
    }
  }, [etude]);

  /**
   * Ajouter au compte rendu sans tout redicter.
   *
   * Le texte ajoute repasse par le moteur avec la dictee d'origine : il est
   * relu et juge comme le reste. Un ajout n'est pas un passe-droit, sinon il
   * suffirait d'ecrire une phrase pour contourner tous les garde-fous.
   */
  const ajouterAuCompteRendu = useCallback(
    async (texte: string, voix = false) => {
      if (!report) return;
      // L'indicateur est POSE ICI et pas ailleurs : l'appel dure plusieurs
      // secondes, et sans retour visuel le praticien croit que rien ne part.
      // C'est ce qui donnait l'impression que la barre d'ajout etait cassee.
      setReformatting(true);
      try {
        const resultat = await iterateReport(report, texte);
        handleFormatted(resultat);
        noterTranscription(
          rawTranscription ? `${rawTranscription} ${texte}` : texte,
        );
        // L'ajout reste VISIBLE apres coup. Sans historique, le praticien qui
        // vient de dicter une precision ne voit plus nulle part ce qu'il a
        // ajoute : le texte a change quelque part, et il doit le retrouver a
        // l'oeil pour verifier que la transcription l'a bien compris.
        setHistoriqueAjouts((actuel) => [
          { id: `${Date.now()}`, texte, voix, a: Date.now() },
          ...actuel,
        ]);
      } finally {
        setReformatting(false);
      }
    },
    [report, rawTranscription, handleFormatted, noterTranscription],
  );


  // Rouvre un CR de l'historique dans l'editeur (charge le detail complet).
  const handleOpenReport = useCallback(
    async (reportId: string) => {
      try {
        const data = await getReport(reportId);
        setReport(data.structured_report ?? "");
        setRawTranscription(data.raw_transcription ?? null);
        setOrganeDetecte(data.organe_detecte ?? "");
        // Aucun marqueur pour un CR historise : la completude est recalculee
        // depuis le texte et signalee comme non verifiee par le moteur.
        setMarkers([]);
        setMarkersReport(null);
        // Chaque dossier a son propre brouillon : plus d'ecrasement silencieux.
        setDraftId(data.id ?? reportId);
        setExplication(null); // pas de trace pour un CR historisé
        setDismissedFields(new Set());
        setSavedReportId(data.id ?? reportId);
        setFeedbackSent(
          data.feedback_rating !== null && data.feedback_rating !== undefined,
        );
        setPage("app");
        setActiveView("report");
        toast("Compte-rendu ouvert", "success");
      } catch (err) {
        toast(
          err instanceof Error ? err.message : "Erreur de chargement",
          "error",
        );
      }
    },
    [toast],
  );

  const handleReformat = useCallback(
    async (text: string) => {
      if (!text.trim() || reformatting) return;
      setReformatting(true);
      try {
        const result = await formatTranscription(text, report ?? undefined);
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
      const data = await saveReport({
        raw_transcription: rawTranscription,
        structured_report: report,
        organe_detecte: organeDetecte,
      });
      setSavedReportId(data.id);
      // L'horloge se ferme AVANT la cloture : une pause en cours au moment de
      // valider serait perdue, et c'est systematiquement la derniere
      // interruption du dossier.
      const dossier = etude.dossierId;
      await horloge.cloturer();
      const resultat = await etude.clore({ cr_valide: report });
      if (dossier) {
        setDossierQuestionne(dossier);
        setQuestionnaireDu(
          resultat?.questionnaire_periodique_du ? "periodique" : "par_cas",
        );
      }
      toast("Compte-rendu sauvegarde", "success");
    } catch {
      toast("Erreur lors de la sauvegarde", "error");
    } finally {
      setSaving(false);
    }
  }, [report, rawTranscription, organeDetecte, saving, getToken, toast, etude, horloge]);

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
          <MarcLogo size={40} className="animate-breathe" />
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

  // Le questionnaire s'affiche IMMEDIATEMENT apres la validation, jamais en
  // fin de session : un jugement retrospectif global ne vaut rien.
  const questionnaireEnCours = questionnaireDu !== null && (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-4 backdrop-blur-sm sm:p-8">
      <div className="w-full max-w-2xl rounded-xl border bg-card p-5 shadow-xl">
        <Questionnaire
          nom={questionnaireDu}
          dossierId={dossierQuestionne ?? undefined}
          onTermine={() => setQuestionnaireDu(null)}
          onIndisponible={() => setQuestionnaireDu(null)}
        />
      </div>
    </div>
  );


  return (
    <div className="flex h-screen bg-background text-foreground">
      {questionnaireEnCours}
      {/* Sidebar */}
      <Sidebar
        page={page}
        setPage={setPage}
        setActiveView={setActiveView}
        isAdmin={user.role === "admin"}
        onLogout={logout}
      />

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card/30 px-5">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <MarcLogo size={22} />
              <MarcWordmark className="text-lg" />
            </div>
            <div className="flex items-center gap-2 hide-mobile">
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
                {/* "Sauvegarder" ne distinguait pas un brouillon d'un compte
                    rendu fini : personne ne savait ce qu'il validait, et le
                    texte valide n'arrivait jamais en base. Le libelle dit
                    desormais l'acte, et le compteur dit ce qui reste. */}
                {!savedReportId ? (
                  <div data-ergo="validation" className="flex items-center gap-2">
                    {pointsRestants > 0 && (
                      <span className="hide-mobile text-xs tabular-nums text-muted-foreground">
                        {pointsRestants} à vérifier
                      </span>
                    )}
                    <Button size="sm" onClick={handleSave} disabled={saving}>
                      <Save className="h-3.5 w-3.5" />
                      <span className="hide-mobile">
                        {saving ? "Enregistrement…" : "Valider le compte rendu"}
                      </span>
                    </Button>
                  </div>
                ) : (
                  <Badge variant="success" className="text-xs">
                    Compte rendu validé
                  </Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    // On ne demande que s'il y a quelque chose a perdre.
                    if (!savedReportId && report) setConfirmerNouveau(true);
                    else handleReset();
                  }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span className="hide-mobile">Nouveau CR</span>
                </Button>
              </>
            )}
            {/* Plus de bouton « À compléter » : la liste vit dans l'analyse,
                a cote du texte. Deux listes identiques a deux endroits
                faisaient croire a deux choses differentes. */}
          </div>
        </header>

        {/* Content area */}
        <main className="flex flex-1 overflow-hidden">
          {page === "history" ? (
            <section className="flex-1 overflow-y-auto p-6 scrollbar-thin">
              <HistoryPage token={getToken()} onOpenReport={handleOpenReport} />
            </section>
          ) : (
          <>
          {/* Tant qu'aucun compte rendu n'existe, la dictee occupe la place :
              c'est la seule chose a faire. Des qu'il en existe un, l'analyse
              prend la gauche et le compte rendu la droite — l'ordre de lecture
              du travail qui reste a faire. */}
          {!report ? (
            /* LA DICTEE PREND LA GAUCHE, comme l'analyse ensuite. La place
               qu'occupe la dictee est celle que prendra l'analyse : le regard
               n'a pas a se deplacer quand le compte rendu apparait. Centree,
               elle sautait d'un cote a l'autre a chaque generation.

               A droite, l'emplacement du compte rendu est esquisse plutot que
               laisse vide : on voit ou l'on va. */
            <div className="flex min-w-0 flex-1 overflow-hidden max-lg:hidden">
              <section
                className="min-w-0 shrink-0 overflow-y-auto p-5 scrollbar-thin"
                style={{ width: `${partAnalyse * 100}%` }}
              >
                <RecorderPanel
                  rawTranscription={rawTranscription}
                  report={report}
                  onTranscription={noterTranscription}
                  onFormatted={handleFormatted}
                  onReset={handleReset}
                  onRawChange={noterTranscription}
                  onReformat={handleReformat}
                  reformatting={reformatting}
                />
              </section>

              <div className="w-px shrink-0 bg-border" />

              <section
                aria-hidden
                className="min-w-0 flex-1 overflow-hidden p-5 opacity-40"
              >
                <div className="space-y-3">
                  <div className="h-3 w-2/5 rounded bg-muted" />
                  <div className="space-y-1.5">
                    <div className="h-2.5 w-full rounded bg-muted/70" />
                    <div className="h-2.5 w-11/12 rounded bg-muted/70" />
                    <div className="h-2.5 w-4/5 rounded bg-muted/70" />
                  </div>
                  <div className="h-3 w-1/3 rounded bg-muted" />
                  <div className="space-y-1.5">
                    <div className="h-2.5 w-full rounded bg-muted/70" />
                    <div className="h-2.5 w-10/12 rounded bg-muted/70" />
                    <div className="h-2.5 w-full rounded bg-muted/70" />
                    <div className="h-2.5 w-3/5 rounded bg-muted/70" />
                  </div>
                  <div className="h-3 w-1/4 rounded bg-muted" />
                  <div className="space-y-1.5">
                    <div className="h-2.5 w-11/12 rounded bg-muted/70" />
                    <div className="h-2.5 w-2/3 rounded bg-muted/70" />
                  </div>
                </div>
                <p className="mt-6 text-xs text-muted-foreground">
                  Votre compte rendu s'écrira ici.
                </p>
              </section>
            </div>
          ) : (
            <div className="relative flex min-w-0 flex-1 overflow-hidden max-lg:hidden">
              <PanneauExplicabilite
                data-ergo="analyse"
                className="my-3 ml-3"
                style={{ width: `${partAnalyse * 100}%` }}
                blocs={blocs}
                selection={selection}
                trouSelectionne={trouSelectionne}
                decisions={decisionsParBloc}
                transcription={rawTranscription}
                verifies={pointsVerifies}
                codes={codesAffiches}
                onEclairer={setSelection}
                onAllerAuBloc={setAllerA}
              />

              <Glissiere part={partAnalyse} onChange={setPartAnalyse} />

              <section
                data-ergo="compte_rendu"
                className="min-w-0 flex-1 overflow-y-auto p-5 pb-28 scrollbar-thin"
              >
                {/* LE COMPTE RENDU EST LA SURFACE DE TRAVAIL. Accepter,
                    refuser, combler un trou, choisir dans une liste : tout se
                    fait ici, sur la phrase concernee. Le panneau de gauche
                    explique et ne commande rien. */}
                {/* DEUX MODES SUR LE MEME TEXTE. « Travailler » pour
                    trancher ce que MARC propose, « Écrire » pour retoucher
                    librement. Basculer ne perd rien : c'est le meme texte. */}
                <div className="mb-3 flex items-center gap-1 text-xs">
                  <button
                    type="button"
                    onClick={() => setModeEdition(false)}
                    className={
                      !modeEdition
                        ? "rounded-md bg-primary px-2.5 py-1 font-medium text-primary-foreground"
                        : "rounded-md px-2.5 py-1 text-muted-foreground hover:bg-accent"
                    }
                  >
                    Travailler
                  </button>
                  <button
                    type="button"
                    onClick={() => setModeEdition(true)}
                    className={
                      modeEdition
                        ? "rounded-md bg-primary px-2.5 py-1 font-medium text-primary-foreground"
                        : "rounded-md px-2.5 py-1 text-muted-foreground hover:bg-accent"
                    }
                  >
                    Écrire librement
                  </button>
                </div>

                {modeEdition ? (
                  <ReportPanel
                    report={report}
                    onReportChange={setReport}
                    organeDetecte={organeDetecte}
                    pendingCount={completion.remaining}
                  />
                ) : (
                <CompteRenduTravail
                  blocs={blocs}
                  decisions={decisionsParBloc}
                  eclaire={selection}
                  occupe={etude.occupe || reformatting}
                  onDecider={deciderBloc}
                  onEditer={editerBloc}
                  onRemplirTrou={remplirTrouDuBloc}
                  onEcarterTrou={ecarterTrouDuBloc}
                  onExpliquer={expliquerBloc}
                  onVu={signalerBlocVu}
                  allerA={allerA}
                />
                )}

                {/* LES CODES ADICAP ET SNOMED. Ils vivaient dans ReportPanel,
                    et sont partis avec lui quand la surface de travail l'a
                    remplace. Ce sont des livrables du compte rendu, pas des
                    explications : ils restent sous le texte, la ou ils
                    etaient. */}
                {report && (
                  <div className="mt-4">
                    <CodificationPanel report={report} organe={organeDetecte} />
                  </div>
                )}

                {savedReportId && (
                  <FeedbackPanel
                    savedReportId={savedReportId}
                    feedbackSent={feedbackSent}
                    getToken={getToken}
                    onSent={() => setFeedbackSent(true)}
                  />
                )}
              </section>

              {/* Flottante, au-dessus du compte rendu : ajouter sans redicter
                  l'ensemble etait la chose la moins ergonomique de l'outil. */}
              <BarreAjout
                data-ergo="barre_ajout"
                className="absolute inset-x-0 bottom-4"
                occupe={reformatting}
                onAjouter={ajouterAuCompteRendu}
                historique={historiqueAjouts}
                onDicterDebut={dicteeAppoint.demarrer}
                onDicterFin={dicteeAppoint.arreter}
              />
            </div>
          )}

          {/* Mobile / tablette : une seule vue a la fois */}
          <div className="hidden max-lg:flex max-lg:flex-1 max-lg:flex-col max-lg:overflow-hidden">
            {activeView === "record" ? (
              <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
                <RecorderPanel
                  rawTranscription={rawTranscription}
                  report={report}
                  onTranscription={noterTranscription}
                  onFormatted={handleFormatted}
                  onReset={handleReset}
                  onRawChange={noterTranscription}
                  onReformat={handleReformat}
                  reformatting={reformatting}
                />
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
                {report && explication && (
                  <ExplainPanel
                    trace={explication.trace}
                    warnings={explication.warnings}
                    coherence={explication.coherence}
                  />
                )}
                {/* LE COMPTE RENDU EST LA SURFACE DE TRAVAIL. Accepter,
                    refuser, combler un trou, choisir dans une liste : tout se
                    fait ici, sur la phrase concernee. Le panneau de gauche
                    explique et ne commande rien. */}
                <CompteRenduTravail
                  blocs={blocs}
                  decisions={decisionsParBloc}
                  eclaire={selection}
                  occupe={etude.occupe || reformatting}
                  onDecider={deciderBloc}
                  onEditer={editerBloc}
                  onRemplirTrou={remplirTrouDuBloc}
                  onEcarterTrou={ecarterTrouDuBloc}
                  onExpliquer={expliquerBloc}
                  onVu={signalerBlocVu}
                  allerA={allerA}
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
            MARC est un outil de productivite. Il ne constitue pas un dispositif medical (UE 2017/745). Le praticien reste seul responsable du contenu.
          </p>
        </footer>
      </div>

      {/* TROIS ISSUES, pas deux. « Sauvegarder avant de creer un nouveau
          compte rendu ? » en oui/non obligeait a sauvegarder pour avancer :
          un essai, un cas abandonne ou un doublon partaient quand meme dans
          l'historique. Continuer sans sauvegarder est un choix legitime. */}
      <Confirmation
        ouverte={confirmerNouveau}
        titre="Ce compte rendu n'est pas enregistré"
        message="Vous pouvez l'enregistrer avant de repartir, ou le laisser de côté."
        onAnnuler={() => setConfirmerNouveau(false)}
        actions={[
          {
            libelle: "Enregistrer puis continuer",
            principale: true,
            onChoisir: () => {
              setConfirmerNouveau(false);
              void handleSave().then(() => handleReset());
            },
          },
          {
            libelle: "Continuer sans enregistrer",
            onChoisir: () => {
              setConfirmerNouveau(false);
              handleReset();
            },
          },
        ]}
      />

      {/* Completion drawer */}
      <div
        className={`iris-drawer-overlay ${drawerOpen ? "open" : ""}`}
        onClick={() => setDrawerOpen(false)}
      />
      <div className={`iris-drawer border-l bg-card shadow-2xl ${drawerOpen ? "open" : ""}`}>
        <div className="flex h-full flex-col overflow-y-auto p-4 scrollbar-thin">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">À compléter</h3>
            <button
              onClick={() => setDrawerOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <CompletionPanel
            completion={completion}
            organeDetecte={organeDetecte}
            onDismiss={handleDismissField}
          />
        </div>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav
        activeView={activeView}
        setActiveView={setActiveView}
        hasReport={report !== null}
        completionCount={completion.remaining}
        onOpenDrawer={() => setDrawerOpen(true)}
        page={page}
        setPage={setPage}
      />
    </div>
  );
}
