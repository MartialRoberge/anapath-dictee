/**
 * Barre d'etat du parcours : ou en est le compte rendu, et surtout s'il est
 * enregistre.
 *
 * ------------------------------------------------------------------
 *  POURQUOI CE COMPOSANT EXISTE
 * ------------------------------------------------------------------
 *
 *  La sauvegarde automatique en memoire du navigateur donnait au praticien le
 *  sentiment que son texte etait enregistre. Il ne l'etait pas : le texte
 *  valide n'arrivait jamais en base, la charge d'edition ne se calculait pas,
 *  et l'administration restait vide. Cette barre dit donc l'INVERSE de ce que
 *  suggerait l'autosave : tant que la validation n'a pas eu lieu, on ecrit
 *  noir sur blanc que rien n'est enregistre. On l'affirme, on ne le suggere
 *  pas.
 *
 *  Trois etats, un seul terminal :
 *   - brouillon : le texte ne vit que dans ce navigateur. Etat le plus
 *                 dangereux, donc celui qui porte l'avertissement le plus net.
 *   - en_cours  : le praticien juge les propositions. Le compteur des
 *                 restantes doit DIMINUER a vue d'oeil, sinon la tache parait
 *                 interminable.
 *   - valide    : acte explicite, horodate.
 *
 *  Le parent est libre de repasser en `en_cours` si le texte est modifie apres
 *  validation : un compte rendu retouche n'est plus le compte rendu valide, et
 *  le dire vaut mieux que d'afficher un sceau perime.
 *
 *  La barre de progression s'anime, jamais la mesure : `restantes` arrive deja
 *  a jour du parent, l'animation ne fait que rattraper l'affichage.
 */

import { AlertCircle, CheckCircle2, FileWarning, ListChecks } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export type EtatParcours = "brouillon" | "en_cours" | "valide";

export interface BarreEtatProps {
  etat: EtatParcours;
  restantes: number;
  total: number;
  /** Horodatage ISO 8601 de la validation, nul tant qu'elle n'a pas eu lieu. */
  valideA: string | null;
  enregistrementEnCours: boolean;
  erreurEnregistrement: string | null;
}

/** ISO 8601 -> heure locale courte, avec la date complete pour l'infobulle. */
function formaterValidation(
  iso: string | null,
): { heure: string; complet: string } | null {
  if (!iso) return null;
  const date = new Date(iso);
  // Un horodatage illisible ne doit pas afficher "Invalid Date" a la place
  // d'une preuve d'enregistrement : on retombe sur le libelle seul.
  if (Number.isNaN(date.getTime())) return null;
  return {
    heure: date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }),
    complet: date.toLocaleString("fr-FR", { dateStyle: "full", timeStyle: "short" }),
  };
}

const LIBELLE: Record<EtatParcours, string> = {
  brouillon: "Brouillon local",
  en_cours: "Revue en cours",
  valide: "Compte rendu valide",
};

const HABILLAGE: Record<EtatParcours, string> = {
  brouillon: "border-warning/30 bg-warning/5",
  en_cours: "border-primary/20 bg-primary/5",
  valide: "border-success/30 bg-success/5",
};

export default function BarreEtat({
  etat,
  restantes,
  total,
  valideA,
  enregistrementEnCours,
  erreurEnregistrement,
}: BarreEtatProps) {
  const valide = etat === "valide";
  // Bornes defensives : un compteur negatif ou une barre a 130 % feraient
  // douter de tout le reste de l'ecran.
  const restantesSures = Math.max(0, restantes);
  const juges = Math.max(0, total - restantesSures);
  const progression = total > 0 ? Math.min(100, (juges / total) * 100) : 0;
  const validation = valide ? formaterValidation(valideA) : null;

  // La phrase qui leve l'ambiguite. Elle est differente pour chaque etat parce
  // que le risque n'est pas le meme : en brouillon rien n'existe hors du
  // navigateur ; en revue les decisions partent au fil de l'eau mais pas le
  // texte ; une fois valide, c'est la retouche qui devient le piege.
  const explication =
    etat === "brouillon"
      ? "Ce texte n'existe que dans la memoire de ce navigateur. C'est la validation qui l'enregistre."
      : etat === "en_cours"
        ? restantesSures === 0
          ? "Toutes les propositions sont jugees. Le texte, lui, ne sera enregistre qu'a la validation."
          : "Vos decisions sont enregistrees au fil de l'eau. Le texte, lui, ne le sera qu'a la validation."
        : "Le texte et vos decisions sont enregistres. Toute modification demandera une nouvelle validation.";

  return (
    <div className="flex flex-col gap-2">
      <div
        role="status"
        aria-live="polite"
        className={cn(
          "flex flex-col gap-2.5 rounded-lg border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4",
          HABILLAGE[etat],
        )}
      >
        <div className="flex min-w-0 items-start gap-2">
          <span className="mt-0.5 shrink-0">
            {etat === "brouillon" && <FileWarning className="h-4 w-4 text-warning" />}
            {etat === "en_cours" && <ListChecks className="h-4 w-4 text-primary" />}
            {valide && <CheckCircle2 className="h-4 w-4 text-success" />}
          </span>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span
                className={cn(
                  "text-sm font-semibold",
                  valide ? "text-success" : "text-foreground",
                )}
              >
                {LIBELLE[etat]}
              </span>
              {/* Le point dur du parcours tient dans cette pastille : tant
                  qu'elle est la, le compte rendu n'est pas en base. */}
              {!valide && (
                <Badge variant="warning" className="px-2 py-0 text-[0.65rem]">
                  Non enregistre
                </Badge>
              )}
              {validation && (
                <span
                  className="text-xs font-medium tabular-nums text-success"
                  title={validation.complet}
                >
                  a {validation.heure}
                </span>
              )}
            </div>

            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
              {explication}
            </p>

            {enregistrementEnCours && (
              <span className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-primary">
                <span className="h-3 w-3 shrink-0 animate-spin-slow rounded-full border-2 border-primary/30 border-t-primary" />
                Enregistrement en cours...
              </span>
            )}
          </div>
        </div>

        {/* Le compteur n'a de sens que s'il y a des propositions a juger. */}
        {!valide && total > 0 && (
          <div className="w-full shrink-0 sm:w-52">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              {restantesSures > 0 ? (
                <span className="text-muted-foreground">
                  <span className="text-sm font-bold tabular-nums text-foreground">
                    {restantesSures}
                  </span>{" "}
                  proposition{restantesSures > 1 ? "s" : ""} a juger
                </span>
              ) : (
                <span className="text-sm font-semibold text-success">
                  Tout est juge
                </span>
              )}
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {juges}/{total}
              </span>
            </div>
            <div
              role="progressbar"
              aria-label="Propositions jugees"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={juges}
              className="mt-1 h-1.5 w-full rounded-full bg-muted"
            >
              <div
                className="h-1.5 rounded-full bg-primary transition-all duration-500 motion-reduce:transition-none"
                style={{ width: `${progression}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Un echec d'enregistrement est l'exact scenario que ce parcours doit
          rendre impossible a manquer : on nomme la consequence, pas seulement
          l'erreur technique. */}
      {erreurEnregistrement && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="leading-relaxed">
            <span className="font-semibold">
              Le compte rendu n'a pas ete enregistre.
            </span>{" "}
            {erreurEnregistrement}
          </span>
        </div>
      )}
    </div>
  );
}
