import { useCallback, useMemo, useState } from "react";
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
import type { Marker } from "../services/api";
import {
  findFieldKnowledge,
  ORGAN_GUIDANCE,
  type FieldKnowledge,
} from "../data/field-knowledge";

/* ------------------------------------------------------------------ */
/*  Admin field filter (RGPD et entete)                                */
/* ------------------------------------------------------------------ */

const EXCLUDED_ADMIN_FIELDS: string[] = [
  "hopital", "hôpital", "nom du patient", "nom et prenom", "prenom",
  "patient", "date de naissance", "numero de dossier", "n° dossier",
  "numero", "numéro", "medecin prescripteur", "médecin prescripteur",
  "medecin referent", "médecin référent", "clinicien", "service demandeur",
  "nom du service", "adresse", "telephone", "téléphone",
  "securite sociale", "sécurité sociale", "ipp", "nda", "compte-rendu n",
  "renseignements cliniques", "renseignement clinique",
  "nom et signature", "signature", "nom du pathologiste",
  "pathologiste", "medecin signataire",
  "date du prelevement", "date de prélèvement", "date de reception",
  "date de réception", "date du compte", "date",
  "numero de compte", "reference", "référence",
  "nom",
];

function isAdminField(field: string): boolean {
  const normalized = field.toLowerCase();
  return EXCLUDED_ADMIN_FIELDS.some((excl) => normalized.includes(excl));
}

/* ------------------------------------------------------------------ */
/*  Section labels for display                                         */
/* ------------------------------------------------------------------ */

const SECTION_DISPLAY: Record<string, string> = {
  titre: "Titre",
  renseignements_cliniques: "Renseignements cliniques",
  macroscopie: "Macroscopie",
  microscopie: "Microscopie",
  immunomarquage: "Immunomarquage",
  biologie_moleculaire: "Biologie moleculaire",
  conclusion: "Conclusion",
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface CompletionPanelProps {
  markers: Marker[];
  organeDetecte: string;
  onDismiss: (fieldName: string) => void;
  dismissedFields: Set<string>;
}

/* ------------------------------------------------------------------ */
/*  FieldCard                                                          */
/* ------------------------------------------------------------------ */

interface FieldCardProps {
  marker: Marker;
  knowledge: FieldKnowledge | null;
  onDismiss: () => void;
  isDismissed: boolean;
}

function FieldCard({ marker, knowledge, onDismiss, isDismissed }: FieldCardProps) {
  const [infoOpen, setInfoOpen] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  const severity = knowledge?.severity ?? marker.severity;
  const sectionLabel = SECTION_DISPLAY[marker.section] ?? marker.section;

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
          : "border-warning/20 bg-warning/5",
      )}
    >
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
              {knowledge?.title ?? marker.field}
            </span>
            {knowledge && (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[0.6rem] font-bold text-muted-foreground">
                {knowledge.icon}
              </span>
            )}
          </div>

          <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <MapPin className="h-3 w-3 shrink-0" />
            <span>
              Attendu dans :{" "}
              <span className="font-medium text-foreground">{sectionLabel}</span>
            </span>
          </div>

          <div className="mt-1.5 flex items-center gap-1.5">
            <Badge
              variant={severity === "error" ? "destructive" : "warning"}
              className="px-1.5 py-0 text-[0.6rem]"
            >
              {severity === "error" ? "Obligatoire" : "Recommande"}
            </Badge>
            {marker.auto_filled && (
              <Badge
                variant="secondary"
                className="px-1.5 py-0 text-[0.6rem]"
                title={`Rempli automatiquement via ${marker.rule_id}`}
              >
                Auto-complete
              </Badge>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-start gap-1">
          {knowledge && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-primary"
              onClick={() => setInfoOpen(!infoOpen)}
              title="Pourquoi ce champ est important"
            >
              <Info className="h-4 w-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={handleDismiss}
            title="Ignorer cette suggestion"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

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

      {!infoOpen && marker.message && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          {marker.message}
        </p>
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
/*  CompletionPanel                                                    */
/* ------------------------------------------------------------------ */

export default function CompletionPanel({
  markers,
  organeDetecte,
  onDismiss,
  dismissedFields,
}: CompletionPanelProps) {
  const relevantMarkers = useMemo(
    () => markers.filter((m) => !isAdminField(m.field)),
    [markers],
  );

  const activeMarkers = useMemo(
    () => relevantMarkers.filter((m) => !dismissedFields.has(m.field)),
    [relevantMarkers, dismissedFields],
  );

  const dismissedCount = relevantMarkers.length - activeMarkers.length;

  const errorCount = useMemo(
    () =>
      activeMarkers.filter((m) => {
        const k = findFieldKnowledge(m.field, organeDetecte);
        return (k?.severity ?? m.severity) === "error";
      }).length,
    [activeMarkers, organeDetecte],
  );

  const warningCount = activeMarkers.length - errorCount;

  if (relevantMarkers.length === 0) {
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
        {organeDetecte && <OrganGuidance organe={organeDetecte} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-foreground">Completude</h3>
        <div className="flex items-center gap-2">
          {errorCount > 0 && (
            <Badge variant="destructive" className="gap-1 text-[0.65rem]">
              <AlertCircle className="h-3 w-3" />
              {errorCount} obligatoire{errorCount > 1 ? "s" : ""}
            </Badge>
          )}
          {warningCount > 0 && (
            <Badge variant="warning" className="gap-1 text-[0.65rem]">
              <AlertTriangle className="h-3 w-3" />
              {warningCount} recommande{warningCount > 1 ? "s" : ""}
            </Badge>
          )}
        </div>
      </div>

      {/* Barre de progression */}
      {relevantMarkers.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[0.65rem] text-muted-foreground">
            <span>{dismissedCount + (relevantMarkers.length - activeMarkers.length)} / {relevantMarkers.length} verifie{dismissedCount > 1 ? "s" : ""}</span>
            <span>{Math.round(((relevantMarkers.length - activeMarkers.length) / relevantMarkers.length) * 100)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted">
            <div
              className="h-1.5 rounded-full bg-primary transition-all duration-500"
              style={{ width: `${((relevantMarkers.length - activeMarkers.length) / relevantMarkers.length) * 100}%` }}
            />
          </div>
        </div>
      )}

      <p className="rounded-md bg-accent/50 px-3 py-2 text-[0.7rem] text-muted-foreground">
        Dictez les elements manquants ou cliquez sur un champ pour le remplir.
        Utilisez le bouton info pour comprendre pourquoi chaque champ est important.
      </p>

      {organeDetecte && <OrganGuidance organe={organeDetecte} />}

      <div className="space-y-2">
        {activeMarkers
          .sort((a, b) => {
            const ka = findFieldKnowledge(a.field, organeDetecte);
            const kb = findFieldKnowledge(b.field, organeDetecte);
            const sa = ka?.severity ?? a.severity;
            const sb = kb?.severity ?? b.severity;
            if (sa === "error" && sb !== "error") return -1;
            if (sa !== "error" && sb === "error") return 1;
            return 0;
          })
          .map((marker) => (
            <FieldCard
              key={`${marker.section}:${marker.field}`}
              marker={marker}
              knowledge={findFieldKnowledge(marker.field, organeDetecte)}
              onDismiss={() => onDismiss(marker.field)}
              isDismissed={dismissedFields.has(marker.field)}
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
