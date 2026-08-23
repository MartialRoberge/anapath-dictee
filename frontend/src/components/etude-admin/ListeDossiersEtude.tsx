import { FolderOpen, Clock, Pencil, ListChecks } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types — miroir de GET /admin/etude/dossiers                        */
/* ------------------------------------------------------------------ */

export interface LigneDossierEtude {
  id: string;
  praticien_id: string;
  index_session: number;
  organe: string | null;
  cree_a: string;
  abandonne: boolean;
  motif_abandon: string | null;
  nb_propositions: number;
  nb_decidees: number;
  caracteres_modifies: number | null;
  revision_nette_ms: number | null;
}

interface ListeDossiersEtudeProps {
  dossiers: LigneDossierEtude[];
  /** Cas ouvert dans le detail, pour que la liste reste un repere visuel. */
  dossierSelectionne: string | null;
  onSelectionner: (dossierId: string) => void;
}

/* ------------------------------------------------------------------ */
/*  Formatage                                                          */
/* ------------------------------------------------------------------ */

/** Duree ramassee, pour une ligne de liste : la minute suffit a comparer. */
function dureeCompacte(ms: number | null): string {
  if (ms === null) return "-";
  const secondes = Math.round(ms / 1000);
  if (secondes < 60) return `${secondes} s`;
  return `${Math.floor(secondes / 60)} min`;
}

function dateCourte(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function nomOrgane(organe: string | null): string {
  if (!organe) return "Organe non renseigne";
  return organe.replace(/_/g, " ");
}

/* ------------------------------------------------------------------ */
/*  ListeDossiersEtude                                                 */
/* ------------------------------------------------------------------ */

export default function ListeDossiersEtude({
  dossiers,
  dossierSelectionne,
  onSelectionner,
}: ListeDossiersEtudeProps) {
  if (dossiers.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card/50 px-4 py-14 text-center">
        <FolderOpen className="h-8 w-8 text-muted-foreground/40" />
        <div>
          <p className="text-sm font-medium text-muted-foreground">
            Aucun cas enregistre
          </p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            Les dossiers apparaitront ici des la premiere dictee d'un
            praticien inclus.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {dossiers.length} cas
      </p>
      {dossiers.map((dossier) => (
        <button
          key={dossier.id}
          type="button"
          onClick={() => onSelectionner(dossier.id)}
          aria-current={dossierSelectionne === dossier.id}
          className={cn(
            "w-full rounded-xl border bg-card p-3 text-left transition-all",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            dossierSelectionne === dossier.id
              ? "border-primary bg-primary/5"
              : "hover:border-iris-300 hover:shadow-sm",
          )}
        >
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-sm font-semibold first-letter:uppercase">
              {nomOrgane(dossier.organe)}
            </span>
            <Badge variant="outline" className="shrink-0 text-[0.6rem]">
              Cas {dossier.index_session}
            </Badge>
          </div>

          <div className="mt-1 flex items-center gap-2 text-[0.65rem] text-muted-foreground">
            <span className="truncate font-mono">
              {dossier.praticien_id.slice(0, 8)}
            </span>
            <span className="shrink-0">{dateCourte(dossier.cree_a)}</span>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.65rem] text-muted-foreground">
            <span className="flex items-center gap-1">
              <ListChecks className="h-3 w-3 shrink-0" />
              <span className="tabular-nums">
                {dossier.nb_decidees}/{dossier.nb_propositions}
              </span>
              decidees
            </span>
            {dossier.caracteres_modifies !== null && (
              <span className="flex items-center gap-1">
                <Pencil className="h-3 w-3 shrink-0" />
                <span className="tabular-nums">
                  {dossier.caracteres_modifies}
                </span>
                car.
              </span>
            )}
            {dossier.revision_nette_ms !== null && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3 shrink-0" />
                {dureeCompacte(dossier.revision_nette_ms)}
              </span>
            )}
          </div>

          {dossier.abandonne && (
            <Badge
              variant="destructive"
              className="mt-2 text-[0.6rem]"
              title={
                dossier.motif_abandon
                  ? `Motif : ${dossier.motif_abandon.replace(/_/g, " ")}`
                  : undefined
              }
            >
              Abandonne
            </Badge>
          )}
        </button>
      ))}
    </div>
  );
}
