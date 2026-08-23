import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  FolderOpen,
  LayoutDashboard,
  Pencil,
  RefreshCw,
  Star,
  Users,
  Download,} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/config";
import SyntheseEtude from "@/components/etude-admin/SyntheseEtude";
import type { DonneesSynthese } from "@/components/etude-admin/SyntheseEtude";
import type { LigneDossierEtude } from "@/components/etude-admin/ListeDossiersEtude";
import VuePraticiens from "@/components/admin/VuePraticiens";
import VueDossier from "@/components/admin/VueDossier";
import type { DossierAdmin } from "@/components/admin/VueDossier";
import {
  chargerDossier,
  chargerDossiers,
  chargerSynthese,
} from "@/services/etude";
import {
  getAdminCorrections,
  getAdminReports,
  getAdminStats,
} from "@/services/api";
import type {
  AdminCorrection,
  AdminReport,
  AdminStats,
} from "@/services/api";

/**
 * UNE administration, qui montre tout.
 *
 * La separation entre « exploitation » et « etude » etait une distinction de
 * concepteur : celui qui regarde veut un praticien, ses comptes rendus, ce
 * qu'il a change, et les chiffres qui en decoulent — au meme endroit. Les
 * trois onglets suivent donc le chemin du regard, pas la provenance des
 * donnees : ou en est-on, qui a fait quoi, et ce que disent les indicateurs.
 */
type Onglet = "ensemble" | "praticiens" | "indicateurs";

interface AdminPageProps {
  /** Jeton fourni par le point d'assemblage : cette page ne gere aucune session. */
  token: string | null;
  onBack: () => void;
}

/* ------------------------------------------------------------------ */
/*  Etats partages                                                     */
/* ------------------------------------------------------------------ */

function messageErreur(erreur: unknown): string {
  return erreur instanceof Error ? erreur.message : "Erreur inconnue";
}

/* ------------------------------------------------------------------ */
/*  Lecture                                                            */
/* ------------------------------------------------------------------ */

/** Une lecture aboutie ou son motif d'echec : jamais un resultat vide muet. */
type Lecture<T> = { ok: true; valeur: T } | { ok: false; message: string };

interface LectureAdministration {
  etude: Lecture<{
    synthese: DonneesSynthese;
    dossiers: LigneDossierEtude[];
  }>;
  exploitation: Lecture<{
    stats: AdminStats;
    rapports: AdminReport[];
    corrections: AdminCorrection[];
  }>;
}

/**
 * Lit les deux familles de donnees et RESTITUE le resultat, sans jamais
 * toucher a l'etat : l'ecriture appartient a l'appelant, ce qui garde les
 * effets libres de rendu en cascade.
 *
 * Les deux familles sont lues en parallele mais rapportees separement : une
 * panne sur l'une ne doit pas faire disparaitre l'autre, ni la faire passer
 * pour vide.
 */
async function lireAdministration(): Promise<LectureAdministration> {
  const [etude, exploitation] = await Promise.allSettled([
    Promise.all([chargerSynthese(), chargerDossiers()]),
    Promise.all([getAdminStats(), getAdminReports(), getAdminCorrections()]),
  ]);

  return {
    etude:
      etude.status === "fulfilled"
        ? {
            ok: true,
            valeur: { synthese: etude.value[0], dossiers: etude.value[1] },
          }
        : { ok: false, message: messageErreur(etude.reason) },
    exploitation:
      exploitation.status === "fulfilled"
        ? {
            ok: true,
            valeur: {
              stats: exploitation.value[0],
              rapports: exploitation.value[1],
              corrections: exploitation.value[2],
            },
          }
        : { ok: false, message: messageErreur(exploitation.reason) },
  };
}

function Chargement() {
  return (
    <div className="flex items-center justify-center py-20 text-muted-foreground">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-primary" />
    </div>
  );
}

function MessageErreur({
  message,
  onReessayer,
}: {
  message: string;
  onReessayer: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center">
      <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
      <p className="min-w-0 flex-1 break-words text-sm text-muted-foreground">
        {message}
      </p>
      <Button variant="outline" size="sm" onClick={onReessayer}>
        <RefreshCw className="h-3.5 w-3.5" />
        Reessayer
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Formatage                                                          */
/* ------------------------------------------------------------------ */

const NOMBRE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

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
/*  CarteChiffre                                                       */
/* ------------------------------------------------------------------ */

function CarteChiffre({
  icone: Icone,
  label,
  valeur,
  detail,
  mesuree = true,
}: {
  icone: typeof Users;
  label: string;
  valeur: string;
  detail?: string;
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
            ? "text-2xl font-bold tabular-nums"
            : "text-sm font-medium text-muted-foreground",
        )}
      >
        {valeur}
      </p>
      {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  VueEnsemble                                                        */
/* ------------------------------------------------------------------ */

interface EtatCorpus {
  nbPraticiens: number;
  nbCas: number;
  nbValides: number;
  nbAbandonnes: number;
  nbEnSuspens: number;
}

/**
 * Un cas est valide quand la charge d'edition existe : le backend ne la calcule
 * qu'a la cloture, contre le texte reellement valide. Le reste se partage entre
 * les abandons — une donnee du protocole — et les cas laisses en suspens, qui
 * sont exactement ce que l'administration ne voyait pas.
 */
function etatDuCorpus(dossiers: LigneDossierEtude[]): EtatCorpus {
  const valides = dossiers.filter(
    (dossier) => dossier.caracteres_modifies !== null,
  ).length;
  // Un abandon n'est compte ici que s'il n'a pas de texte valide : sans cette
  // precaution, un cas compte deux fois et « en suspens » passerait negatif.
  const abandonnes = dossiers.filter(
    (dossier) => dossier.abandonne && dossier.caracteres_modifies === null,
  ).length;
  return {
    nbPraticiens: new Set(dossiers.map((dossier) => dossier.praticien_id)).size,
    nbCas: dossiers.length,
    nbValides: valides,
    nbAbandonnes: abandonnes,
    nbEnSuspens: dossiers.length - valides - abandonnes,
  };
}

function VueEnsemble({
  etat,
  chargeMoyenne,
  stats,
  erreurExploitation,
  derniersCas,
  onOuvrirCas,
}: {
  etat: EtatCorpus;
  /** Moyenne des caracteres modifies, `null` tant qu'aucun cas n'est cloture. */
  chargeMoyenne: number | null;
  stats: AdminStats | null;
  erreurExploitation: string | null;
  derniersCas: LigneDossierEtude[];
  onOuvrirCas: (dossier: LigneDossierEtude) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Le bandeau qui repond a la question posee : est-ce que les praticiens
          disent que leur compte rendu est termine ? */}
      {etat.nbCas === 0 ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-dashed p-4">
          <FolderOpen className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Rien n'a encore ete enregistre. Des la premiere dictee, le praticien,
            ses cas et sa charge d'edition apparaitront ici.
          </p>
        </div>
      ) : etat.nbValides === 0 ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/5 p-4">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              Aucun compte rendu valide sur {etat.nbCas} cas
            </p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              Tant qu'un praticien ne declare pas son compte rendu termine, le
              texte valide n'arrive pas en base : la charge d'edition ne se
              calcule pas et les indicateurs restent sans mesure. Ce n'est pas
              une charge d'edition nulle, c'est une absence de validation.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2.5 rounded-lg border border-success/30 bg-success/5 p-4">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
          <p className="text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">
              {etat.nbValides} cas sur {etat.nbCas}
            </span>{" "}
            ont un compte rendu valide.
            {etat.nbEnSuspens > 0 && (
              <>
                {" "}
                {etat.nbEnSuspens} cas {etat.nbEnSuspens > 1 ? "restent" : "reste"}{" "}
                en suspens : ni valide{etat.nbEnSuspens > 1 ? "s" : ""} ni
                abandonne{etat.nbEnSuspens > 1 ? "s" : ""}.
              </>
            )}
          </p>
        </div>
      )}

      {/* L'etude : ce qui se mesure */}
      <section className="space-y-3">
        <h2 className="text-sm font-bold">Ou en est-on</h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <CarteChiffre
            icone={Users}
            label="Praticiens actifs"
            valeur={etat.nbPraticiens.toString()}
            detail="au moins un cas dicte"
          />
          <CarteChiffre
            icone={FolderOpen}
            label="Cas"
            valeur={etat.nbCas.toString()}
            detail={
              etat.nbAbandonnes > 0
                ? `dont ${etat.nbAbandonnes} abandonne${etat.nbAbandonnes > 1 ? "s" : ""}`
                : "aucun abandon declare"
            }
          />
          <CarteChiffre
            icone={CheckCircle2}
            label="Cas valides"
            valeur={`${etat.nbValides} / ${etat.nbCas}`}
            detail={`${etat.nbCas - etat.nbValides} sans texte valide`}
          />
          <CarteChiffre
            icone={Pencil}
            label="Charge d'edition"
            valeur={
              chargeMoyenne === null
                ? "Non mesuree"
                : `${NOMBRE.format(chargeMoyenne)} car.`
            }
            detail={
              chargeMoyenne === null
                ? "aucun cas cloture"
                : "moyenne par cas valide"
            }
            mesuree={chargeMoyenne !== null}
          />
        </div>
      </section>

      {/* L'exploitation : ce qui est enregistre cote comptes */}
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-bold">Comptes rendus enregistres</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Ce que les comptes ont sauvegarde, avec leurs avis et les
            modifications journalisees. Le detail par utilisateur est dans
            l'onglet Praticiens.
          </p>
        </div>

        {erreurExploitation !== null ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              Ces chiffres n'ont pas pu etre lus : {erreurExploitation}. Aucun
              nombre n'est affiche — un zero se lirait comme une mesure.
            </p>
          </div>
        ) : stats === null ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
            Aucune donnee d'exploitation.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <CarteChiffre
                icone={FolderOpen}
                label="Comptes rendus"
                valeur={stats.total_reports.toString()}
              />
              <CarteChiffre
                icone={Users}
                label="Comptes"
                valeur={stats.total_users.toString()}
              />
              <CarteChiffre
                icone={Star}
                label="Note moyenne"
                valeur={
                  stats.average_rating === null
                    ? "Non mesuree"
                    : `${NOMBRE.format(stats.average_rating)}/5`
                }
                detail={
                  stats.average_rating === null
                    ? "aucun avis depose"
                    : `sur ${stats.reports_with_feedback} avis`
                }
                mesuree={stats.average_rating !== null}
              />
              <CarteChiffre
                icone={Pencil}
                label="CR modifies"
                valeur={`${stats.reports_with_corrections} / ${stats.total_reports}`}
                detail="modifications journalisees"
              />
            </div>

            {/* Le diagnostic que le proprietaire reclame : zero correction
                journalisee ne veut pas dire zero correction faite. */}
            {stats.total_reports > 0 && stats.reports_with_corrections === 0 && (
              <div className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/5 p-4">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                <p className="text-sm leading-relaxed text-muted-foreground">
                  Aucune modification n'est journalisee sur les{" "}
                  {stats.total_reports} compte
                  {stats.total_reports > 1 ? "s" : ""} rendu
                  {stats.total_reports > 1 ? "s" : ""} enregistre
                  {stats.total_reports > 1 ? "s" : ""}. Cela ne prouve pas que
                  les praticiens n'ont rien corrige : c'est la comparaison
                  propose / valide de chaque cas qui fait foi, et elle se lit
                  dans l'onglet Praticiens.
                </p>
              </div>
            )}
          </>
        )}
      </section>

      {/* Le raccourci qui evite de repartir de la liste : d'un chiffre a un
          cas, puis a la phrase de dictee en cause. */}
      {derniersCas.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-bold">Derniers cas</h2>
          <div className="divide-y overflow-hidden rounded-lg border bg-card">
            {derniersCas.map((dossier) => (
              <button
                key={dossier.id}
                type="button"
                onClick={() => onOuvrirCas(dossier)}
                className={cn(
                  "flex w-full items-center gap-3 p-3 text-left transition-colors hover:bg-accent/30",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium first-letter:uppercase">
                      {nomOrgane(dossier.organe)}
                    </span>
                    {dossier.abandonne ? (
                      <Badge variant="destructive" className="text-[0.6rem]">
                        Abandonne
                      </Badge>
                    ) : dossier.caracteres_modifies === null ? (
                      <Badge variant="warning" className="text-[0.6rem]">
                        Non valide
                      </Badge>
                    ) : (
                      <Badge
                        variant="success"
                        className="text-[0.6rem] text-success"
                      >
                        Valide
                      </Badge>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.65rem] text-muted-foreground">
                    <span
                      className="font-mono"
                      title={dossier.praticien_id}
                    >
                      {dossier.praticien_id.slice(0, 8)}
                    </span>
                    <span className="tabular-nums">
                      {dateCourte(dossier.cree_a)}
                    </span>
                    {dossier.revision_nette_ms !== null && (
                      <span className="flex items-center gap-1 tabular-nums">
                        <Clock className="h-3 w-3 shrink-0" />
                        {Math.round(dossier.revision_nette_ms / 1000)} s
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  AdminPage                                                          */
/* ------------------------------------------------------------------ */

export default function AdminPage({ token, onBack }: AdminPageProps) {
  const [onglet, setOnglet] = useState<Onglet>("ensemble");
  const [exportEnCours, setExportEnCours] = useState(false);

  /**
   * Telecharge l'archive des donnees de l'etude.
   *
   * Le jeton d'authentification ne peut pas voyager dans une balise de lien :
   * on recupere donc le fichier, puis on declenche la sauvegarde depuis la
   * memoire. C'est aussi ce qui permet de dire au praticien quand la
   * preparation est en cours — une archive de plusieurs milliers de lignes ne
   * se fabrique pas instantanement.
   */
  const telechargerExport = useCallback(async () => {
    setExportEnCours(true);
    try {
      const reponse = await fetch(`${API_BASE}/admin/etude/export`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!reponse.ok) throw new Error(`Export impossible (${reponse.status})`);
      const blob = await reponse.blob();
      const url = URL.createObjectURL(blob);
      const lien = document.createElement("a");
      lien.href = url;
      lien.download = `marc-etude-${new Date().toISOString().slice(0, 10)}.zip`;
      lien.click();
      URL.revokeObjectURL(url);
    } catch (erreur) {
      window.alert(
        erreur instanceof Error ? erreur.message : "Export impossible.",
      );
    } finally {
      setExportEnCours(false);
    }
  }, [token]);

  const [synthese, setSynthese] = useState<DonneesSynthese | null>(null);
  const [dossiers, setDossiers] = useState<LigneDossierEtude[]>([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [rapports, setRapports] = useState<AdminReport[]>([]);
  const [corrections, setCorrections] = useState<AdminCorrection[]>([]);
  const [erreurExploitation, setErreurExploitation] = useState<string | null>(
    null,
  );

  const [praticienId, setPraticienId] = useState<string | null>(null);
  const [dossierId, setDossierId] = useState<string | null>(null);
  /** Le cas lu est garde AVEC son identifiant : sans cela, le detail du cas
   *  precedent resterait affiche sous le titre du suivant pendant sa lecture. */
  const [detail, setDetail] = useState<{
    id: string;
    dossier: DossierAdmin;
  } | null>(null);
  const [detailErreur, setDetailErreur] = useState<{
    id: string;
    message: string;
  } | null>(null);
  /** Relancer une lecture : re-selectionner le meme identifiant ne relancerait
   *  rien, React ne renotifie pas un etat inchange. */
  const [rechargement, setRechargement] = useState(0);

  // L'effet ne fait que declencher la lecture : tout l'etat s'ecrit dans la
  // continuation, une fois la reponse recue. Le drapeau `obsolete` protege du
  // cas ou une reponse lente arrive apres un rechargement.
  useEffect(() => {
    if (token === null) return;
    let obsolete = false;
    lireAdministration().then((vue) => {
      if (obsolete) return;
      if (vue.etude.ok) {
        setSynthese(vue.etude.valeur.synthese);
        setDossiers(vue.etude.valeur.dossiers);
        setErreur(null);
      } else {
        setErreur(vue.etude.message);
      }
      if (vue.exploitation.ok) {
        setStats(vue.exploitation.valeur.stats);
        setRapports(vue.exploitation.valeur.rapports);
        setCorrections(vue.exploitation.valeur.corrections);
        setErreurExploitation(null);
      } else {
        setErreurExploitation(vue.exploitation.message);
      }
      setChargement(false);
    });
    return () => {
      obsolete = true;
    };
  }, [token, rechargement]);

  // Le detail suit la selection. Le drapeau `obsolete` protege du cas ou une
  // reponse lente arrive apres qu'un autre cas a ete ouvert.
  useEffect(() => {
    if (token === null || dossierId === null) return;
    let obsolete = false;
    chargerDossier(dossierId)
      .then((vue) => {
        if (!obsolete) setDetail({ id: dossierId, dossier: vue });
      })
      .catch((echec: unknown) => {
        if (!obsolete)
          setDetailErreur({ id: dossierId, message: messageErreur(echec) });
      });
    return () => {
      obsolete = true;
    };
  }, [dossierId, token, rechargement]);

  const actualiser = useCallback(() => {
    setChargement(true);
    // Le cas ouvert est relu lui aussi : actualiser doit tout rafraichir, sinon
    // l'ecran melange deux instants de la base.
    setDetail(null);
    setDetailErreur(null);
    setRechargement((n) => n + 1);
  }, []);

  const reessayerCas = useCallback(() => {
    setDetailErreur(null);
    setRechargement((n) => n + 1);
  }, []);

  const etat = useMemo(() => etatDuCorpus(dossiers), [dossiers]);
  // La liste arrive deja triee du plus recent au plus ancien.
  const derniersCas = useMemo(() => dossiers.slice(0, 6), [dossiers]);

  const ouvrirPraticien = useCallback((identifiant: string | null) => {
    setPraticienId(identifiant);
    // Changer de praticien referme le cas ouvert : il appartenait au precedent.
    setDossierId(null);
  }, []);

  const ouvrirCas = useCallback((dossier: LigneDossierEtude) => {
    setOnglet("praticiens");
    setPraticienId(dossier.praticien_id);
    setDossierId(dossier.id);
  }, []);

  const casOuvert = dossiers.find((dossier) => dossier.id === dossierId) ?? null;

  // Sans jeton, il n'y a pas d'attente a montrer : il y a un refus a expliquer.
  const enChargement = token !== null && chargement;
  const messageGlobal =
    token === null
      ? "Authentification requise pour consulter l'administration."
      : erreur;

  // Le cas est en cours de lecture tant qu'on n'a ni son detail ni son echec :
  // deduit de ce qu'on possede, l'indicateur ne peut pas se desynchroniser.
  const detailDuCas = detail?.id === dossierId ? detail.dossier : null;
  const erreurDuCas =
    detailErreur?.id === dossierId ? detailErreur.message : null;

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b px-5">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="truncate text-base font-bold">Administration</h1>
        {/* L'export est la PREMIERE action de cet ecran : aucun depouillement
            serieux ne se fait dans un navigateur. Un tableau qu'on ne peut pas
            sortir n'est pas une donnee d'etude, c'est une capture d'ecran. */}
        <Button
          variant="outline"
          size="sm"
          onClick={telechargerExport}
          disabled={exportEnCours}
          className="ml-auto"
        >
          <Download className="h-3.5 w-3.5" />
          <span className="hide-mobile">
            {exportEnCours ? "Préparation…" : "Exporter (CSV)"}
          </span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={actualiser}
          title="Actualiser"
        >
          <RefreshCw className={cn("h-4 w-4", enChargement && "animate-spin")} />
        </Button>
      </header>

      <div className="flex overflow-x-auto border-b scrollbar-thin">
        {(
          [
            { cle: "ensemble", label: "Vue d'ensemble", icone: LayoutDashboard },
            { cle: "praticiens", label: "Praticiens", icone: Users },
            { cle: "indicateurs", label: "Indicateurs", icone: BarChart3 },
          ] as const
        ).map(({ cle, label, icone: Icone }) => (
          <button
            key={cle}
            type="button"
            onClick={() => setOnglet(cle)}
            className={cn(
              "flex shrink-0 items-center gap-2 px-4 py-3 text-sm font-medium transition-colors sm:px-5",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              onglet === cle
                ? "border-b-2 border-primary text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icone className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <main className="flex-1 overflow-y-auto p-4 sm:p-5">
        {/* Plus large des que la liste des cas cotoie le cas ouvert : la
            comparaison propose / valide n'a d'interet que cote a cote. */}
        <div
          className={cn(
            "mx-auto w-full",
            onglet === "praticiens" ? "max-w-7xl" : "max-w-5xl",
          )}
        >
          {messageGlobal !== null ? (
            <MessageErreur message={messageGlobal} onReessayer={actualiser} />
          ) : enChargement && synthese === null ? (
            <Chargement />
          ) : onglet === "ensemble" ? (
            <VueEnsemble
              etat={etat}
              chargeMoyenne={synthese?.corpus.caracteres_modifies_moyen ?? null}
              stats={stats}
              erreurExploitation={erreurExploitation}
              derniersCas={derniersCas}
              onOuvrirCas={ouvrirCas}
            />
          ) : onglet === "indicateurs" ? (
            synthese && <SyntheseEtude synthese={synthese} />
          ) : (
            <div className="space-y-4">
              {/* Fil d'Ariane : le contexte reste lisible jusqu'au fond du
                  parcours, et chaque niveau se remonte d'un clic. */}
              {praticienId !== null && (
                <nav
                  aria-label="Fil d'Ariane"
                  className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground"
                >
                  <button
                    type="button"
                    onClick={() => ouvrirPraticien(null)}
                    className="rounded font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Praticiens
                  </button>
                  <ChevronRight className="h-3 w-3 shrink-0" />
                  {dossierId === null ? (
                    <span className="font-mono" title={praticienId}>
                      {praticienId.slice(0, 8)}
                    </span>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => setDossierId(null)}
                        title={praticienId}
                        className="rounded font-mono font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {praticienId.slice(0, 8)}
                      </button>
                      <ChevronRight className="h-3 w-3 shrink-0" />
                      <span className="first-letter:uppercase">
                        {casOuvert
                          ? `Cas ${casOuvert.index_session} · ${nomOrgane(casOuvert.organe)}`
                          : "Cas"}
                      </span>
                    </>
                  )}
                </nav>
              )}

              {dossierId === null ? (
                <VuePraticiens
                  dossiers={dossiers}
                  rapports={rapports}
                  corrections={corrections}
                  erreurExploitation={erreurExploitation}
                  praticienSelectionne={praticienId}
                  dossierSelectionne={null}
                  onSelectionnerPraticien={ouvrirPraticien}
                  onSelectionnerDossier={setDossierId}
                />
              ) : (
                <div className="grid gap-4 xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
                  {/* La liste des cas du praticien reste sous les yeux : c'est
                      ce qui permet d'enchainer les dossiers sans revenir en
                      arriere. Sous xl, elle laisse la place au cas ouvert. */}
                  <div className="hidden min-w-0 xl:sticky xl:top-0 xl:block xl:max-h-[calc(100vh-9rem)] xl:self-start xl:overflow-y-auto xl:pr-1 scrollbar-thin">
                    <VuePraticiens
                      dossiers={dossiers}
                      rapports={rapports}
                      corrections={corrections}
                      erreurExploitation={erreurExploitation}
                      praticienSelectionne={praticienId}
                      dossierSelectionne={dossierId}
                      onSelectionnerPraticien={ouvrirPraticien}
                      onSelectionnerDossier={setDossierId}
                      compact
                    />
                  </div>

                  <div className="min-w-0">
                    {erreurDuCas !== null ? (
                      <MessageErreur
                        message={erreurDuCas}
                        onReessayer={reessayerCas}
                      />
                    ) : detailDuCas === null ? (
                      <Chargement />
                    ) : (
                      <VueDossier
                        dossier={detailDuCas}
                        onFermer={() => setDossierId(null)}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
