// Acces aux endpoints admin telemetrie ; reutilise le jeton de l'application existante.
import { API_BASE } from "@/lib/config";
import { getAuthHeaders } from "@/services/api";
import { recommandationsDemo, syntheseDemo } from "./demo";
import type { Periode, Recommandation, Synthese } from "./types";

/** Fetch authentifie injectable (par defaut : jeton de l'app). */
export type FetchAuth = (chemin: string) => Promise<Response>;

export const fetchParDefaut: FetchAuth = (chemin) => fetch(`${API_BASE}${chemin}`, { headers: getAuthHeaders() });

async function json<T>(r: Response): Promise<T> {
  if (r.status === 403) throw new Error("Acces reserve aux administrateurs.");
  if (!r.ok) throw new Error(`Erreur ${r.status}`);
  return (await r.json()) as T;
}

export async function chargerTout(p: Periode, f: FetchAuth, demo: boolean): Promise<{ s: Synthese; recos: Recommandation[] }> {
  if (demo) return { s: syntheseDemo(p), recos: recommandationsDemo };
  const [s, rec] = await Promise.all([
    f(`/v3/admin/telemetrie/synthese?periode=${p}`).then((r) => json<Synthese>(r)),
    f(`/v3/admin/telemetrie/recommandations?periode=${p}`).then((r) => json<{ recommandations: Recommandation[] }>(r)),
  ]);
  return { s, recos: rec.recommandations };
}
