// Accès à l'API d'administration (contrat : docs/v3/11_contrat_admin.md). Même jeton que le reste de l'app.
import { API_BASE } from "@/lib/config";
import { TOKEN_KEY } from "../lib/api";
import { telecharger } from "../lib/api";
import { apiDemo } from "./demo";
import type { AdminApi, FiltresRetours, Periode } from "./types";

export type FetchAuth = (chemin: string, init?: RequestInit) => Promise<Response>;

export const fetchParDefaut: FetchAuth = (chemin, init = {}) => {
  const h: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) h.Authorization = `Bearer ${t}`;
  if (init.body && !h["Content-Type"]) h["Content-Type"] = "application/json";
  return fetch(`${API_BASE}${chemin}`, { ...init, headers: h });
};

/** Les erreurs de l'API sont `{detail: "<message français>"}` ; `detail` peut être une liste (422 de paramètre). */
async function lire<T>(r: Response): Promise<T> {
  if (r.ok) return (await r.json()) as T;
  const corps = await r.json().catch(() => ({}));
  const d = (corps as { detail?: unknown }).detail;
  if (r.status === 401) throw new Error("Votre session a expiré. Reconnectez-vous.");
  if (r.status === 403) throw new Error("Accès réservé aux administrateurs.");
  if (typeof d === "string") throw new Error(d);
  throw new Error(`Erreur ${r.status}.`);
}

/** La télémétrie n'accepte que 7j, 30j et 90j : « tout » se lit sur 90 jours. */
export const periodeTelemetrie = (p: Periode): "7j" | "30j" | "90j" => (p === "tout" ? "90j" : p);

export function creerApi(f: FetchAuth = fetchParDefaut): AdminApi {
  const get = <T,>(c: string) => f(c).then((r) => lire<T>(r));
  return {
    vueEnsemble: (p) => get(`/v3/admin/vue-ensemble?periode=${p}`),
    recommandations: (p) => get<{ recommandations: never[] }>(`/v3/admin/telemetrie/recommandations?periode=${periodeTelemetrie(p)}`).then((r) => r.recommandations),
    syntheseTelemetrie: (p) => get(`/v3/admin/telemetrie/synthese?periode=${periodeTelemetrie(p)}`),
    retours: (x: FiltresRetours) => {
      const q = new URLSearchParams({ page: String(x.page), par_page: "25" });
      if (x.origine) q.set("origine", x.origine);
      if (x.categorie) q.set("categorie", x.categorie);
      if (x.statut) q.set("statut", x.statut);
      return get(`/v3/admin/retours?${q}`);
    },
    majSignalement: (id, corps) => f(`/v3/admin/signalements/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(corps) }).then((r) => lire(r)),
    utilisateurs: () => get("/v3/admin/utilisateurs"),
    habilitation: (id, habilite) => f(`/v3/conformite/habilitations/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ habilite }) }).then((r) => lire(r)),
    etude: () => get("/v3/admin/etude"),
    dossiersEtude: () => get("/admin/etude/dossiers"),
    exporter: async (chemin, nom) => {
      const r = await f(chemin);
      if (!r.ok) await lire(r);
      telecharger(await r.blob(), nom);
    },
    sante: () => get("/v3/admin/sante"),
  };
}

export const choisirApi = (demo: boolean): AdminApi => (demo ? apiDemo : creerApi());
