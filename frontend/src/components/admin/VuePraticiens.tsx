import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FolderOpen,
  GitCompare,
  ListChecks,
  MessageSquare,
  Pencil,
  Star,
  UserRound,
  Users,
  Trash2,} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { LigneDossierEtude } from "@/components/etude-admin/ListeDossiersEtude";
import type { AdminCorrection, AdminReport } from "@/services/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

/**
 * Une ligne de la table des praticiens, agregee cote client a partir des
 * dossiers. Rien n'est invente : chaque champ se recalcule a partir de la liste
 * recue, et vaut `null` quand la mesure n'existe pas.
 */
export interface LignePraticien {
  praticienId: string;
  /** Le nom, pour que l'administrateur reconnaisse ses praticiens. */
  praticienNom: string;
  nbCas: number;
  /** Cas dont le compte rendu a ete VALIDE (charge d'edition calculee). */
  nbValides: number;
  nbAbandons: number;
  /** Mediane, et non moyenne : un seul cas tres remanie deplacerait la moyenne. */
  chargeEditionMediane: number | null;
  revisionMedianeMs: number | null;
  derniereActivite: string | null;
  nbDecidees: number;
  nbPropositions: number;
}

interface VuePraticiensProps {
  /** Les dossiers de l'etude, deja tries du plus recent au plus ancien. */
  dossiers: LigneDossierEtude[];
  /** Comptes rendus enregistres cote exploitation (avec le nom du compte). */
  rapports: AdminReport[];
  /** Modifications journalisees sur ces comptes rendus. */
  corrections: AdminCorrection[];
  /**
   * Renseigne quand la source d'exploitation n'a pas pu etre lue. Une liste
   * vide dirait « aucun compte rendu » : ce n'est pas la meme chose qu'une
   * lecture impossible, et la confusion est exactement ce qu'on corrige ici.
   */
  erreurExploitation: string | null;
  praticienSelectionne: string | null;
  dossierSelectionne: string | null;
  onSelectionnerPraticien: (praticienId: string | null) => void;
  onSelectionnerDossier: (dossierId: string | null) => void;
  /**
   * Detruit un cas d'essai. Reserve aux dossiers d'AVANT l'etude : une fois
   * celle-ci commencee, effacer un cas rendrait l'etude incapable de rendre
   * compte de son effectif, et c'est l'EXCLUSION qu'il faut.
   */
  onSupprimerDossier: (dossierId: string) => Promise<void>;
  /**
   * Colonne de contexte a cote d'un dossier ouvert : le resume du praticien
   * s'efface pour laisser toute la hauteur a la liste de ses cas.
   */
  compact?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Formatage                                                          */
/* ------------------------------------------------------------------ */

const NOMBRE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

function mediane(valeurs: number[]): number | null {
  if (valeurs.length === 0) return null;
  const tri = [...valeurs].sort((a, b) => a - b);
  const milieu = Math.floor(tri.length / 2);
  return tri.length % 2 === 0
    ? (tri[milieu - 1] + tri[milieu]) / 2
    : tri[milieu];
}

/** Duree ramassee : a l'echelle d'une comparaison entre praticiens, la minute suffit. */
function dureeCompacte(ms: number | null): string {
  if (ms === null) return "-";
  const secondes = Math.round(ms / 1000);
  if (secondes < 60) return `${secondes} s`;
  return `${Math.floor(secondes / 60)} min`;
}

function dateCourte(iso: string | null): string {
  if (!iso) return "";
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

/**
 * L'etude ne stocke aucun nom : le praticien y est un identifiant de compte.
 * On affiche les huit premiers caracteres, comme partout ailleurs dans
 * l'administration, et l'identifiant complet reste en infobulle.
 */
/**
 * Le nom du praticien, tel qu'il s'affiche a l'administrateur.
 *
 * Un identifiant tronque ne dit RIEN a qui gere l'etude : il connait ses
 * praticiens et doit les reconnaitre d'un coup d'oeil. La pseudonymisation a
 * sa place dans l'EXPORT, la ou les donnees sortent du systeme — ici elle ne
 * protege personne et rend l'ecran inutilisable.
 */
function nomPraticien(cas: { praticien_nom?: string; praticien_id: string }[]): string {
  return cas[0]?.praticien_nom || cas[0]?.praticien_id.slice(0, 8) || "?";
}

const MOTIF_ABANDON_LABELS: Record<string, string> = {
  outil_trop_lent: "Outil trop lent",
  propositions_inexploitables: "Propositions inexploitables",
  interruption: "Interruption",
  cas_trop_complexe: "Cas trop complexe",
  autre: "Autre",
};

/* ------------------------------------------------------------------ */
/*  Agregation                                                         */
/* ------------------------------------------------------------------ */

/**
 * Un cas est VALIDE lorsque la charge d'edition existe : le backend ne la
 * calcule qu'a la cloture, contre le texte reellement valide. Un cas sans
 * charge d'edition n'est donc pas un cas « a zero correction », c'est un cas
 * dont le praticien n'a jamais dit qu'il etait termine.
 */
function estValide(dossier: LigneDossierEtude): boolean {
  return dossier.caracteres_modifies !== null;
}

function agregerPraticiens(dossiers: LigneDossierEtude[]): LignePraticien[] {
  const parPraticien = new Map<string, LigneDossierEtude[]>();
  for (const dossier of dossiers) {
    const liste = parPraticien.get(dossier.praticien_id);
    if (liste) liste.push(dossier);
    else parPraticien.set(dossier.praticien_id, [dossier]);
  }

  const lignes: LignePraticien[] = [];
  for (const [praticienId, cas] of parPraticien) {
    const valides = cas.filter(estValide);
    const dates = cas
      .map((dossier) => dossier.cree_a)
      .filter((iso) => !Number.isNaN(new Date(iso).getTime()))
      .sort();
    lignes.push({
      praticienId,
      praticienNom: nomPraticien(cas),
      nbCas: cas.length,
      nbValides: valides.length,
      nbAbandons: cas.filter((dossier) => dossier.abandonne).length,
      // Les cas non valides sont ECARTES, jamais ramenes a zero : un cas sans
      // texte valide n'est pas un cas corrige a zero caractere, et le compter
      // ainsi tirerait la mediane vers le bas a chaque cas laisse en suspens.
      chargeEditionMediane: mediane(
        valides
          .map((dossier) => dossier.caracteres_modifies)
          .filter((mesure): mesure is number => mesure !== null),
      ),
      revisionMedianeMs: mediane(
        cas
          .map((dossier) => dossier.revision_nette_ms)
          .filter((ms): ms is number => ms !== null),
      ),
      derniereActivite: dates.length > 0 ? dates[dates.length - 1] : null,
      nbDecidees: cas.reduce((total, dossier) => total + dossier.nb_decidees, 0),
      nbPropositions: cas.reduce(
        (total, dossier) => total + dossier.nb_propositions,
        0,
      ),
    });
  }

  // Le plus actif recemment en premier : c'est ce qu'on vient regarder.
  return lignes.sort((a, b) =>
    (b.derniereActivite ?? "").localeCompare(a.derniereActivite ?? ""),
  );
}

/* ------------------------------------------------------------------ */
/*  Cellules honnetes                                                  */
/* ------------------------------------------------------------------ */

/** Rien observe : on le dit. Ecrire 0 ici serait mentir avec un tableau. */
function NonMesure({ raison }: { raison: string }) {
  return (
    <div className="space-y-1">
      <span className="inline-block rounded-md border border-dashed border-border px-2 py-0.5 text-xs font-medium text-muted-foreground">
        Non mesure
      </span>
      <p className="text-xs text-muted-foreground">{raison}</p>
    </div>
  );
}

/** Un taux ne s'affiche jamais sans son denominateur. */
function CelluleValides({ valides, total }: { valides: number; total: number }) {
  const tousValides = total > 0 && valides === total;
  return (
    <div className="space-y-1">
      <p
        className={cn(
          "text-sm font-semibold tabular-nums",
          valides === 0 && total > 0 && "text-warning",
        )}
      >
        {valides} / {total}
      </p>
      <p className="text-xs text-muted-foreground">
        {tousValides
          ? "Tous termines"
          : `${total - valides} sans texte valide`}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  TableauPraticiens                                                  */
/* ------------------------------------------------------------------ */

function TableauPraticiens({
  lignes,
  onSelectionner,
}: {
  lignes: LignePraticien[];
  onSelectionner: (praticienId: string) => void;
}) {
  return (
    // Le tableau defile dans son conteneur, jamais la page.
    <div className="overflow-x-auto rounded-lg border bg-card">
      <table className="w-full min-w-[52rem] border-collapse text-sm">
        <thead>
          <tr className="border-b bg-muted/50">
            {[
              "Praticien",
              "Cas",
              "Cas valides",
              "Charge d'edition",
              "Revision (mediane)",
              "Decisions",
              "Derniere activite",
            ].map((entete) => (
              <th
                key={entete}
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {entete}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((ligne) => (
            <tr
              key={ligne.praticienId}
              className="border-b align-top transition-colors last:border-0 hover:bg-accent/40"
            >
              <td className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => onSelectionner(ligne.praticienId)}
                  title={ligne.praticienId}
                  className={cn(
                    "flex items-center gap-2 rounded-md text-left font-semibold text-primary",
                    "hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  )}
                >
                  <UserRound className="h-4 w-4 shrink-0" />
                  <span className="font-mono text-sm">
                    {ligne.praticienNom}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                </button>
                {ligne.nbAbandons > 0 && (
                  <Badge
                    variant="outline"
                    className="mt-1.5 gap-1 text-[0.6rem]"
                    title="Un abandon est une donnee du protocole, pas un incident."
                  >
                    <Ban className="h-3 w-3" />
                    {ligne.nbAbandons} abandon
                    {ligne.nbAbandons > 1 ? "s" : ""}
                  </Badge>
                )}
              </td>
              <td className="px-4 py-3 text-sm font-semibold tabular-nums">
                {ligne.nbCas}
              </td>
              <td className="px-4 py-3">
                <CelluleValides valides={ligne.nbValides} total={ligne.nbCas} />
              </td>
              <td className="px-4 py-3">
                {ligne.chargeEditionMediane === null ? (
                  <NonMesure raison="Aucun compte rendu valide" />
                ) : (
                  <div className="space-y-1">
                    <p className="text-sm font-semibold tabular-nums">
                      {NOMBRE.format(ligne.chargeEditionMediane)} car.
                    </p>
                    <p className="text-xs tabular-nums text-muted-foreground">
                      mediane sur {ligne.nbValides} cas valide
                      {ligne.nbValides > 1 ? "s" : ""}
                    </p>
                  </div>
                )}
              </td>
              <td className="px-4 py-3">
                {ligne.revisionMedianeMs === null ? (
                  <NonMesure raison="Aucune revision chronometree" />
                ) : (
                  <p className="text-sm font-semibold tabular-nums">
                    {dureeCompacte(ligne.revisionMedianeMs)}
                  </p>
                )}
              </td>
              <td className="px-4 py-3">
                <p className="text-sm tabular-nums">
                  {ligne.nbDecidees} / {ligne.nbPropositions}
                </p>
                <p className="text-xs text-muted-foreground">propositions</p>
              </td>
              <td className="px-4 py-3 text-xs tabular-nums text-muted-foreground">
                {dateCourte(ligne.derniereActivite) || "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Comptes utilisateurs — le versant nominatif                        */
/* ------------------------------------------------------------------ */

interface CompteUtilisateur {
  email: string;
  nom: string;
  rapports: AdminReport[];
  noteMoyenne: number | null;
  nbFeedbacks: number;
  nbCorrections: number;
  dernierCr: string | null;
}

function agregerComptes(
  rapports: AdminReport[],
  corrections: AdminCorrection[],
): { comptes: CompteUtilisateur[]; parRapport: Map<string, AdminCorrection[]> } {
  // Les corrections portent l'identifiant de leur compte rendu : la jointure
  // est exacte, on ne rapproche jamais deux enregistrements par leur libelle.
  const parRapport = new Map<string, AdminCorrection[]>();
  for (const correction of corrections) {
    const liste = parRapport.get(correction.report_id);
    if (liste) liste.push(correction);
    else parRapport.set(correction.report_id, [correction]);
  }

  const parEmail = new Map<string, AdminReport[]>();
  for (const rapport of rapports) {
    const liste = parEmail.get(rapport.user_email);
    if (liste) liste.push(rapport);
    else parEmail.set(rapport.user_email, [rapport]);
  }

  const comptes: CompteUtilisateur[] = [];
  for (const [email, liste] of parEmail) {
    const tries = [...liste].sort((a, b) =>
      b.created_at.localeCompare(a.created_at),
    );
    const notes = tries
      .map((rapport) => rapport.rating)
      .filter((note): note is number => note !== null);
    comptes.push({
      email,
      nom: tries[0].user_name,
      rapports: tries,
      noteMoyenne:
        notes.length === 0
          ? null
          : notes.reduce((somme, note) => somme + note, 0) / notes.length,
      nbFeedbacks: notes.length,
      nbCorrections: tries.reduce(
        (total, rapport) => total + rapport.correction_count,
        0,
      ),
      dernierCr: tries[0].created_at || null,
    });
  }

  return {
    comptes: comptes.sort((a, b) =>
      (b.dernierCr ?? "").localeCompare(a.dernierCr ?? ""),
    ),
    parRapport,
  };
}

function CarteCompte({
  compte,
  correctionsParRapport,
}: {
  compte: CompteUtilisateur;
  correctionsParRapport: Map<string, AdminCorrection[]>;
}) {
  const [ouvert, setOuvert] = useState(false);

  return (
    <div className="rounded-lg border bg-card">
      <button
        type="button"
        onClick={() => setOuvert((etat) => !etat)}
        aria-expanded={ouvert}
        className={cn(
          "flex w-full items-start gap-3 p-4 text-left transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          ouvert ? "bg-accent/30" : "hover:bg-accent/20",
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{compte.nom}</span>
            <span className="truncate text-xs text-muted-foreground">
              {compte.email}
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <FolderOpen className="h-3 w-3 shrink-0" />
              <span className="tabular-nums">{compte.rapports.length}</span>
              compte{compte.rapports.length > 1 ? "s" : ""} rendu
              {compte.rapports.length > 1 ? "s" : ""}
            </span>
            <span className="flex items-center gap-1">
              <Star className="h-3 w-3 shrink-0" />
              {compte.noteMoyenne === null ? (
                "Aucune note"
              ) : (
                <span className="tabular-nums">
                  {compte.noteMoyenne.toFixed(1).replace(".", ",")}/5 sur{" "}
                  {compte.nbFeedbacks} avis
                </span>
              )}
            </span>
            <span className="flex items-center gap-1">
              <GitCompare className="h-3 w-3 shrink-0" />
              {compte.nbCorrections === 0
                ? "Aucune modification journalisee"
                : `${compte.nbCorrections} modification${compte.nbCorrections > 1 ? "s" : ""}`}
            </span>
            {compte.dernierCr && <span>{dateCourte(compte.dernierCr)}</span>}
          </div>
        </div>
        {ouvert ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {ouvert && (
        <div className="space-y-2 border-t p-4">
          {compte.rapports.map((rapport) => {
            const modifications = correctionsParRapport.get(rapport.id) ?? [];
            return (
              <div key={rapport.id} className="rounded-md border bg-muted/30 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="text-[0.6rem]">
                    {nomOrgane(rapport.organe_detecte)}
                  </Badge>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {dateCourte(rapport.created_at)}
                  </span>
                  {rapport.rating !== null && (
                    <span className="flex items-center gap-0.5">
                      {Array.from({ length: rapport.rating }).map((_, index) => (
                        <Star
                          key={index}
                          className="h-3 w-3 fill-warning text-warning"
                        />
                      ))}
                    </span>
                  )}
                </div>

                {rapport.feedback_comment && (
                  <p className="mt-2 flex items-start gap-1.5 text-xs italic text-muted-foreground">
                    <MessageSquare className="mt-0.5 h-3 w-3 shrink-0" />
                    <span className="min-w-0 break-words">
                      {rapport.feedback_comment}
                    </span>
                  </p>
                )}

                {modifications.length === 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Aucune modification journalisee sur ce compte rendu.
                  </p>
                ) : (
                  <div className="mt-2 space-y-2">
                    {modifications.map((modification, index) => (
                      <div
                        key={`${modification.report_id}-${index}`}
                        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
                      >
                        <div className="rounded bg-destructive/5 p-2">
                          <p className="mb-1 text-[0.6rem] font-semibold uppercase tracking-wide text-destructive">
                            Avant
                          </p>
                          <p className="break-words text-xs text-muted-foreground">
                            {modification.before_excerpt}
                          </p>
                        </div>
                        <div className="rounded bg-success/5 p-2">
                          <p className="mb-1 text-[0.6rem] font-semibold uppercase tracking-wide text-success">
                            Apres
                          </p>
                          <p className="break-words text-xs text-muted-foreground">
                            {modification.after_excerpt}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Liste des cas d'un praticien                                       */
/* ------------------------------------------------------------------ */

function CarteDossier({
  dossier,
  selectionne,
  onSelectionner,
  onSupprimer,
}: {
  dossier: LigneDossierEtude;
  selectionne: boolean;
  onSelectionner: () => void;
  onSupprimer: () => Promise<void>;
}) {
  const [suppression, setSuppression] = useState(false);

  async function supprimer(evenement: React.MouseEvent) {
    // Le clic ne doit pas ouvrir le dossier qu'on est en train d'effacer.
    evenement.stopPropagation();
    if (
      !window.confirm(
        "Supprimer definitivement ce compte rendu et toutes ses mesures ?\n\n" +
          "A n'utiliser que sur un ESSAI. Une fois l'etude commencee, utilisez " +
          "l'exclusion : elle conserve le cas et se defait.",
      )
    ) {
      return;
    }
    setSuppression(true);
    try {
      await onSupprimer();
    } finally {
      setSuppression(false);
    }
  }
  const valide = estValide(dossier);

  return (
    // Un conteneur, deux boutons : ouvrir et supprimer. Imbriquer le second
    // dans le premier serait invalide, et le clic de suppression ouvrirait le
    // dossier qu'on efface.
    <div className="group relative">
    <button
      type="button"
      onClick={onSelectionner}
      aria-current={selectionne}
      className={cn(
        "w-full rounded-xl border bg-card p-3 pr-9 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        selectionne
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

      <div className="mt-1 text-[0.65rem] tabular-nums text-muted-foreground">
        {dateCourte(dossier.cree_a)}
      </div>

      {/* L'etat de validation en premier : c'est ce qui manquait a l'ecran. */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {dossier.abandonne ? (
          <Badge
            variant="destructive"
            className="gap-1 text-[0.6rem]"
            title={
              dossier.motif_abandon
                ? `Motif : ${MOTIF_ABANDON_LABELS[dossier.motif_abandon] ?? dossier.motif_abandon.replace(/_/g, " ")}`
                : undefined
            }
          >
            <Ban className="h-3 w-3" />
            Abandonne
          </Badge>
        ) : valide ? (
          <Badge variant="success" className="gap-1 text-[0.6rem] text-success">
            <CheckCircle2 className="h-3 w-3" />
            Valide
          </Badge>
        ) : (
          <Badge variant="warning" className="gap-1 text-[0.6rem]">
            <AlertTriangle className="h-3 w-3" />
            Non valide
          </Badge>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.65rem] text-muted-foreground">
        <span className="flex items-center gap-1">
          <ListChecks className="h-3 w-3 shrink-0" />
          <span className="tabular-nums">
            {dossier.nb_decidees}/{dossier.nb_propositions}
          </span>
          decidees
        </span>
        {/* Absent quand rien n'a ete valide : « 0 car. » ferait croire a un
            compte rendu accepte tel quel. */}
        {dossier.caracteres_modifies !== null && (
          <span className="flex items-center gap-1">
            <Pencil className="h-3 w-3 shrink-0" />
            <span className="tabular-nums">{dossier.caracteres_modifies}</span>
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
    </button>

      <button
        type="button"
        onClick={supprimer}
        disabled={suppression}
        title="Supprimer definitivement ce cas d'essai"
        aria-label="Supprimer ce compte rendu"
        className={cn(
          "absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-md",
          "text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
          "disabled:opacity-40",
        )}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Etats vides                                                        */
/* ------------------------------------------------------------------ */

function EtatVide({
  icone: Icone,
  titre,
  detail,
}: {
  icone: typeof Users;
  titre: string;
  detail: string;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card/50 px-4 py-14 text-center">
      <Icone className="h-8 w-8 text-muted-foreground/40" />
      <div className="max-w-sm">
        <p className="text-sm font-medium text-muted-foreground">{titre}</p>
        <p className="mt-1 text-xs text-muted-foreground/70">{detail}</p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  VuePraticiens                                                      */
/* ------------------------------------------------------------------ */

export default function VuePraticiens({
  dossiers,
  rapports,
  corrections,
  erreurExploitation,
  praticienSelectionne,
  dossierSelectionne,
  onSelectionnerPraticien,
  onSelectionnerDossier,
  onSupprimerDossier,
  compact = false,
}: VuePraticiensProps) {
  const lignes = useMemo(() => agregerPraticiens(dossiers), [dossiers]);
  const { comptes, parRapport } = useMemo(
    () => agregerComptes(rapports, corrections),
    [rapports, corrections],
  );

  const casDuPraticien = useMemo(
    () =>
      praticienSelectionne === null
        ? []
        : dossiers.filter(
            (dossier) => dossier.praticien_id === praticienSelectionne,
          ),
    [dossiers, praticienSelectionne],
  );
  const ligneOuverte =
    lignes.find((ligne) => ligne.praticienId === praticienSelectionne) ?? null;

  /* --- Un praticien : ses cas, du plus recent au plus ancien --- */
  if (praticienSelectionne !== null && ligneOuverte !== null) {
    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onSelectionnerPraticien(null)}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Tous les praticiens
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <UserRound className="h-4 w-4 shrink-0 text-primary" />
            <h2
              className="truncate font-mono text-base font-bold"
              title={ligneOuverte.praticienId}
            >
              {ligneOuverte.praticienNom}
            </h2>
            <Badge variant="secondary" className="text-[0.65rem]">
              {ligneOuverte.nbCas} cas
            </Badge>
          </div>
        </div>

        {!compact && (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <ResumeChiffre
              icone={CheckCircle2}
              label="Cas valides"
              valeur={`${ligneOuverte.nbValides} / ${ligneOuverte.nbCas}`}
              detail={
                ligneOuverte.nbValides === ligneOuverte.nbCas
                  ? "Tous termines"
                  : `${ligneOuverte.nbCas - ligneOuverte.nbValides} sans texte valide`
              }
            />
            <ResumeChiffre
              icone={Pencil}
              label="Charge d'edition"
              valeur={
                ligneOuverte.chargeEditionMediane === null
                  ? "Non mesuree"
                  : `${NOMBRE.format(ligneOuverte.chargeEditionMediane)} car.`
              }
              detail={
                ligneOuverte.chargeEditionMediane === null
                  ? "Aucun compte rendu valide"
                  : `mediane sur ${ligneOuverte.nbValides} cas valide${ligneOuverte.nbValides > 1 ? "s" : ""}`
              }
              mesuree={ligneOuverte.chargeEditionMediane !== null}
            />
            <ResumeChiffre
              icone={Clock}
              label="Revision (mediane)"
              valeur={
                ligneOuverte.revisionMedianeMs === null
                  ? "Non mesuree"
                  : dureeCompacte(ligneOuverte.revisionMedianeMs)
              }
              detail="hors interruptions"
              mesuree={ligneOuverte.revisionMedianeMs !== null}
            />
            <ResumeChiffre
              icone={ListChecks}
              label="Decisions"
              valeur={`${ligneOuverte.nbDecidees} / ${ligneOuverte.nbPropositions}`}
              detail="propositions tranchees"
            />
          </div>
        )}

        {casDuPraticien.length === 0 ? (
          <EtatVide
            icone={FolderOpen}
            titre="Aucun cas pour ce praticien"
            detail="Les dossiers apparaitront ici des la premiere dictee."
          />
        ) : (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {casDuPraticien.length} cas
            </p>
            {casDuPraticien.map((dossier) => (
              <CarteDossier
                key={dossier.id}
                dossier={dossier}
                selectionne={dossier.id === dossierSelectionne}
                onSelectionner={() => onSelectionnerDossier(dossier.id)}
                onSupprimer={() => onSupprimerDossier(dossier.id)}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  /* --- Tous les praticiens --- */
  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-bold">Praticiens</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Un praticien par ligne. Cliquez son identifiant pour ouvrir ses cas,
            puis un cas pour remonter jusqu'a la phrase de dictee en cause.
            L'etude ne conserve aucun nom : le praticien y est un identifiant de
            compte.
          </p>
        </div>

        {lignes.length === 0 ? (
          <EtatVide
            icone={Users}
            titre="Aucun praticien n'a encore travaille"
            detail="Des la premiere dictee, le praticien apparait ici avec ses cas, ses validations et sa charge d'edition."
          />
        ) : (
          <TableauPraticiens
            lignes={lignes}
            onSelectionner={onSelectionnerPraticien}
          />
        )}
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-bold">Comptes utilisateurs</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Les comptes rendus enregistres, avec le nom du compte, l'avis laisse
            et les modifications journalisees. Ces enregistrements ne portent pas
            l'identifiant d'etude : les deux listes restent donc distinctes,
            plutot que rapprochees a tort sur une ressemblance de dates.
          </p>
        </div>

        {erreurExploitation !== null ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              Comptes non lus : {erreurExploitation}. Rien n'est affiche ici —
              une liste vide se lirait comme une absence de compte rendu.
            </p>
          </div>
        ) : comptes.length === 0 ? (
          <EtatVide
            icone={FolderOpen}
            titre="Aucun compte rendu enregistre"
            detail="Un compte rendu apparait ici lorsque le praticien le declare termine. Tant qu'il reste en brouillon, il n'existe que sur son poste."
          />
        ) : (
          <div className="space-y-2">
            {comptes.map((compte) => (
              <CarteCompte
                key={compte.email}
                compte={compte}
                correctionsParRapport={parRapport}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ResumeChiffre                                                      */
/* ------------------------------------------------------------------ */

function ResumeChiffre({
  icone: Icone,
  label,
  valeur,
  detail,
  mesuree = true,
}: {
  icone: typeof Users;
  label: string;
  valeur: string;
  detail: string;
  /** Une absence de mesure ne doit jamais avoir l'allure d'un chiffre mesure. */
  mesuree?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icone className="h-4 w-4 shrink-0" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p
        className={cn(
          "mt-2",
          mesuree
            ? "text-xl font-bold tabular-nums"
            : "text-sm font-medium text-muted-foreground",
        )}
      >
        {valeur}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}
