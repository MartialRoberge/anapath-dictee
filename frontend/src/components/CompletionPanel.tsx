import { useState, useMemo, useCallback, useEffect } from "react";
import {
  Info,
  Trash2,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  BookOpen,
  Lightbulb,
  MapPin,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { DonneeManquante, AdicapResult, SnomedResult } from "../services/api";
import { getAdicap, getSnomed } from "../services/api";
import {
  findFieldKnowledge,
  ORGAN_GUIDANCE,
  type FieldKnowledge,
} from "../data/field-knowledge";

/* ------------------------------------------------------------------ */
/*  Admin field filter                                                 */
/* ------------------------------------------------------------------ */

const EXCLUDED_ADMIN_FIELDS: string[] = [
  // Identite patient (RGPD)
  "hopital", "hôpital", "nom du patient", "nom et prenom", "prenom",
  "patient", "date de naissance", "numero de dossier", "n° dossier",
  "numero", "numéro", "medecin prescripteur", "médecin prescripteur",
  "medecin referent", "médecin référent", "clinicien", "service demandeur",
  "nom du service", "adresse", "telephone", "téléphone",
  "securite sociale", "sécurité sociale", "ipp", "nda", "compte-rendu n",
  // Renseignements cliniques (contient des infos patient RGPD)
  "renseignements cliniques", "renseignement clinique",
  // Info pathologiste (fait sur Word)
  "nom et signature", "signature", "nom du pathologiste",
  "pathologiste", "medecin signataire",
  // Admin fait sur Word
  "date du prelevement", "date de prélèvement", "date de reception",
  "date de réception", "date du compte", "date",
  "numero de compte", "reference", "référence",
  // Generique
  "nom",
];

function isAdminField(champ: string): boolean {
  const normalized = champ.toLowerCase();
  return EXCLUDED_ADMIN_FIELDS.some((excl) => normalized.includes(excl));
}

/* ------------------------------------------------------------------ */
/*  Section labels for display                                         */
/* ------------------------------------------------------------------ */

const SECTION_DISPLAY: Record<string, string> = {
  macroscopie: "Macroscopie",
  microscopie: "Etude histologique",
  ihc: "Immunomarquage",
  conclusion: "Conclusion",
  biologie_moleculaire: "Biologie moleculaire",
  renseignements_cliniques: "Renseignements cliniques",
  titre: "Titre",
  non_determine: "Section non determinee",
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface CompletionPanelProps {
  donneesManquantes: DonneeManquante[];
  organeDetecte: string;
  report: string;
  onDismiss: (champ: string) => void;
  dismissedFields: Set<string>;
}

/* ------------------------------------------------------------------ */
/*  FieldCard                                                          */
/* ------------------------------------------------------------------ */

interface FieldCardProps {
  donnee: DonneeManquante;
  knowledge: FieldKnowledge | null;
  onDismiss: () => void;
  isDismissed: boolean;
}

function FieldCard({ donnee, knowledge, onDismiss, isDismissed }: FieldCardProps) {
  const [infoOpen, setInfoOpen] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  const severity = knowledge?.severity ?? (donnee.obligatoire ? "error" : "warning");
  const sectionLabel = SECTION_DISPLAY[donnee.section] ?? donnee.section;

  const handleDismiss = useCallback(() => {
    setDismissing(true);
    setTimeout(() => onDismiss(), 300);
  }, [onDismiss]);

  if (isDismissed) return null;

  return (
    <div
      className={cn(
        "group rounded-lg border p-3 transition-all duration-300",
        dismissing && "translate-x-4 scale-95 opacity-0",
        severity === "error"
          ? "border-destructive/20 bg-destructive/5"
          : "border-warning/20 bg-warning/5"
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-2">
        <div className="mt-0.5 shrink-0">
          {severity === "error" ? (
            <AlertCircle className="h-4 w-4 text-destructive" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-warning" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {knowledge?.title ?? donnee.champ}
            </span>
            {knowledge && (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[0.6rem] font-bold text-muted-foreground">
                {knowledge.icon}
              </span>
            )}
          </div>

          {/* WHERE it belongs - prominent location */}
          <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <MapPin className="h-3 w-3 shrink-0" />
            <span>
              Attendu dans : <span className="font-medium text-foreground">{sectionLabel}</span>
            </span>
          </div>

          <div className="mt-1.5 flex items-center gap-1.5">
            <Badge
              variant={severity === "error" ? "destructive" : "warning"}
              className="px-1.5 py-0 text-[0.6rem]"
            >
              {severity === "error" ? "Obligatoire" : "Recommande"}
            </Badge>
          </div>
        </div>

        {/* Actions */}
        <div className="flex shrink-0 gap-1">
          {knowledge && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-primary"
              onClick={() => setInfoOpen(!infoOpen)}
              title="Pourquoi ce champ est important"
            >
              <Info className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={handleDismiss}
            title="Ignorer cette suggestion"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Info panel (expandable) */}
      {infoOpen && knowledge && (
        <div className="mt-3 space-y-2.5 rounded-md border border-border/50 bg-card p-3">
          <div className="flex items-start gap-2">
            <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
            <div>
              <p className="text-xs font-medium text-foreground">
                Pourquoi c'est important
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {knowledge.why}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
            <div>
              <p className="text-xs font-medium text-foreground">
                Reference normative
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {knowledge.norm}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
            <div>
              <p className="text-xs font-medium text-foreground">
                Risque si absent
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {knowledge.risk}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  OrganGuidance                                                      */
/* ------------------------------------------------------------------ */

function OrganGuidance({ organe }: { organe: string }) {
  const [open, setOpen] = useState(true);
  const guidance = ORGAN_GUIDANCE[organe] ?? ORGAN_GUIDANCE["non_determine"];

  if (!guidance) return null;

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
      <button
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold text-primary">
            Guide : {guidance.title}
          </span>
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-primary" />
        ) : (
          <ChevronDown className="h-4 w-4 text-primary" />
        )}
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5 pl-6">
          {guidance.tips.map((tip, idx) => (
            <li
              key={idx}
              className="flex items-start gap-2 text-xs text-muted-foreground"
            >
              <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-primary/50" />
              {tip}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CodingTabs (ADICAP / SNOMED)                                       */
/* ------------------------------------------------------------------ */

function CodingTabs({
  adicap,
  snomed,
  codeTab,
  onTabChange,
}: {
  adicap: AdicapResult | null;
  snomed: SnomedResult | null;
  codeTab: "adicap" | "snomed";
  onTabChange: (tab: "adicap" | "snomed") => void;
}) {
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b">
        <button
          className={cn(
            "flex-1 px-3 py-2 text-xs font-semibold transition-colors",
            codeTab === "adicap"
              ? "bg-primary/10 text-primary border-b-2 border-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => onTabChange("adicap")}
        >
          ADICAP
        </button>
        <button
          className={cn(
            "flex-1 px-3 py-2 text-xs font-semibold transition-colors",
            codeTab === "snomed"
              ? "bg-primary/10 text-primary border-b-2 border-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
          onClick={() => onTabChange("snomed")}
        >
          SNOMED CT
        </button>
      </div>

      {/* Tab content */}
      <div className="p-3">
        {codeTab === "adicap" && (
          <div>
            {adicap && adicap.organe_code !== "XX" ? (
              <>
                <div className="flex items-center justify-center rounded-md bg-muted px-3 py-2">
                  <span className="font-mono text-base font-bold tracking-widest text-primary">
                    {adicap.code}
                  </span>
                </div>
                <div className="mt-2 space-y-0.5 text-[0.65rem] text-muted-foreground">
                  <p><span className="font-medium text-foreground">{adicap.prelevement_code}</span> {adicap.prelevement}</p>
                  <p><span className="font-medium text-foreground">{adicap.technique_code}</span> {adicap.technique}</p>
                  <p><span className="font-medium text-foreground">{adicap.organe_code}</span> {adicap.organe}</p>
                  <p><span className="font-medium text-foreground">{adicap.lesion_code}</span> {adicap.lesion}</p>
                </div>
              </>
            ) : (
              <p className="text-center text-xs text-muted-foreground">
                Code non determine automatiquement.
              </p>
            )}
            <input
              type="text"
              placeholder="Saisir / corriger le code ADICAP"
              defaultValue={adicap?.code ?? ""}
              className="mt-2 w-full rounded-md border border-input bg-background px-2.5 py-1.5 font-mono text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <p className="mt-1 text-[0.6rem] italic text-muted-foreground/60">
              A valider par le praticien. Source : thesaurus ADICAP/SFP.
            </p>
          </div>
        )}

        {codeTab === "snomed" && (
          <div className="space-y-3">
            <div>
              <p className="text-[0.65rem] font-medium text-muted-foreground">Topographie</p>
              <div className="mt-1 flex items-center gap-2 rounded-md bg-muted px-3 py-1.5">
                <span className="font-mono text-sm font-bold text-primary">{snomed?.topography.code || "—"}</span>
                <span className="text-xs text-muted-foreground">{snomed?.topography.display ?? "Non determine"}</span>
              </div>
            </div>
            <div>
              <p className="text-[0.65rem] font-medium text-muted-foreground">Morphologie</p>
              <div className="mt-1 flex items-center gap-2 rounded-md bg-muted px-3 py-1.5">
                <span className="font-mono text-sm font-bold text-primary">{snomed?.morphology.code || "—"}</span>
                <span className="text-xs text-muted-foreground">{snomed?.morphology.display ?? "Non determine"}</span>
              </div>
            </div>
            <input
              type="text"
              placeholder="Saisir / corriger le code SNOMED"
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 font-mono text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <p className="text-[0.6rem] italic text-muted-foreground/60">
              A valider par le praticien. Source : SNOMED International.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CompletionPanel                                                    */
/* ------------------------------------------------------------------ */

export default function CompletionPanel({
  donneesManquantes,
  organeDetecte,
  report,
  onDismiss,
  dismissedFields,
}: CompletionPanelProps) {
  const [adicap, setAdicap] = useState<AdicapResult | null>(null);
  const [snomed, setSnomed] = useState<SnomedResult | null>(null);
  const [codeTab, setCodeTab] = useState<"adicap" | "snomed">("adicap");

  useEffect(() => {
    if (!report) return;
    getAdicap(report, organeDetecte).then(setAdicap).catch(() => setAdicap(null));
    getSnomed(report, organeDetecte).then(setSnomed).catch(() => setSnomed(null));
  }, [report, organeDetecte]);

  const relevantFields = useMemo(
    () => donneesManquantes.filter((d) => !isAdminField(d.champ)),
    [donneesManquantes]
  );

  const activeFields = useMemo(
    () => relevantFields.filter((d) => !dismissedFields.has(d.champ)),
    [relevantFields, dismissedFields]
  );

  const dismissedCount = relevantFields.length - activeFields.length;

  const errorCount = useMemo(
    () =>
      activeFields.filter((d) => {
        const k = findFieldKnowledge(d.champ, organeDetecte);
        return (k?.severity ?? (d.obligatoire ? "error" : "warning")) === "error";
      }).length,
    [activeFields, organeDetecte]
  );

  const warningCount = activeFields.length - errorCount;

  if (relevantFields.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-col items-center gap-3 rounded-lg border border-success/30 bg-success/5 p-6 text-center">
          <CheckCircle2 className="h-8 w-8 text-success" />
          <div>
            <p className="text-sm font-semibold text-success">
              Compte-rendu complet
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Toutes les donnees obligatoires sont presentes.
            </p>
          </div>
        </div>

        {/* Coding tabs: ADICAP / SNOMED */}
        {(adicap || snomed) && (
          <CodingTabs
            adicap={adicap}
            snomed={snomed}
            codeTab={codeTab}
            onTabChange={setCodeTab}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-foreground">Completude</h3>
        <div className="flex items-center gap-2">
          {errorCount > 0 && (
            <Badge variant="destructive" className="gap-1 text-[0.65rem]">
              <AlertCircle className="h-3 w-3" />
              {errorCount}
            </Badge>
          )}
          {warningCount > 0 && (
            <Badge variant="warning" className="gap-1 text-[0.65rem]">
              <AlertTriangle className="h-3 w-3" />
              {warningCount}
            </Badge>
          )}
        </div>
      </div>

      {/* Count */}
      {activeFields.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {activeFields.length} element{activeFields.length > 1 ? "s" : ""} a verifier
        </p>
      )}

      {/* Coding tabs: ADICAP / SNOMED */}
      {(adicap || snomed) && (
        <CodingTabs
          adicap={adicap}
          snomed={snomed}
          codeTab={codeTab}
          onTabChange={setCodeTab}
        />
      )}

      {/* Iterative hint */}
      <p className="rounded-md bg-accent/50 px-3 py-2 text-[0.7rem] text-muted-foreground">
        Dictez les elements manquants pour completer le CR. Le rapport sera mis a jour automatiquement.
      </p>

      {/* Organ guidance */}
      {organeDetecte && <OrganGuidance organe={organeDetecte} />}

      {/* Field cards - sorted by severity, errors first */}
      <div className="space-y-2">
        {activeFields
          .sort((a, b) => {
            const ka = findFieldKnowledge(a.champ, organeDetecte);
            const kb = findFieldKnowledge(b.champ, organeDetecte);
            const sa = ka?.severity ?? (a.obligatoire ? "error" : "warning");
            const sb = kb?.severity ?? (b.obligatoire ? "error" : "warning");
            if (sa === "error" && sb !== "error") return -1;
            if (sa !== "error" && sb === "error") return 1;
            return 0;
          })
          .map((donnee) => (
            <FieldCard
              key={donnee.champ}
              donnee={donnee}
              knowledge={findFieldKnowledge(donnee.champ, organeDetecte)}
              onDismiss={() => onDismiss(donnee.champ)}
              isDismissed={dismissedFields.has(donnee.champ)}
            />
          ))}
      </div>

      {dismissedCount > 0 && (
        <p className="text-center text-[0.65rem] text-muted-foreground">
          {dismissedCount} suggestion{dismissedCount > 1 ? "s" : ""} ignoree
          {dismissedCount > 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
