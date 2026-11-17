// Client telemetrie v3 : file en memoire, envoi par lots, echec silencieux, jamais bloquant.
// Regle absolue : aucun texte libre, aucune donnee medicale, aucun identifiant patient.
// Seuls des types d'evenements et des champs whitelistes (nombres, booleens, enums, ids techniques).
// Le serveur revalide strictement (backend/telemetrie/whitelist.py) ; ce filtre client evite
// simplement d'emettre ce qui sera rejete et protege des erreurs d'appel.
import { API_BASE } from "@/lib/config";

export type TelemetryType =
  | "projet_genere" | "projet_itere" | "element_edite" | "trou_comble" | "trou_ignore"
  | "alerte_resolue" | "alerte_ignoree" | "correction_acceptee" | "correction_rejetee"
  | "code_copie" | "code_modifie" | "source_consultee" | "feedback" | "export" | "session_temps" | "erreur";

export type TelemetryPayload = Record<string, number | boolean | string | string[] | undefined>;

/** Champs autorises par type (miroir de la whitelist serveur). */
const CHAMPS: Record<TelemetryType, readonly string[]> = {
  projet_genere: ["duree_ms", "niveau_service", "organes", "contexte_lesionnel", "prelevement", "nb_elements", "nb_trous", "nb_alertes", "nb_corrections", "confiance_moyenne"],
  projet_itere: ["duree_ms", "nb_tours"],
  element_edite: ["element_type", "statut", "niveau", "champ_id", "delta_caracteres"],
  trou_comble: ["champ_id", "via", "delai_ms", "obligatoire"],
  trou_ignore: ["champ_id", "obligatoire"],
  alerte_resolue: ["alerte_type", "gravite", "delai_ms"],
  alerte_ignoree: ["alerte_type", "gravite", "delai_ms"],
  correction_acceptee: ["confiance", "delai_ms"],
  correction_rejetee: ["confiance", "delai_ms"],
  code_copie: ["systeme", "statut"],
  code_modifie: ["systeme", "statut"],
  source_consultee: ["source_kind"],
  feedback: ["sens", "motifs"],
  export: ["format", "duree_depuis_generation_ms", "nb_retouches", "sans_retouche"],
  session_temps: ["duree_s"],
  erreur: ["code", "etape", "niveau_service"],
};

/** Identifiant technique : jamais d'espace ni de ponctuation, donc aucune phrase. */
const ID_RE = /^[A-Za-z0-9_]{1,48}$/;
const PROJET_RE = /^[A-Za-z0-9_-]{1,64}$/;

interface Evenement { type: TelemetryType; payload: Record<string, unknown>; projet_id?: string }

const TAILLE_LOT = 20;
const DELAI_MS = 10_000;
const MAX_FILE = 200;
let file: Evenement[] = [];
let minuteur: ReturnType<typeof setTimeout> | null = null;
let ecouteursPoses = false;

function valeurOk(v: unknown): boolean {
  if (typeof v === "number") return Number.isFinite(v);
  if (typeof v === "boolean") return true;
  if (typeof v === "string") return ID_RE.test(v);
  if (Array.isArray(v)) return v.length <= 20 && v.every((x) => typeof x === "string" && ID_RE.test(x));
  return false;
}

/** Retourne l'evenement nettoye, ou null si une valeur/cle n'est pas conforme. Exporte pour les tests. */
export function assainir(type: TelemetryType, payload: TelemetryPayload, projetId?: string): Evenement | null {
  const autorises = CHAMPS[type];
  if (!autorises) return null;
  const propre: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(payload)) {
    if (v === undefined) continue;
    if (!autorises.includes(k) || !valeurOk(v)) return null;
    propre[k] = v;
  }
  if (projetId !== undefined && !PROJET_RE.test(projetId)) return null;
  return { type, payload: propre, projet_id: projetId };
}

function jeton(): string | null {
  try { return localStorage.getItem("iris_access_token"); } catch { return null; }
}

/** Envoie la file. `keepalive` permet l'envoi pendant la fermeture de la page. Echec silencieux. */
function vider(): void {
  if (minuteur) { clearTimeout(minuteur); minuteur = null; }
  const token = jeton();
  if (!file.length) return;
  if (!token) { file = []; return; } // pas de session : rien n'est envoye ni conserve
  const lot = file.splice(0, 50);
  try {
    void fetch(`${API_BASE}/v3/telemetrie/evenements`, {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ evenements: lot }),
    }).catch(() => undefined);
  } catch { /* jamais bloquant */ }
  if (file.length) vider();
}

function poserEcouteurs(): void {
  if (ecouteursPoses || typeof window === "undefined") return;
  ecouteursPoses = true;
  window.addEventListener("pagehide", vider);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") vider(); });
}

export function track(type: TelemetryType, payload: TelemetryPayload = {}, projetId?: string): void {
  try {
    const ev = assainir(type, payload, projetId);
    if (!ev) return;
    poserEcouteurs();
    if (file.length >= MAX_FILE) file.shift();
    file.push(ev);
    if (file.length >= TAILLE_LOT) vider();
    else if (!minuteur) minuteur = setTimeout(vider, DELAI_MS);
  } catch { /* la telemetrie ne doit jamais casser l'application */ }
}

/** Force l'envoi immediat (deconnexion, tests). */
export const viderTelemetrie = vider;
