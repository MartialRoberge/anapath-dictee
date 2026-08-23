import {
  Users,
  FolderOpen,
  CheckCircle2,
  Ban,
  TrendingDown,
  AlertTriangle,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types — miroir de GET /admin/etude/synthese                        */
/* ------------------------------------------------------------------ */

/**
 * Un rapport, toujours accompagne de ses deux termes bruts.
 * `valeur` vaut null quand le denominateur est nul : c'est une ABSENCE DE
 * MESURE, pas un zero. Tout l'affichage ci-dessous decoule de cette nuance.
 */
export interface Taux {
  libelle: string;
  numerateur: number;
  denominateur: number;
  valeur: number | null;
}

export interface IndicateursPropositions {
  decidees: number;
  non_decidees: number;
  taux: Record<string, Taux>;
}

export interface DonneesSynthese {
  corpus: {
    nb_praticiens: number;
    nb_dossiers: number;
    nb_dossiers_clos: number;
    nb_abandons: number;
    motifs_abandon: Record<string, number>;
    organes: Record<string, number>;
    caracteres_modifies_moyen: number | null;
  };
  propositions: {
    toutes_decisions: IndicateursPropositions;
    hors_decisions_hatives: IndicateursPropositions;
  };
  apprentissage: {
    caracteres_modifies_par_tercile: (number | null)[];
    nb_dossiers_retenus: number;
    nb_praticiens_retenus: number;
    minimum_par_praticien: number;
  };
}

/* ------------------------------------------------------------------ */
/*  Formatage                                                          */
/* ------------------------------------------------------------------ */

const POURCENT = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  maximumFractionDigits: 1,
});

const POINTS = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});

/** Plus petite valeur que l'arrondi a une decimale sait encore distinguer. */
const PLANCHER_AFFICHABLE = 0.001;

/**
 * Formate un taux SANS jamais ecrire zero pour une valeur non nulle.
 *
 * Un taux d'hallucination de 1 sur 3 000 vaut 0,0003 : arrondi a une decimale,
 * il s'affiche « 0 % », typographiquement indiscernable d'un zero mesure. Or
 * 3 000 decisions, c'est le coeur du plan de l'etude, pas un cas limite — et
 * une hallucination reelle presentee comme un zero est exactement le mensonge
 * que le reste de ce tableau s'applique a eviter.
 */
function formaterTaux(valeur: number): string {
  if (valeur > 0 && valeur < PLANCHER_AFFICHABLE) return "< 0,1 %";
  if (valeur < 0 && valeur > -PLANCHER_AFFICHABLE) return "> -0,1 %";
  return POURCENT.format(valeur);
}

/** Meme regle sur l'ecart : un ecart reel non nul ne s'affiche jamais « 0 pt ». */
function formaterPoints(points: number): string {
  if (points > 0 && points < 0.05) return "< +0,1 pt";
  if (points < 0 && points > -0.05) return "> -0,1 pt";
  return `${POINTS.format(points)} pt`;
}

const NOMBRE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

/** Au-dela de ce seuil, l'ecart entre les deux lectures cesse d'etre du bruit. */
const ECART_NOTABLE_PT = 5;

const MOTIF_ABANDON_LABELS: Record<string, string> = {
  outil_trop_lent: "Outil trop lent",
  propositions_inexploitables: "Propositions inexploitables",
  interruption: "Interruption",
  cas_trop_complexe: "Cas trop complexe",
  autre: "Autre",
};

/**
 * Ce que compte le denominateur de chaque indicateur. Un taux se lit avec sa
 * base ou ne se lit pas : c'est cet ecran qui sert a preparer la publication.
 */
const BASE_INDICATEUR: Record<string, string> = {
  acceptation_sans_modification: "Base : decisions de restitution",
  hallucination: "Base : decisions de restitution",
  bruit: "Base : decisions de restitution",
  exactitude_codes:
    "Base : codes tranches — « je ne sais pas » exclu des deux termes",
  abstention_codes: "Base : tous les codes decides",
  utilite_completude: "Base : suggestions de completude decidees",
  decisions_hatives: "Base : toutes les decisions prises",
  changement_apres_justification: "Base : toutes les decisions prises",
};

function pluriel(n: number, mot: string): string {
  return `${n} ${mot}${n > 1 ? "s" : ""}`;
}

/* ------------------------------------------------------------------ */
/*  CelluleTaux — le coeur de l'honnetete de ce tableau                */
/* ------------------------------------------------------------------ */

function CelluleTaux({ taux }: { taux: Taux }) {
  // Rien observe : on le dit. Ecrire 0 % ici serait la maniere la plus
  // courante de mentir avec un tableau.
  if (taux.valeur === null) {
    return (
      <div className="space-y-1">
        <span className="inline-block rounded-md border border-dashed border-border px-2 py-0.5 text-xs font-medium text-muted-foreground">
          Non mesure
        </span>
        <p className="text-xs text-muted-foreground">Aucune decision observee</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <p className="text-lg font-bold tabular-nums">
        {formaterTaux(taux.valeur)}
      </p>
      <p className="text-xs tabular-nums text-muted-foreground">
        {taux.numerateur} / {pluriel(taux.denominateur, "decision")}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CelluleEcart — combien le verrou d'export a gonfle le resultat     */
/* ------------------------------------------------------------------ */

function CelluleEcart({ toutes, hors }: { toutes: Taux; hors: Taux }) {
  if (toutes.valeur === null || hors.valeur === null) {
    return <span className="text-xs text-muted-foreground">-</span>;
  }

  const ecartPt = (hors.valeur - toutes.valeur) * 100;
  const notable = Math.abs(ecartPt) >= ECART_NOTABLE_PT;

  return (
    <div className="space-y-1">
      <p
        className={cn(
          "text-sm font-semibold tabular-nums",
          notable ? "text-warning" : "text-muted-foreground",
        )}
      >
        {formaterPoints(ecartPt)}
      </p>
      {notable && (
        <p className="text-xs text-warning">
          Les decisions hatives pesent sur ce taux.
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CarteChiffre                                                       */
/* ------------------------------------------------------------------ */

function CarteChiffre({
  icon: Icon,
  label,
  value,
  hint,
  mesuree = true,
}: {
  icon: typeof FileText;
  label: string;
  value: string;
  hint?: string;
  /** Une absence de mesure ne doit jamais avoir l'allure d'un chiffre mesure. */
  mesuree?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4 shrink-0" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p
        className={cn(
          "mt-2",
          mesuree
            ? "text-2xl font-bold tabular-nums"
            : "text-sm font-medium text-muted-foreground",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Repartition — effectifs par valeur                                 */
/* ------------------------------------------------------------------ */

function Repartition({
  titre,
  effectifs,
  vide,
  libelle,
}: {
  titre: string;
  effectifs: Record<string, number>;
  vide: string;
  libelle?: (cle: string) => string;
}) {
  const entrees = Object.entries(effectifs);
  const maximum = Math.max(1, ...entrees.map(([, n]) => n));

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-3 text-sm font-semibold">{titre}</h3>
      {entrees.length === 0 ? (
        <p className="text-sm text-muted-foreground">{vide}</p>
      ) : (
        <div className="space-y-2">
          {entrees.map(([cle, nombre]) => {
            const texte = libelle ? libelle(cle) : cle.replace(/_/g, " ");
            return (
              <div key={cle} className="flex items-center gap-3">
                <span
                  className="w-28 shrink-0 truncate text-sm text-muted-foreground first-letter:uppercase sm:w-36"
                  title={texte}
                >
                  {texte}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{
                        width: `${Math.max((nombre / maximum) * 100, 5)}%`,
                      }}
                    />
                  </div>
                </div>
                <span className="text-sm font-medium tabular-nums">
                  {nombre}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SyntheseEtude                                                      */
/* ------------------------------------------------------------------ */

const TERCILE_LABELS = ["Premier tiers", "Deuxieme tiers", "Dernier tiers"];

export default function SyntheseEtude({
  synthese,
}: {
  synthese: DonneesSynthese;
}) {
  const { corpus, propositions, apprentissage } = synthese;
  const toutes = propositions.toutes_decisions;
  const hors = propositions.hors_decisions_hatives;
  const cles = Object.keys(toutes.taux);

  return (
    <div className="space-y-6">
      {corpus.nb_dossiers === 0 && (
        <div className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/5 p-4">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <p className="text-sm text-muted-foreground">
            L'etude ne contient encore aucun dossier. Les indicateurs
            ci-dessous restent donc sans mesure : ils s'afficheront des le
            premier cas cloture.
          </p>
        </div>
      )}

      {/* Corpus */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold">Corpus</h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <CarteChiffre
            icon={Users}
            label="Praticiens"
            value={corpus.nb_praticiens.toString()}
          />
          <CarteChiffre
            icon={FolderOpen}
            label="Dossiers"
            value={corpus.nb_dossiers.toString()}
          />
          <CarteChiffre
            icon={CheckCircle2}
            label="Dossiers clos"
            value={corpus.nb_dossiers_clos.toString()}
            hint={`${corpus.nb_dossiers - corpus.nb_dossiers_clos} en cours`}
          />
          <CarteChiffre
            icon={Ban}
            label="Abandons"
            value={corpus.nb_abandons.toString()}
            hint="Porte de sortie du protocole"
          />
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">
            Charge d'edition moyenne :{" "}
            {corpus.caracteres_modifies_moyen === null ? (
              <span className="font-medium text-foreground">
                non mesuree (aucun dossier cloture)
              </span>
            ) : (
              <span className="font-bold tabular-nums text-foreground">
                {NOMBRE.format(corpus.caracteres_modifies_moyen)} caracteres
                modifies par cas
              </span>
            )}
          </p>
        </div>
      </section>

      {/* Propositions : les deux lectures, cote a cote */}
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-bold">Decisions sur les propositions</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Chaque taux est calcule deux fois. L'ecart entre les deux lectures
            mesure combien les decisions trop rapides pour avoir ete lues
            gonflent le resultat : c'est un resultat en soi, pas un detail de
            methode.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-xs font-medium text-muted-foreground">
              Toutes decisions
            </p>
            <p className="mt-1 text-lg font-bold tabular-nums">
              {toutes.decidees} decidee{toutes.decidees > 1 ? "s" : ""}
            </p>
            <p className="text-xs text-muted-foreground">
              {toutes.non_decidees} proposition
              {toutes.non_decidees > 1 ? "s" : ""} sans decision
            </p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-xs font-medium text-muted-foreground">
              Hors decisions hatives
            </p>
            <p className="mt-1 text-lg font-bold tabular-nums">
              {hors.decidees} decidee{hors.decidees > 1 ? "s" : ""}
            </p>
            <p className="text-xs text-muted-foreground">
              {toutes.decidees - hors.decidees} ecartee
              {toutes.decidees - hors.decidees > 1 ? "s" : ""} comme hative
              {toutes.decidees - hors.decidees > 1 ? "s" : ""}
            </p>
          </div>
        </div>

        {/* Le tableau defile dans son conteneur, jamais la page. */}
        <div className="overflow-x-auto rounded-lg border bg-card">
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Indicateur
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Toutes decisions
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Hors decisions hatives
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Ecart
                </th>
              </tr>
            </thead>
            <tbody>
              {cles.map((cle) => (
                <tr key={cle} className="border-b align-top last:border-0">
                  <td className="px-4 py-3">
                    <p className="font-medium">{toutes.taux[cle].libelle || cle}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {BASE_INDICATEUR[cle] ?? "Base : decisions prises"}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <CelluleTaux taux={toutes.taux[cle]} />
                  </td>
                  <td className="px-4 py-3">
                    <CelluleTaux taux={hors.taux[cle]} />
                  </td>
                  <td className="px-4 py-3">
                    <CelluleEcart
                      toutes={toutes.taux[cle]}
                      hors={hors.taux[cle]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Repartitions */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Repartition
          titre="Dossiers par organe"
          effectifs={corpus.organes}
          vide="Aucun organe renseigne."
        />
        <Repartition
          titre="Motifs d'abandon"
          effectifs={corpus.motifs_abandon}
          vide="Aucun abandon declare."
          libelle={(cle) => MOTIF_ABANDON_LABELS[cle] ?? cle.replace(/_/g, " ")}
        />
      </section>

      {/* Apprentissage */}
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-bold">Effet d'apprentissage</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Charge d'edition moyenne par tiers d'ordre de passage. Si elle
            baisse du premier au dernier tiers, c'est le praticien qui
            s'habitue — pas l'outil qui s'ameliore. Chaque praticien est
            decoupe chez lui, puis les tiers sont moyennes a poids egal : sans
            cela, le praticien le plus actif porterait la courbe a lui seul.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {TERCILE_LABELS.map((label, index) => {
            // Un tiers sans dossier n'a pas de moyenne : « non mesure », jamais 0.
            const moyenne =
              apprentissage.caracteres_modifies_par_tercile[index] ?? null;
            return (
              <CarteChiffre
                key={label}
                icon={TrendingDown}
                label={label}
                value={moyenne === null ? "Non mesure" : NOMBRE.format(moyenne)}
                mesuree={moyenne !== null}
                hint="caracteres modifies"
              />
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          {/* L'effectif de PRATICIENS d'abord : c'est lui qui dit si la courbe
              tient debout. Un seul praticien a 30 cas donnerait 30 dossiers et
              une courbe qui ne parle que de lui. */}
          {pluriel(apprentissage.nb_praticiens_retenus, "praticien")} retenu
          {apprentissage.nb_praticiens_retenus > 1 ? "s" : ""} (
          {pluriel(apprentissage.nb_dossiers_retenus, "dossier")}) pour ce
          decoupage. Seuls les dossiers clotures comptent, et il faut au moins{" "}
          {apprentissage.minimum_par_praticien} cas par praticien pour le
          decouper en tiers.
        </p>
      </section>
    </div>
  );
}
