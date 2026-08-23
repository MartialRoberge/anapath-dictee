import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Clock,
  FlaskConical,
  GitCompare,
  MessageSquare,
  Pause,
  Quote,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { markdownToPlainText } from "@/lib/reportText";
import type {
  Decision,
  DecisionPourType,
  DossierDetaille,
  NomQuestionnaire,
  PauseDetaillee,
  PrelevementDetaille,
  PropositionDetaillee,
  RevisionDecision,
  TempsDossier,
  TypeProposition,
} from "@/services/etude";

/* ------------------------------------------------------------------ */
/*  Types — miroir de GET /admin/etude/dossiers/{id}                   */
/* ------------------------------------------------------------------ */

/**
 * Le cas est celui de `services/etude.ts`, pas une copie.
 *
 * Recopier la forme ici la ferait diverger en silence le jour ou le backend
 * renomme un champ : l'ecran afficherait alors des cases vides sans que rien
 * ne signale la rupture. En s'appuyant sur le miroir declare une seule fois,
 * c'est la compilation qui previent — et les unions fermees (type de
 * proposition, grille de decision, motif d'abandon) restent fermees jusqu'ici.
 */

/** Une reponse de questionnaire rattachee a ce cas. */
export interface ReponseQuestionnaireDossier {
  questionnaire: NomQuestionnaire;
  item: string;
  libelle: string | null;
  valeur: string;
  repondu_a: string | null;
}

/**
 * Le cas detaille, augmente des reponses de questionnaire.
 *
 * Le champ est OPTIONNEL tant que la route ne les sert pas : l'ecran distingue
 * alors « la question n'a pas ete posee a l'API » de « le praticien n'a rien
 * repondu ». Les confondre serait le meme mensonge qu'afficher 0 %.
 */
export type DossierAdmin = DossierDetaille & {
  questionnaires?: ReponseQuestionnaireDossier[];
};

interface VueDossierProps {
  dossier: DossierAdmin;
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

/**
 * Une table par grille, et chacune COMPLETE : le type impose une entree pour
 * chaque decision du protocole, si bien qu'une decision ajoutee au backend
 * casse la compilation au lieu de s'afficher comme un libelle brut.
 */
const GRILLES: {
  readonly [T in TypeProposition]: Readonly<
    Record<DecisionPourType<T>, LibelleDecision>
  >;
} = {
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
 * Le libelle d'une decision se lit TOUJOURS a travers le type de sa
 * proposition : « corrige » existe dans la grille restitution et dans la
 * grille code, et ne s'y compte pas de la meme facon.
 *
 * L'elargissement a `Decision` est necessaire parce que `GRILLES[type]` sur un
 * type non litteral rend l'union des trois tables, sur laquelle l'indexation
 * ne se type pas. Le resultat reste facultatif : la reponse pourrait etre hors
 * grille si la base porte une valeur d'une version anterieure du protocole.
 */
function libelleDecision(
  type: TypeProposition,
  decision: Decision,
): LibelleDecision | undefined {
  const grille: Partial<Record<Decision, LibelleDecision>> = GRILLES[type];
  return grille[decision];
}

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

/**
 * Les libelles ci-dessous s'indexent par une chaine et non par leur union,
 * puis retombent sur la valeur brute. C'est delibere : ces valeurs arrivent
 * d'une reponse JSON, donc non verifiees a l'execution. Un cas enregistre sous
 * une version anterieure du protocole doit s'afficher tel quel plutot que de
 * laisser une case vide. Les DECISIONS, elles, passent par `libelleDecision` :
 * leur table est complete, parce qu'un libelle de decision manquant fausserait
 * la lecture d'un taux publie.
 */
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

const QUESTIONNAIRE_LABELS: Record<string, string> = {
  inclusion: "Inclusion",
  par_cas: "Apres ce cas",
  fin_etude: "Fin d'etude",
};

/* ------------------------------------------------------------------ */
/*  Formatage                                                          */
/* ------------------------------------------------------------------ */

function formatDuree(ms: number | null): string {
  if (ms === null) return "Non mesure";
  if (ms < 1000) return `${ms} ms`;
  const secondes = ms / 1000;
  if (secondes < 60) return `${secondes.toFixed(1).replace(".", ",")} s`;
  const minutes = Math.floor(secondes / 60);
  return `${minutes} min ${Math.round(secondes % 60)} s`;
}

function heure(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function nomOrgane(organe: string | null): string {
  if (!organe) return "Organe non renseigne";
  return organe.replace(/_/g, " ");
}

/* ------------------------------------------------------------------ */
/*  Diff mot a mot propose / valide                                    */
/* ------------------------------------------------------------------ */

interface Segment {
  texte: string;
  etat: "commun" | "retire" | "ajoute";
}

/**
 * Budget de la comparaison quadratique, en cellules de table.
 *
 * Il ne porte que sur le NOYAU divergent, une fois le debut et la fin communs
 * retires : une relecture ordinaire laisse un noyau de quelques dizaines de
 * jetons, et meme une reecriture complete de 1 500 mots contre 1 500 mots
 * tient ici — 18 Mo transitoires, quelques dizaines de millisecondes. Le
 * garde-fou ne se declenche donc qu'en dehors de tout usage reel, et ne prive
 * jamais l'ecran de sa comparaison au moment ou elle sert.
 */
const LIMITE_DIFF = 9_000_000;

/** Mots ET espaces : garder les separateurs permet de rendre le texte exact. */
function jetons(texte: string): string[] {
  return texte.split(/(\s+)/).filter((jeton) => jeton !== "");
}

/**
 * Plus longue sous-sequence commune, au mot. On compare le texte BRUT et non
 * son rendu : la mesure publiee porte sur des caracteres, l'ecran doit montrer
 * exactement ce qui a ete compte.
 *
 * Le debut et la fin identiques sont retires avant le calcul. Un compte rendu
 * valide est presque toujours le compte rendu propose avec quelques retouches
 * locales : sans cette coupe, on paierait au prix fort la comparaison de deux
 * textes deja identiques a 95 %.
 */
function diffMots(avant: string, apres: string): Segment[] | null {
  const a = jetons(avant);
  const b = jetons(apres);

  let prefixe = 0;
  while (prefixe < a.length && prefixe < b.length && a[prefixe] === b[prefixe]) {
    prefixe++;
  }
  let suffixe = 0;
  while (
    suffixe < a.length - prefixe &&
    suffixe < b.length - prefixe &&
    a[a.length - 1 - suffixe] === b[b.length - 1 - suffixe]
  ) {
    suffixe++;
  }

  const noyauA = a.slice(prefixe, a.length - suffixe);
  const noyauB = b.slice(prefixe, b.length - suffixe);
  if (noyauA.length * noyauB.length > LIMITE_DIFF) return null;

  const segments: Segment[] = [];
  const pousser = (texte: string, etat: Segment["etat"]) => {
    const dernier = segments[segments.length - 1];
    if (dernier && dernier.etat === etat) dernier.texte += texte;
    else segments.push({ texte, etat });
  };

  if (prefixe > 0) pousser(a.slice(0, prefixe).join(""), "commun");

  const largeur = noyauB.length + 1;
  // 16 bits suffisent, et divisent la memoire par deux : la sous-sequence
  // commune ne depasse jamais min(noyauA, noyauB), lui-meme borne par la
  // racine du budget, soit 3 000 — tres loin des 65 535 representables.
  const table = new Uint16Array((noyauA.length + 1) * largeur);
  for (let i = noyauA.length - 1; i >= 0; i--) {
    for (let j = noyauB.length - 1; j >= 0; j--) {
      table[i * largeur + j] =
        noyauA[i] === noyauB[j]
          ? table[(i + 1) * largeur + j + 1] + 1
          : Math.max(table[(i + 1) * largeur + j], table[i * largeur + j + 1]);
    }
  }

  let i = 0;
  let j = 0;
  while (i < noyauA.length && j < noyauB.length) {
    if (noyauA[i] === noyauB[j]) {
      pousser(noyauA[i], "commun");
      i++;
      j++;
    } else if (table[(i + 1) * largeur + j] >= table[i * largeur + j + 1]) {
      pousser(noyauA[i], "retire");
      i++;
    } else {
      pousser(noyauB[j], "ajoute");
      j++;
    }
  }
  while (i < noyauA.length) pousser(noyauA[i++], "retire");
  while (j < noyauB.length) pousser(noyauB[j++], "ajoute");

  if (suffixe > 0) pousser(a.slice(a.length - suffixe).join(""), "commun");
  return segments;
}

function compterMots(texte: string): number {
  const nettoye = texte.trim();
  return nettoye === "" ? 0 : nettoye.split(/\s+/).length;
}

interface ResumeDiff {
  ajoutes: number;
  retires: number;
  reformules: number;
}

/**
 * Ce que le praticien a fait du texte propose, en trois nombres.
 *
 * Un remplacement n'est PAS un retrait plus un ajout independants : compte
 * ainsi, la moindre reformulation doublerait le volume de changement et
 * ferait passer une relecture de confort pour une reecriture. Les mots
 * retires et ajoutes qui se touchent sont donc apparies en « reformules ».
 */
function resumerDiff(segments: Segment[]): ResumeDiff {
  const resume: ResumeDiff = { ajoutes: 0, retires: 0, reformules: 0 };
  let index = 0;
  while (index < segments.length) {
    if (segments[index].etat === "commun") {
      index++;
      continue;
    }
    let motsRetires = 0;
    let motsAjoutes = 0;
    while (index < segments.length && segments[index].etat !== "commun") {
      const mots = compterMots(segments[index].texte);
      if (segments[index].etat === "retire") motsRetires += mots;
      else motsAjoutes += mots;
      index++;
    }
    const apparies = Math.min(motsRetires, motsAjoutes);
    resume.reformules += apparies;
    resume.retires += motsRetires - apparies;
    resume.ajoutes += motsAjoutes - apparies;
  }
  return resume;
}

/* ------------------------------------------------------------------ */
/*  Rendu du diff                                                      */
/* ------------------------------------------------------------------ */

function TexteSegmente({
  segments,
  garder,
}: {
  segments: Segment[];
  /** Etats retenus : les deux pour la vue fusionnee, un seul par colonne. */
  garder: Segment["etat"][];
}) {
  return (
    <p className="whitespace-pre-wrap break-words text-xs leading-relaxed">
      {segments
        .filter((segment) => garder.includes(segment.etat))
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
  );
}

function Cadre({ children }: { children: React.ReactNode }) {
  return (
    <div className="max-h-80 overflow-y-auto rounded-md border bg-muted/30 p-3 scrollbar-thin">
      {children}
    </div>
  );
}

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
      <Cadre>
        {segments === null ? (
          <p className="whitespace-pre-wrap break-words text-xs leading-relaxed">
            {texte}
          </p>
        ) : (
          <TexteSegmente segments={segments} garder={["commun", marque]} />
        )}
      </Cadre>
    </div>
  );
}

type ModeComparaison = "fusionnee" | "cote_a_cote";

/**
 * Le coeur de l'ecran : ce que l'outil a propose, ce que le praticien a garde.
 * Sans cette confrontation, la charge d'edition reste un nombre sans visage.
 */
function ComparaisonCr({
  crPropose,
  crValide,
  caracteresModifies,
}: {
  crPropose: string;
  crValide: string | null;
  caracteresModifies: number | null;
}) {
  const [mode, setMode] = useState<ModeComparaison>("fusionnee");

  const segments = useMemo(
    () =>
      crValide === null
        ? null
        // La syntaxe markdown est retiree AVANT la comparaison. L'afficher
        // brute couvrait le texte d'asterisques et rendait la comparaison
        // illisible — or c'est l'ecran ou l'on vient justement LIRE ce que le
        // praticien a change. Le diff reste mot a mot, il porte simplement sur
        // le texte tel qu'il se lit.
        : diffMots(markdownToPlainText(crPropose), markdownToPlainText(crValide)),
    [crPropose, crValide],
  );
  const resume = useMemo(
    () => (segments === null ? null : resumerDiff(segments)),
    [segments],
  );

  // Valide SANS retouche : c'est un resultat, et le plus favorable a l'outil.
  // Le laisser se deviner d'un « +0 -0 » le ferait passer pour une absence de
  // mesure, alors que la mesure a bien eu lieu et vaut zero.
  const inchange = crValide !== null && crValide === crPropose;

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <GitCompare className="h-4 w-4 shrink-0 text-primary" />
        <h3 className="text-sm font-semibold">Propose puis valide</h3>
        {caracteresModifies !== null && (
          <Badge variant="secondary" className="text-[0.65rem]">
            {caracteresModifies} caractere{caracteresModifies > 1 ? "s" : ""}{" "}
            modifie{caracteresModifies > 1 ? "s" : ""}
          </Badge>
        )}
        {/* Rien a confronter quand les deux textes sont identiques : le
            selecteur n'offrirait que deux colonnes jumelles. */}
        {segments !== null && !inchange && (
          <div className="ml-auto flex rounded-md border p-0.5">
            {(
              [
                { cle: "fusionnee", label: "Fusionne" },
                { cle: "cote_a_cote", label: "Cote a cote" },
              ] as const
            ).map(({ cle, label }) => (
              <button
                key={cle}
                type="button"
                onClick={() => setMode(cle)}
                aria-pressed={mode === cle}
                className={cn(
                  "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  mode === cle
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Le compte rendu jamais valide n'est pas un compte rendu sans
          correction : c'est un compte rendu dont personne n'a dit qu'il etait
          termine. C'est precisement la distinction qui manquait. */}
      {crValide === null ? (
        <>
          <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/5 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">
                Aucun compte rendu valide
              </span>{" "}
              : ce cas n'a jamais ete declare termine. Il n'y a donc rien a
              comparer, et la charge d'edition n'est pas mesurable — ce n'est
              pas une charge d'edition nulle.
            </p>
          </div>
          <ColonneCr
            titre="Compte rendu propose"
            texte={crPropose}
            segments={null}
            marque="retire"
          />
        </>
      ) : (
        <>
          {inchange ? (
            <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-success/30 bg-success/5 p-3">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">
                  Valide sans aucune retouche
                </span>{" "}
                : le texte declare termine est mot pour mot celui que l'outil a
                propose.
              </p>
            </div>
          ) : (
            resume !== null && (
              <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <span className="font-medium text-success tabular-nums">
                  +{resume.ajoutes} ajoute{resume.ajoutes > 1 ? "s" : ""}
                </span>
                <span className="font-medium text-destructive tabular-nums">
                  -{resume.retires} retire{resume.retires > 1 ? "s" : ""}
                </span>
                <span className="font-medium text-warning tabular-nums">
                  {resume.reformules} reformule
                  {resume.reformules > 1 ? "s" : ""}
                </span>
                <span className="text-muted-foreground">
                  mots ; un remplacement compte pour une reformulation, pas pour
                  deux operations
                </span>
              </div>
            )
          )}

          {segments === null ? (
            <>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <ColonneCr
                  titre="Propose par l'outil"
                  texte={crPropose}
                  segments={null}
                  marque="retire"
                />
                <ColonneCr
                  titre="Valide par le praticien"
                  texte={crValide}
                  segments={null}
                  marque="ajoute"
                />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Textes trop longs pour la comparaison mot a mot : les deux
                versions sont affichees telles quelles.
              </p>
            </>
          ) : /* `inchange` force la vue unique : le selecteur etant masque, un
                mode « cote a cote » herite du cas precedent bloquerait le
                lecteur devant deux colonnes identiques. */
          mode === "fusionnee" || inchange ? (
            <Cadre>
              <TexteSegmente
                segments={segments}
                garder={["commun", "retire", "ajoute"]}
              />
            </Cadre>
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
        </>
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
  ancrable,
}: {
  transcription: string;
  debut: number | null;
  fin: number | null;
  /** Vrai si au moins une proposition porte un passage de dictee. */
  ancrable: boolean;
}) {
  const marqueRef = useRef<HTMLElement | null>(null);
  const cadreRef = useRef<HTMLDivElement | null>(null);

  // La dictee peut etre longue : sans ce recentrage, cliquer une proposition
  // surlignerait un passage reste hors du cadre visible.
  //
  // Le defilement est calcule et applique AU SEUL CADRE. `scrollIntoView`
  // remonterait tous les ancetres defilables : la colonne du cas, puis la page
  // entiere sauteraient, et la proposition qu'on vient de cliquer sortirait de
  // l'ecran — exactement la perte de contexte qu'on veut eviter ici.
  useEffect(() => {
    const marque = marqueRef.current;
    const cadre = cadreRef.current;
    if (marque === null || cadre === null) return;
    const zoneMarque = marque.getBoundingClientRect();
    const zoneCadre = cadre.getBoundingClientRect();
    const ecart =
      zoneMarque.top -
      zoneCadre.top -
      (zoneCadre.height - zoneMarque.height) / 2;
    cadre.scrollTo({ top: cadre.scrollTop + ecart, behavior: "smooth" });
  }, [debut, fin]);

  const ancre = debut !== null && fin !== null && fin > debut;

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <MessageSquare className="h-4 w-4 shrink-0 text-primary" />
        <h3 className="text-sm font-semibold">Dictee</h3>
      </div>
      <div
        ref={cadreRef}
        className="max-h-64 overflow-y-auto rounded-md border bg-muted/30 p-3 scrollbar-thin"
      >
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
      {/* L'invitation ne s'affiche que si le geste est possible : sur un cas
          sans proposition ancree, elle designerait un clic introuvable. */}
      {ancrable && (
        <p className="mt-2 text-xs text-muted-foreground">
          Cliquez l'empan d'une proposition pour le retrouver ici.
        </p>
      )}
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
  proposition: PropositionDetaillee;
  ciblee: boolean;
  onCibler: () => void;
}) {
  const libelle =
    proposition.decision === null
      ? undefined
      : libelleDecision(proposition.type, proposition.decision);

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
          aria-pressed={ciblee}
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
        {proposition.longueur_mots !== null && (
          <span className="tabular-nums">
            {proposition.longueur_mots} mot
            {proposition.longueur_mots > 1 ? "s" : ""}
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

      <HistoriqueDecisions
        revisions={proposition.revisions}
        type={proposition.type}
      />
    </div>
  );
}

/**
 * Le chemin parcouru jusqu'a la decision finale.
 *
 * NE S'AFFICHE QUE QUAND L'AVIS A BOUGE. Sur un bloc decide une seule fois —
 * le cas de loin le plus frequent — l'historique repeterait la decision deja
 * lue juste au-dessus, et noierait les rares blocs ou il se passe quelque
 * chose. Ce sont ceux-la qu'on vient chercher ici : un praticien qui accepte,
 * ouvre la justification, puis refuse, raconte quelque chose sur l'outil que
 * l'etat final seul efface.
 */
function HistoriqueDecisions({
  revisions,
  type,
}: {
  revisions: RevisionDecision[];
  type: TypeProposition;
}) {
  if (revisions.length < 2) return null;

  return (
    <div className="mt-2 rounded-md border border-warning/40 bg-warning/5 p-2">
      <p className="text-xs font-medium text-warning">
        Avis modifie {revisions.length - 1} fois
      </p>
      <ol className="mt-1.5 space-y-1">
        {revisions.map((revision) => (
          <li
            key={revision.rang}
            className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground"
          >
            <span className="tabular-nums font-medium text-foreground">
              {revision.rang}.
            </span>
            <span className="font-medium text-foreground">
              {libelleDecision(type, revision.decision as Decision)?.texte ??
                revision.decision}
            </span>
            <time
              dateTime={revision.decide_a}
              className="tabular-nums"
              title={revision.decide_a}
            >
              {new Date(revision.decide_a).toLocaleTimeString("fr-FR")}
            </time>
            {revision.justif_ouverte && (
              <span className="italic">justification ouverte</span>
            )}
            {revision.valeur_retenue && (
              <span className="w-full truncate font-mono">
                « {revision.valeur_retenue} »
              </span>
            )}
          </li>
        ))}
      </ol>
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
  temps: TempsDossier;
  pauses: PauseDetaillee[];
}) {
  const mesures: { label: string; valeur: number | null }[] = [
    { label: "Dictee", valeur: temps.dictee_ms },
    { label: "Generation", valeur: temps.generation_ms },
    { label: "Revision", valeur: temps.revision_ms },
    { label: "Revision nette", valeur: temps.revision_nette_ms },
  ];

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Clock className="h-4 w-4 shrink-0 text-primary" />
        <h3 className="text-sm font-semibold">Temps</h3>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {mesures.map((mesure) => (
          <div key={mesure.label}>
            <p className="text-xs text-muted-foreground">{mesure.label}</p>
            <p
              className={cn(
                "mt-0.5 text-sm tabular-nums",
                mesure.valeur === null
                  ? "font-medium text-muted-foreground"
                  : "font-semibold",
              )}
            >
              {formatDuree(mesure.valeur)}
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
                <span className="tabular-nums">{heure(pause.debut)}</span>
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
function lireCodes(brut: string): CodeAdicap[] {
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
  prelevements: PrelevementDetaille[];
  nbDetecte: number | null;
  nbCorrige: number | null;
}) {
  const cardinaliteFaussee =
    nbDetecte !== null && nbCorrige !== null && nbDetecte !== nbCorrige;

  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FlaskConical className="h-4 w-4 shrink-0 text-primary" />
        <h3 className="text-sm font-semibold">Prelevements</h3>
        <span className="text-xs text-muted-foreground">
          {nbDetecte === null ? "detection non renseignee" : `${nbDetecte} detecte${nbDetecte > 1 ? "s" : ""}`}
          {" · "}
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
          {prelevements.map((prelevement) => {
            const codes = lireCodes(prelevement.codes);
            return (
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
                {codes.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {codes.map((code, index) => (
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
            );
          })}
        </ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  BlocQuestionnaires                                                 */
/* ------------------------------------------------------------------ */

function BlocQuestionnaires({
  reponses,
}: {
  reponses: ReponseQuestionnaireDossier[] | undefined;
}) {
  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <ClipboardList className="h-4 w-4 shrink-0 text-primary" />
        <h3 className="text-sm font-semibold">Questionnaires</h3>
      </div>

      {reponses === undefined ? (
        // Non servi n'est pas vide : dire « aucune reponse » ici laisserait
        // croire que le praticien n'a rien repondu.
        <p className="text-xs text-muted-foreground">
          Les reponses de questionnaire ne sont pas rattachees a ce cas par
          l'API. Rien n'est affiche plutot qu'un zero trompeur.
        </p>
      ) : reponses.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Aucune reponse de questionnaire enregistree pour ce cas.
        </p>
      ) : (
        <ul className="space-y-2">
          {reponses.map((reponse, index) => (
            <li
              key={`${reponse.questionnaire}-${reponse.item}-${index}`}
              className="rounded-md border bg-muted/30 p-2"
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="text-[0.6rem]">
                  {QUESTIONNAIRE_LABELS[reponse.questionnaire] ??
                    reponse.questionnaire.replace(/_/g, " ")}
                </Badge>
                <span className="font-mono text-[0.6rem] text-muted-foreground">
                  {reponse.item}
                </span>
                {reponse.repondu_a && (
                  <span className="ml-auto text-[0.6rem] tabular-nums text-muted-foreground">
                    {heure(reponse.repondu_a)}
                  </span>
                )}
              </div>
              {reponse.libelle && (
                <p className="mt-1 break-words text-xs text-muted-foreground">
                  {reponse.libelle}
                </p>
              )}
              <p className="mt-1 break-words text-sm font-medium">
                {reponse.valeur || "Sans reponse"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  VueDossier                                                         */
/* ------------------------------------------------------------------ */

export default function VueDossier({ dossier, onFermer }: VueDossierProps) {
  const [propositionCiblee, setPropositionCiblee] = useState<string | null>(
    null,
  );

  const cible =
    dossier.propositions.find(
      (proposition) => proposition.id === propositionCiblee,
    ) ?? null;
  const nbDecidees = dossier.propositions.filter(
    (proposition) => proposition.decision !== null,
  ).length;
  const nbHatives = dossier.propositions.filter(
    (proposition) => proposition.hative,
  ).length;
  const nbAncrees = dossier.propositions.filter(
    (proposition) => proposition.empan_extrait !== "",
  ).length;

  return (
    <div className="space-y-4">
      {/* En-tete : deux lignes, pour qu'un organe long ne soit jamais tronque
          par les identifiants sur un ecran etroit. */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onFermer}>
            <ArrowLeft className="h-3.5 w-3.5" />
            Retour aux cas
          </Button>
          <span
            className="ml-auto truncate font-mono text-[0.65rem] text-muted-foreground"
            title={`${dossier.praticien_id} · ${dossier.id}`}
          >
            {dossier.praticien_id.slice(0, 8)} · {dossier.id.slice(0, 8)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="min-w-0 truncate text-base font-bold first-letter:uppercase">
            {nomOrgane(dossier.organe)}
          </h2>
          {dossier.abandonne ? (
            <Badge variant="destructive" className="text-[0.65rem]">
              Abandonne
            </Badge>
          ) : dossier.cr_valide === null ? (
            <Badge variant="warning" className="gap-1 text-[0.65rem]">
              <AlertTriangle className="h-3 w-3" />
              Non valide
            </Badge>
          ) : (
            <Badge
              variant="success"
              className="gap-1 text-[0.65rem] text-success"
            >
              <CheckCircle2 className="h-3 w-3" />
              Valide
            </Badge>
          )}
        </div>
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

      {/* La comparaison d'abord : c'est ce qu'on vient chercher. */}
      <ComparaisonCr
        crPropose={dossier.cr_propose}
        crValide={dossier.cr_valide}
        caracteresModifies={dossier.caracteres_modifies}
      />

      <TranscriptionAncree
        transcription={dossier.transcription}
        debut={cible?.empan_debut ?? null}
        fin={cible?.empan_fin ?? null}
        ancrable={dossier.transcription.length > 0 && nbAncrees > 0}
      />

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

      <BlocTemps temps={dossier.temps} pauses={dossier.pauses} />

      <BlocPrelevements
        prelevements={dossier.prelevements}
        nbDetecte={dossier.nb_prelevements_detecte}
        nbCorrige={dossier.nb_prelevements_corrige}
      />

      <BlocQuestionnaires reponses={dossier.questionnaires} />
    </div>
  );
}
