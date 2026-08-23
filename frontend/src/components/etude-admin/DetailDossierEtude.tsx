import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Clock,
  Quote,
  Zap,
  AlertTriangle,
  Pause,
  FlaskConical,
  MessageSquare,
  GitCompare,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Types — miroir de GET /admin/etude/dossiers/{id}                   */
/* ------------------------------------------------------------------ */

export interface PropositionEtude {
  id: string;
  type: string;
  sous_type: string | null;
  valeur_proposee: string;
  chemin: string | null;
  confiance: number | null;
  empan_debut: number | null;
  empan_fin: number | null;
  /** Passage de dictee deja decoupe par le serveur : aucun offset a recalculer. */
  empan_extrait: string;
  longueur_mots: number | null;
  decision: string | null;
  valeur_retenue: string | null;
  cause_erreur: string | null;
  latence_ms: number | null;
  hative: boolean;
  justif_ouverte: boolean;
  decision_changee_apres_justif: boolean;
}

export interface PrelevementEtude {
  rang: number;
  libelle: string;
  /** JSON brut du backend : [{"code","role","positions"}]. */
  codes: string | null;
}

export interface TempsDossierEtude {
  dictee_ms: number | null;
  generation_ms: number | null;
  revision_ms: number | null;
  revision_nette_ms: number | null;
  pauses_ms: number;
  nb_pauses: number;
}

export interface PauseEtude {
  debut: string;
  fin: string | null;
  duree_ms: number | null;
  cause: string;
}

export interface DossierDetailleEtude {
  id: string;
  praticien_id: string;
  organe: string | null;
  transcription: string;
  cr_propose: string;
  cr_valide: string | null;
  caracteres_modifies: number | null;
  abandonne: boolean;
  motif_abandon: string | null;
  omission_signalee: boolean | null;
  omission_texte: string | null;
  nb_prelevements_detecte: number | null;
  nb_prelevements_corrige: number | null;
  prelevements: PrelevementEtude[];
  propositions: PropositionEtude[];
  temps: TempsDossierEtude;
  pauses: PauseEtude[];
}

interface DetailDossierEtudeProps {
  dossier: DossierDetailleEtude;
  onFermer: () => void;
}

/* ------------------------------------------------------------------ */
/*  Vocabulaire — TROIS GRILLES DISTINCTES                             */
/*  Les melanger fausserait un taux publie : le libelle d'une decision */
/*  se lit toujours a travers le type de la proposition.               */
/* ------------------------------------------------------------------ */

type TonDecision = "success" | "warning" | "destructive" | "secondary";

interface LibelleDecision {
  texte: string;
  ton: TonDecision;
}

const GRILLES: Record<string, Record<string, LibelleDecision>> = {
  restitution: {
    conforme: { texte: "Conforme", ton: "success" },
    corrige: { texte: "A corriger", ton: "warning" },
    non_dicte: { texte: "Je n'ai pas dit ca", ton: "destructive" },
    hors_sujet: { texte: "Hors sujet", ton: "destructive" },
  },
  code: {
    juste: { texte: "Code juste", ton: "success" },
    corrige: { texte: "A corriger", ton: "warning" },
    // Ni erreur ni reussite : cette reponse sort des deux termes du taux
    // d'exactitude. La colorer comme un echec punirait l'honnetete.
    je_ne_sais_pas: { texte: "Je ne sais pas", ton: "secondary" },
  },
  completude: {
    pertinent_ajoute: { texte: "Pertinent, je l'ajoute", ton: "success" },
    // Juger pertinent puis ne pas l'ecrire n'est PAS un faux positif :
    // cette decision compte au numerateur de l'utilite.
    pertinent_non_retenu: {
      texte: "Pertinent, mais je ne le mets pas",
      ton: "secondary",
    },
    non_pertinent: { texte: "Pas pertinent ici", ton: "destructive" },
  },
};

/**
 * Le jeton `success-foreground` est blanc : sur le fond a 10 % du badge, il
 * faut reprendre la couleur pleine pour que la decision reste lisible.
 */
const CLASSE_TON: Record<TonDecision, string> = {
  success: "text-success",
  warning: "",
  destructive: "",
  secondary: "",
};

const TYPE_LABELS: Record<string, string> = {
  restitution: "Restitution",
  code: "Code",
  completude: "Completude",
};

const CAUSE_ERREUR_LABELS: Record<string, string> = {
  transcription: "La transcription a mal compris un mot",
  interpretation: "Transcription juste, interpretation fausse",
};

const MOTIF_ABANDON_LABELS: Record<string, string> = {
  outil_trop_lent: "Outil trop lent",
  propositions_inexploitables: "Propositions inexploitables",
  interruption: "Interruption",
  cas_trop_complexe: "Cas trop complexe",
  autre: "Autre",
};

const CAUSE_PAUSE_LABELS: Record<string, string> = {
  onglet_masque: "Onglet masque",
  inactivite: "Inactivite",
};

/* ------------------------------------------------------------------ */
/*  Formatage                                                          */
/* ------------------------------------------------------------------ */

function formatDuree(ms: number | null): string {
  if (ms === null) return "Non mesure";
  if (ms < 1000) return `${ms} ms`;
  const secondes = ms / 1000;
  if (secondes < 60) {
    return `${secondes.toFixed(1).replace(".", ",")} s`;
  }
  const minutes = Math.floor(secondes / 60);
  return `${minutes} min ${Math.round(secondes % 60)} s`;
}

/* ------------------------------------------------------------------ */
/*  Diff mot a mot propose / valide                                    */
/* ------------------------------------------------------------------ */

interface Segment {
  texte: string;
  etat: "commun" | "retire" | "ajoute";
}

/** Au-dela, la comparaison quadratique couterait plus qu'elle n'apporte. */
const LIMITE_DIFF = 250_000;

/**
 * Plus longue sous-sequence commune, au mot. On compare le texte BRUT et non
 * son rendu : la mesure publiee porte sur des caracteres, l'ecran doit montrer
 * exactement ce qui a ete compte.
 */
function diffMots(avant: string, apres: string): Segment[] | null {
  const a = avant.split(/(\s+)/).filter((mot) => mot !== "");
  const b = apres.split(/(\s+)/).filter((mot) => mot !== "");
  if (a.length * b.length > LIMITE_DIFF) return null;

  const largeur = b.length + 1;
  const table = new Uint32Array((a.length + 1) * largeur);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i * largeur + j] =
        a[i] === b[j]
          ? table[(i + 1) * largeur + j + 1] + 1
          : Math.max(table[(i + 1) * largeur + j], table[i * largeur + j + 1]);
    }
  }

  const segments: Segment[] = [];
  const pousser = (texte: string, etat: Segment["etat"]) => {
    const dernier = segments[segments.length - 1];
    if (dernier && dernier.etat === etat) dernier.texte += texte;
    else segments.push({ texte, etat });
  };

  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      pousser(a[i], "commun");
      i++;
      j++;
    } else if (table[(i + 1) * largeur + j] >= table[i * largeur + j + 1]) {
      pousser(a[i], "retire");
      i++;
    } else {
      pousser(b[j], "ajoute");
      j++;
    }
  }
  while (i < a.length) pousser(a[i++], "retire");
  while (j < b.length) pousser(b[j++], "ajoute");
  return segments;
}

/* ------------------------------------------------------------------ */
/*  ColonneCr                                                          */
/* ------------------------------------------------------------------ */

function ColonneCr({
  titre,
  texte,
  segments,
  marque,
}: {
  titre: string;
  texte: string;
  segments: Segment[] | null;
  marque: "retire" | "ajoute";
}) {
  return (
    <div className="min-w-0">
      <p className="mb-1.5 text-[0.65rem] font-bold uppercase tracking-wide text-muted-foreground">
        {titre}
      </p>
      <div className="max-h-80 overflow-y-auto rounded-md border bg-muted/30 p-3">
        <p className="whitespace-pre-wrap break-words text-xs leading-relaxed">
          {segments === null
            ? texte
            : segments
                .filter((s) => s.etat === "commun" || s.etat === marque)
                .map((segment, index) => (
                  <span
                    key={index}
                    className={cn(
                      segment.etat === "retire" &&
                        "bg-destructive/10 text-destructive line-through",
                      segment.etat === "ajoute" && "bg-success/10 text-success",
                    )}
                  >
                    {segment.texte}
                  </span>
                ))}
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ComparaisonCr                                                      */
/* ------------------------------------------------------------------ */

function ComparaisonCr({
  crPropose,
  crValide,
  caracteresModifies,
}: {
  crPropose: string;
  crValide: string | null;
  caracteresModifies: number | null;
}) {
  const segments = useMemo(
    () => (crValide === null ? null : diffMots(crPropose, crValide)),
    [crPropose, crValide],
  );

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <GitCompare className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Propose puis valide</h3>
        {caracteresModifies !== null && (
          <Badge variant="secondary" className="text-[0.65rem]">
            {caracteresModifies} caractere{caracteresModifies > 1 ? "s" : ""}{" "}
            modifie{caracteresModifies > 1 ? "s" : ""}
          </Badge>
        )}
      </div>

      {crValide === null ? (
        <>
          <p className="mb-3 text-xs text-muted-foreground">
            Cas non cloture : aucun compte rendu valide a comparer.
          </p>
          <ColonneCr
            titre="Compte rendu propose"
            texte={crPropose}
            segments={null}
            marque="retire"
          />
        </>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <ColonneCr
            titre="Propose par l'outil"
            texte={crPropose}
            segments={segments}
            marque="retire"
          />
          <ColonneCr
            titre="Valide par le praticien"
            texte={crValide}
            segments={segments}
            marque="ajoute"
          />
        </div>
      )}

      {crValide !== null && segments === null && (
        <p className="mt-2 text-xs text-muted-foreground">
          Textes trop longs pour la comparaison mot a mot : les deux versions
          sont affichees telles quelles.
        </p>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  TranscriptionAncree                                                */
/* ------------------------------------------------------------------ */

function TranscriptionAncree({
  transcription,
  debut,
  fin,
}: {
  transcription: string;
  debut: number | null;
  fin: number | null;
}) {
  const marqueRef = useRef<HTMLElement | null>(null);

  // La dictee peut etre longue : sans ce recentrage, cliquer une proposition
  // surlignerait un passage reste hors du cadre visible.
  useEffect(() => {
    marqueRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [debut, fin]);

  const ancre = debut !== null && fin !== null && fin > debut;

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Dictee</h3>
      </div>
      <div className="max-h-64 overflow-y-auto rounded-md border bg-muted/30 p-3">
        <p className="whitespace-pre-wrap break-words text-xs leading-relaxed">
          {transcription.length === 0 ? (
            <span className="text-muted-foreground">
              Aucune transcription enregistree.
            </span>
          ) : ancre ? (
            <>
              {transcription.slice(0, debut)}
              <mark
                ref={marqueRef}
                className="rounded bg-warning/25 px-0.5 text-foreground"
              >
                {transcription.slice(debut, fin)}
              </mark>
              {transcription.slice(fin)}
            </>
          ) : (
            transcription
          )}
        </p>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Cliquez l'empan d'une proposition pour le retrouver ici.
      </p>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  CarteProposition                                                   */
/* ------------------------------------------------------------------ */

function CarteProposition({
  proposition,
  ciblee,
  onCibler,
}: {
  proposition: PropositionEtude;
  ciblee: boolean;
  onCibler: () => void;
}) {
  const libelle = proposition.decision
    ? GRILLES[proposition.type]?.[proposition.decision]
    : undefined;

  return (
    <div
      className={cn(
        "rounded-lg border p-3 transition-colors",
        ciblee ? "border-primary/40 bg-primary/5" : "bg-card",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="text-[0.6rem]">
          {TYPE_LABELS[proposition.type] ?? proposition.type}
        </Badge>
        {proposition.sous_type && (
          <span className="text-[0.65rem] text-muted-foreground">
            {proposition.sous_type.replace(/_/g, " ")}
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {/* Une decision hative est trop rapide pour avoir ete lue : elle doit
              se voir, c'est un signal de qualite du protocole. */}
          {proposition.hative && (
            <Badge
              variant="warning"
              className="gap-1 text-[0.6rem]"
              title="Decision plus rapide que le seuil de lecture"
            >
              <Zap className="h-3 w-3" />
              Hative
            </Badge>
          )}
          {libelle ? (
            <Badge
              variant={libelle.ton}
              className={cn("text-[0.6rem]", CLASSE_TON[libelle.ton])}
            >
              {libelle.texte}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[0.6rem]">
              {proposition.decision ?? "Sans decision"}
            </Badge>
          )}
        </div>
      </div>

      <p className="mt-2 break-words text-sm">{proposition.valeur_proposee}</p>

      {proposition.valeur_retenue !== null &&
        proposition.valeur_retenue !== proposition.valeur_proposee && (
          <p className="mt-1 break-words text-sm text-success">
            Retenu : {proposition.valeur_retenue}
          </p>
        )}

      {proposition.empan_extrait ? (
        <button
          type="button"
          onClick={onCibler}
          className={cn(
            "mt-2 flex w-full items-start gap-2 rounded-md border p-2 text-left transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            ciblee
              ? "border-primary/40 bg-primary/10"
              : "border-border bg-muted/40 hover:bg-muted",
          )}
          title="Situer ce passage dans la dictee"
        >
          <Quote className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
          <span className="min-w-0 break-words text-xs italic text-muted-foreground">
            {proposition.empan_extrait}
          </span>
        </button>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">
          Aucun passage de dictee rattache a cette proposition.
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.65rem] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Clock className="h-3 w-3 shrink-0" />
          {formatDuree(proposition.latence_ms)}
        </span>
        {proposition.confiance !== null && (
          <span className="tabular-nums">
            Confiance {Math.round(proposition.confiance * 100)} %
          </span>
        )}
        {proposition.chemin && (
          <span className="truncate font-mono">{proposition.chemin}</span>
        )}
        {proposition.justif_ouverte && <span>Justification ouverte</span>}
        {proposition.decision_changee_apres_justif && (
          <span className="font-medium text-warning">
            Avis change apres justification
          </span>
        )}
      </div>

      {proposition.cause_erreur && (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Cause :{" "}
          {CAUSE_ERREUR_LABELS[proposition.cause_erreur] ??
            proposition.cause_erreur}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  BlocTemps                                                          */
/* ------------------------------------------------------------------ */

function BlocTemps({
  temps,
  pauses,
}: {
  temps: TempsDossierEtude;
  pauses: PauseEtude[];
}) {
  const mesures: { label: string; valeur: string }[] = [
    { label: "Dictee", valeur: formatDuree(temps.dictee_ms) },
    { label: "Generation", valeur: formatDuree(temps.generation_ms) },
    { label: "Revision", valeur: formatDuree(temps.revision_ms) },
    { label: "Revision nette", valeur: formatDuree(temps.revision_nette_ms) },
  ];

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Clock className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Temps</h3>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {mesures.map((mesure) => (
          <div key={mesure.label}>
            <p className="text-xs text-muted-foreground">{mesure.label}</p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums">
              {mesure.valeur}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-3 border-t pt-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Pause className="h-3 w-3 shrink-0" />
          {temps.nb_pauses === 0 ? (
            <span>Aucune interruption neutralisee.</span>
          ) : (
            <span>
              {temps.nb_pauses} interruption{temps.nb_pauses > 1 ? "s" : ""} —{" "}
              {formatDuree(temps.pauses_ms)} deduites du chronometre
            </span>
          )}
        </div>
        {pauses.length > 0 && (
          <ul className="mt-2 space-y-1">
            {pauses.map((pause, index) => (
              <li
                key={`${pause.debut}-${index}`}
                className="flex flex-wrap items-center gap-x-2 text-[0.65rem] text-muted-foreground"
              >
                <span>{CAUSE_PAUSE_LABELS[pause.cause] ?? pause.cause}</span>
                <span className="tabular-nums">
                  {formatDuree(pause.duree_ms)}
                </span>
                <span className="tabular-nums">
                  {new Date(pause.debut).toLocaleTimeString("fr-FR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  BlocPrelevements                                                   */
/* ------------------------------------------------------------------ */

interface CodeAdicap {
  code?: string;
  role?: string;
}

/** Le backend stocke les codes en JSON brut : on lit sans jamais casser la vue. */
function lireCodes(brut: string | null): CodeAdicap[] {
  if (!brut) return [];
  try {
    const valeur: unknown = JSON.parse(brut);
    return Array.isArray(valeur) ? (valeur as CodeAdicap[]) : [];
  } catch {
    return [];
  }
}

function BlocPrelevements({
  prelevements,
  nbDetecte,
  nbCorrige,
}: {
  prelevements: PrelevementEtude[];
  nbDetecte: number | null;
  nbCorrige: number | null;
}) {
  const cardinaliteFaussee =
    nbDetecte !== null && nbCorrige !== null && nbDetecte !== nbCorrige;

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Prelevements</h3>
        <span className="text-xs text-muted-foreground">
          {nbDetecte ?? "?"} detecte{(nbDetecte ?? 0) > 1 ? "s" : ""} ·{" "}
          {nbCorrige === null ? "non corrige" : `${nbCorrige} apres correction`}
        </span>
        {cardinaliteFaussee && (
          <Badge variant="warning" className="text-[0.6rem]">
            Cardinalite corrigee
          </Badge>
        )}
      </div>

      {prelevements.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Aucun prelevement enregistre pour ce cas.
        </p>
      ) : (
        <ul className="space-y-2">
          {prelevements.map((prelevement) => (
            <li
              key={prelevement.rang}
              className="rounded-md border bg-muted/30 p-2"
            >
              <div className="flex items-start gap-2">
                <Badge variant="outline" className="shrink-0 text-[0.6rem]">
                  {prelevement.rang}
                </Badge>
                <span className="min-w-0 break-words text-xs">
                  {prelevement.libelle || "Libelle non renseigne"}
                </span>
              </div>
              {lireCodes(prelevement.codes).length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {lireCodes(prelevement.codes).map((code, index) => (
                    <Badge
                      key={`${code.code ?? "code"}-${index}`}
                      variant={code.role === "primaire" ? "default" : "outline"}
                      className="font-mono text-[0.6rem]"
                    >
                      {code.code ?? "?"}
                    </Badge>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  DetailDossierEtude                                                 */
/* ------------------------------------------------------------------ */

export default function DetailDossierEtude({
  dossier,
  onFermer,
}: DetailDossierEtudeProps) {
  const [propositionCiblee, setPropositionCiblee] = useState<string | null>(
    null,
  );

  const cible =
    dossier.propositions.find((p) => p.id === propositionCiblee) ?? null;
  const nbDecidees = dossier.propositions.filter(
    (p) => p.decision !== null,
  ).length;
  const nbHatives = dossier.propositions.filter((p) => p.hative).length;

  return (
    <div className="space-y-4">
      {/* En-tete : deux lignes, pour qu'un organe long ne soit jamais tronque
          par les identifiants sur un ecran etroit. */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onFermer}>
            <ArrowLeft className="h-3.5 w-3.5" />
            Retour a la liste
          </Button>
          <span className="ml-auto truncate font-mono text-[0.65rem] text-muted-foreground">
            {dossier.praticien_id.slice(0, 8)} · {dossier.id.slice(0, 8)}
          </span>
        </div>
        <h2 className="truncate text-base font-bold first-letter:uppercase">
          {dossier.organe?.replace(/_/g, " ") ?? "Organe non renseigne"}
        </h2>
      </div>

      {dossier.abandonne && (
        <div className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <p className="text-sm text-muted-foreground">
            Cas abandonne —{" "}
            <span className="font-medium text-foreground">
              {dossier.motif_abandon
                ? (MOTIF_ABANDON_LABELS[dossier.motif_abandon] ??
                  dossier.motif_abandon.replace(/_/g, " "))
                : "motif non precise"}
            </span>
            . Un abandon est une donnee du protocole, pas un incident.
          </p>
        </div>
      )}

      {dossier.omission_signalee && (
        <div className="flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/5 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              Omission signalee par le praticien
            </p>
            <p className="mt-0.5 break-words text-xs text-muted-foreground">
              {dossier.omission_texte || "Aucun detail fourni."}
            </p>
          </div>
        </div>
      )}

      <BlocTemps temps={dossier.temps} pauses={dossier.pauses} />

      <ComparaisonCr
        crPropose={dossier.cr_propose}
        crValide={dossier.cr_valide}
        caracteresModifies={dossier.caracteres_modifies}
      />

      <BlocPrelevements
        prelevements={dossier.prelevements}
        nbDetecte={dossier.nb_prelevements_detecte}
        nbCorrige={dossier.nb_prelevements_corrige}
      />

      <TranscriptionAncree
        transcription={dossier.transcription}
        debut={cible?.empan_debut ?? null}
        fin={cible?.empan_fin ?? null}
      />

      {/* Propositions */}
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">Propositions</h3>
          <span className="text-xs text-muted-foreground">
            {dossier.propositions.length} au total · {nbDecidees} decidee
            {nbDecidees > 1 ? "s" : ""}
          </span>
          {nbHatives > 0 && (
            <Badge variant="warning" className="gap-1 text-[0.6rem]">
              <Zap className="h-3 w-3" />
              {nbHatives} hative{nbHatives > 1 ? "s" : ""}
            </Badge>
          )}
        </div>

        {dossier.propositions.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
            Aucune proposition n'a ete soumise sur ce cas.
          </p>
        ) : (
          <div className="space-y-2">
            {dossier.propositions.map((proposition) => (
              <CarteProposition
                key={proposition.id}
                proposition={proposition}
                ciblee={proposition.id === propositionCiblee}
                onCibler={() =>
                  setPropositionCiblee((actuel) =>
                    actuel === proposition.id ? null : proposition.id,
                  )
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
