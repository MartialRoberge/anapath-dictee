import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Info, RefreshCw, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_BASE } from "@/lib/config";
import { getAuthHeaders } from "@/services/api";
import ItemQuestionnaire from "./ItemQuestionnaire";
import type { ItemDefinition, TypeItem } from "./ItemQuestionnaire";

/* ------------------------------------------------------------------ */
/*  Contrat                                                            */
/* ------------------------------------------------------------------ */

export interface QuestionnaireProps {
  nom: "inclusion" | "par_cas" | "fin_etude";
  dossierId?: string;
  onTermine: () => void;
  onIndisponible?: (raison: string) => void;
}

interface DefinitionQuestionnaire {
  nom: string;
  titre: string;
  duree_estimee_s: number;
  items: ItemDefinition[];
}

type Etat =
  | { phase: "chargement" }
  | { phase: "pret"; def: DefinitionQuestionnaire }
  | { phase: "indisponible"; detail: string }
  | { phase: "erreur"; raison: string };

/* ------------------------------------------------------------------ */
/*  Regles de l'etude                                                  */
/* ------------------------------------------------------------------ */

/** Le questionnaire par cas est celui des 40 secondes annoncees : il est rendu
 *  resserre pour tenir d'un coup. Une promesse de 40 secondes qui en prend deux
 *  minutes fait abandonner l'etude. */
const QUESTIONNAIRE_DENSE = "par_cas";

/** La mesure d'omission : un oubli ne laisse aucune trace dans la telemetrie,
 *  cet item est la seule source qui puisse la produire. D'ou son poids visuel. */
const ITEM_OMISSION = "par_cas_00";

/** oui_non ne porte pas d'options cote backend : le frontend fixe la paire.
 *  « Non » vient en premier parce que depend_de traite la premiere option comme
 *  celle qui ne declenche pas la relance (« Lequel ? » ne suit que « Oui »). */
const OPTIONS_OUI_NON = ["Non", "Oui"];

/** Types qui respirent mal dans une demi-colonne. */
const TYPES_PLEINE_LARGEUR: ReadonlySet<TypeItem> = new Set<TypeItem>([
  "classement",
  "echelle_10",
  "choix_multiple",
]);

const AUCUN_ITEM: ItemDefinition[] = [];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function ancre(nom: string, idItem: string): string {
  return `q-${nom}-${idItem}`;
}

async function lireDetail(reponse: Response, defaut: string): Promise<string> {
  const corps: unknown = await reponse.json().catch(() => null);
  if (corps && typeof corps === "object" && "detail" in corps) {
    const detail = (corps as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return defaut;
}

function completer(item: ItemDefinition): ItemDefinition {
  if (item.type !== "oui_non" || item.options.length > 0) return item;
  return { ...item, options: [...OPTIONS_OUI_NON] };
}

/** Un item conditionnel ne s'affiche que si celui dont il depend a recu une
 *  reponse AUTRE que sa premiere option : inutile de demander « lequel ? » a
 *  quelqu'un qui vient de repondre « jamais ». */
function estVisible(
  item: ItemDefinition,
  parId: ReadonlyMap<string, ItemDefinition>,
  reponses: Readonly<Record<string, string>>,
): boolean {
  if (!item.depend_de) return true;
  const parent = parId.get(item.depend_de);
  // Dependance introuvable : on prefere poser la question que l'escamoter.
  if (!parent) return true;
  const reponse = reponses[item.depend_de] ?? "";
  if (!reponse) return false;
  return reponse !== (parent.options[0] ?? "");
}

/** Amener le praticien sur l'item : lui dire ce qui manque ne suffit pas s'il
 *  doit le retrouver au milieu de quinze questions. */
function amenerA(idAncre: string): void {
  const cible = document.getElementById(idAncre);
  if (!cible) return;
  cible.scrollIntoView({ behavior: "smooth", block: "center" });
  cible
    .querySelector<HTMLElement>("input, textarea, button")
    ?.focus({ preventScroll: true });
}

/** Le questionnaire annonce sa duree : le praticien decide s'il a le temps. */
function dureeLisible(secondes: number): string {
  if (secondes < 90) return `environ ${secondes} secondes`;
  return `environ ${Math.round(secondes / 60)} minutes`;
}

function pluriel(n: number): string {
  return n > 1 ? "s" : "";
}

/* ------------------------------------------------------------------ */
/*  Questionnaire                                                      */
/* ------------------------------------------------------------------ */

export default function Questionnaire({
  nom,
  dossierId,
  onTermine,
  onIndisponible,
}: QuestionnaireProps) {
  const [etat, setEtat] = useState<Etat>({ phase: "chargement" });
  const [reponses, setReponses] = useState<Record<string, string>>({});
  const [verifie, setVerifie] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  // Les reponses s'ajoutent ligne a ligne cote base : un second envoi les
  // dupliquerait. Une fois parti, le bouton ne repart pas.
  const [envoye, setEnvoye] = useState(false);
  const [erreurEnvoi, setErreurEnvoi] = useState<string | null>(null);
  const [tentative, setTentative] = useState(0);

  // Changer de questionnaire remet le formulaire a zero. Sans cela, un parent
  // qui reutilise le composant reporterait les reponses d'un questionnaire sur
  // le suivant — des reponses attribuees au mauvais instrument.
  const [nomCharge, setNomCharge] = useState(nom);
  if (nom !== nomCharge) {
    setNomCharge(nom);
    setReponses({});
    setVerifie(false);
    setEnvoye(false);
    setErreurEnvoi(null);
  }

  // Le parent n'a pas a memoiser ses callbacks : on passe par une ref pour que
  // le questionnaire ne se recharge pas a chaque rendu du parent.
  const indisponibleRef = useRef(onIndisponible);
  useEffect(() => {
    indisponibleRef.current = onIndisponible;
  }, [onIndisponible]);

  useEffect(() => {
    let annule = false;

    const charger = async () => {
      try {
        const reponse = await fetch(
          `${API_BASE}/etude/questionnaires/${nom}`,
          { headers: getAuthHeaders() },
        );
        if (annule) return;
        // 409 : les libelles publies ne sont pas encore en place. C'est voulu,
        // pas une panne — et surtout pas une invitation a en fabriquer.
        if (reponse.status === 409) {
          const detail = await lireDetail(
            reponse,
            "Questionnaire pas encore publie.",
          );
          if (annule) return;
          setEtat({ phase: "indisponible", detail });
          indisponibleRef.current?.(detail);
          return;
        }
        if (!reponse.ok) {
          throw new Error(
            await lireDetail(reponse, `Erreur HTTP ${reponse.status}`),
          );
        }
        const def = (await reponse.json()) as DefinitionQuestionnaire;
        if (annule) return;
        setEtat({
          phase: "pret",
          def: { ...def, items: def.items.map(completer) },
        });
      } catch (erreur) {
        if (annule) return;
        const raison =
          erreur instanceof Error
            ? erreur.message
            : "Questionnaire injoignable.";
        setEtat({ phase: "erreur", raison });
        indisponibleRef.current?.(raison);
      }
    };

    charger();
    return () => {
      annule = true;
    };
  }, [nom, tentative]);

  const items = etat.phase === "pret" ? etat.def.items : AUCUN_ITEM;

  const parId = useMemo(
    () => new Map(items.map((item) => [item.id, item])),
    [items],
  );

  const visibles = useMemo(
    () => items.filter((item) => estVisible(item, parId, reponses)),
    [items, parId, reponses],
  );

  const oublis = useMemo(
    () =>
      visibles.filter(
        (item) => item.obligatoire && !(reponses[item.id] ?? "").trim(),
      ),
    [visibles, reponses],
  );

  const repondus = visibles.filter((item) =>
    (reponses[item.id] ?? "").trim(),
  ).length;

  const definir = useCallback((idItem: string, valeur: string) => {
    setReponses((prev) => ({ ...prev, [idItem]: valeur }));
  }, []);

  const envoyer = useCallback(async () => {
    setVerifie(true);
    if (oublis.length > 0) {
      amenerA(ancre(nom, oublis[0].id));
      return;
    }
    setEnvoi(true);
    setErreurEnvoi(null);
    try {
      // Seules les reponses des items VISIBLES partent : une reponse devenue
      // sans objet parce que l'item s'est masque fausserait le depouillement.
      const retenues: Record<string, string> = {};
      for (const item of visibles) {
        const valeur = (reponses[item.id] ?? "").trim();
        if (valeur) retenues[item.id] = valeur;
      }
      const reponse = await fetch(`${API_BASE}/etude/questionnaires`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          questionnaire: nom,
          reponses: retenues,
          dossier_id: dossierId ?? null,
        }),
      });
      if (!reponse.ok) {
        throw new Error(
          await lireDetail(reponse, `Erreur HTTP ${reponse.status}`),
        );
      }
      setEnvoye(true);
      setEnvoi(false);
      onTermine();
    } catch (erreur) {
      setErreurEnvoi(
        erreur instanceof Error ? erreur.message : "Envoi impossible.",
      );
      setEnvoi(false);
    }
  }, [dossierId, nom, onTermine, oublis, reponses, visibles]);

  if (etat.phase === "chargement") {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground">
        <div className="h-6 w-6 animate-spin-slow rounded-full border-[2.5px] border-muted border-t-primary" />
        <span className="text-sm font-medium">Chargement du questionnaire...</span>
      </div>
    );
  }

  if (etat.phase === "indisponible") {
    return (
      <div className="mx-auto flex w-full max-w-[640px] flex-col gap-3 rounded-lg border border-warning/30 bg-warning/5 p-4">
        <div className="flex items-start gap-2.5">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0 space-y-1.5">
            <p className="text-sm font-semibold text-foreground">
              Questionnaire pas encore disponible
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {etat.detail}
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Ce n'est pas une panne. Les items concernes doivent etre repris mot
              pour mot depuis leur source publiee : reformules, ils produiraient
              un score qui ne se compare a rien. Mieux vaut ne pas les poser.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={onTermine}>
            Continuer
          </Button>
        </div>
      </div>
    );
  }

  if (etat.phase === "erreur") {
    return (
      <div className="mx-auto flex w-full max-w-[640px] flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <div className="flex items-start gap-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold text-foreground">
              Questionnaire indisponible
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {etat.raison}
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setTentative((t) => t + 1)}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Reessayer
          </Button>
        </div>
      </div>
    );
  }

  const dense = nom === QUESTIONNAIRE_DENSE;
  const manquants = verifie ? oublis : AUCUN_ITEM;

  return (
    <section
      className={cn(
        "flex min-w-0 flex-col",
        dense ? "gap-3" : "mx-auto w-full max-w-[720px] gap-4",
      )}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
          <h2
            className={cn(
              "font-bold tracking-tight",
              dense ? "text-sm" : "text-base",
            )}
          >
            {etat.def.titre}
          </h2>
          <p className="text-xs text-muted-foreground">
            {visibles.length} question{pluriel(visibles.length)} &middot;{" "}
            {dureeLisible(etat.def.duree_estimee_s)}
          </p>
        </div>
        <Badge variant="secondary" className="shrink-0 text-[0.7rem]">
          {repondus} / {visibles.length}
        </Badge>
      </header>

      {!dense && visibles.length > 0 && (
        <div className="h-1.5 w-full rounded-full bg-muted">
          <div
            className="h-1.5 rounded-full bg-primary transition-all duration-500"
            style={{ width: `${(repondus / visibles.length) * 100}%` }}
          />
        </div>
      )}

      {manquants.length > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {manquants.length} reponse{pluriel(manquants.length)} obligatoire
            {pluriel(manquants.length)} manquante{pluriel(manquants.length)}
          </p>
          <ul className="mt-1.5 space-y-1">
            {manquants.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => amenerA(ancre(nom, item.id))}
                  className="rounded text-left text-xs text-muted-foreground underline underline-offset-2 transition-colors hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  {item.libelle}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div
        className={cn("grid min-w-0 gap-3", dense && "gap-2 md:grid-cols-2")}
      >
        {visibles.map((item) => {
          const accentue = item.id === ITEM_OMISSION;
          return (
            <ItemQuestionnaire
              key={item.id}
              item={item}
              ancreId={ancre(nom, item.id)}
              valeur={reponses[item.id] ?? ""}
              onChange={(valeur) => definir(item.id, valeur)}
              manquant={manquants.some((oubli) => oubli.id === item.id)}
              dense={dense}
              accentue={accentue}
              className={cn(
                dense &&
                  (accentue || TYPES_PLEINE_LARGEUR.has(item.type)) &&
                  "md:col-span-2",
              )}
            />
          );
        })}
      </div>

      {erreurEnvoi && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="min-w-0 break-words">{erreurEnvoi}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
        <p className="min-w-0 text-xs text-muted-foreground">
          {oublis.length > 0
            ? `${oublis.length} reponse${pluriel(oublis.length)} obligatoire${pluriel(oublis.length)} attendue${pluriel(oublis.length)}`
            : ""}
        </p>
        <Button onClick={envoyer} disabled={envoi || envoye}>
          {envoi && (
            <span className="h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground" />
          )}
          {!envoi && envoye && <Check className="h-3.5 w-3.5" />}
          {!envoi && !envoye && <Send className="h-3.5 w-3.5" />}
          {envoye ? "Reponses enregistrees" : envoi ? "Envoi..." : "Valider mes reponses"}
        </Button>
      </div>
    </section>
  );
}
