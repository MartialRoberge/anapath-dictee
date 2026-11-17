// Signalement utilisateur : un seul circuit (POST /v3/signalements). Le message est libre mais ne doit jamais contenir de donnée patient ;
// le serveur le refuse (422) et renvoie un message en français que l'on affiche tel quel.
import { API_BASE } from "@/lib/config";
import { ApiError, modeDemo, TOKEN_KEY } from "./api";

export const CATEGORIES_SIGNALEMENT = [
  ["dysfonctionnement", "Dysfonctionnement"],
  ["erreur_projet", "Erreur du projet"],
  ["amelioration", "Amélioration"],
  ["non_conformite", "Non-conformité"],
] as const;
export type CategorieSignalement = (typeof CATEGORIES_SIGNALEMENT)[number][0];

export const MESSAGE_MAX = 1000;
export const AVERTISSEMENT_PATIENT = "N'indiquez aucune donnée patient";
export const MESSAGE_DOUBLON = "Déjà signalé, merci";
export const MESSAGE_ENVOYE = "Signalement envoyé, merci";

/** Version de l'application jointe automatiquement aux signalements (motif serveur : [A-Za-z0-9_.+-]{1,60}). */
export const VERSION_APP: string = (import.meta.env?.VITE_APP_VERSION as string | undefined) ?? "3.0.0";

export interface SignalementEnvoye { id: string; doublon_de: string | null }
export interface SignalementCorps { categorie: CategorieSignalement; message: string; projet_id?: string; ecran?: string }

export async function envoyerSignalement(c: SignalementCorps): Promise<SignalementEnvoye> {
  if (modeDemo()) return { id: "demo", doublon_de: null };
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) h.Authorization = `Bearer ${t}`;
  const corps: Record<string, string> = { categorie: c.categorie, message: c.message.trim(), version_app: VERSION_APP };
  if (c.projet_id && /^[A-Za-z0-9_-]{1,64}$/.test(c.projet_id)) corps.projet_id = c.projet_id;
  if (c.ecran && /^[A-Za-z0-9_./:-]{1,60}$/.test(c.ecran)) corps.ecran = c.ecran;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v3/signalements`, { method: "POST", headers: h, body: JSON.stringify(corps) });
  } catch {
    throw new ApiError("Connexion impossible. Réessayez.", 0);
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    const d = (j as { detail?: unknown })?.detail;
    // Le message du serveur (422 donnée patient, 429 limite) est affiché tel quel.
    const msg = typeof d === "string" ? d
      : res.status === 401 ? "Votre session a expiré. Reconnectez-vous."
      : res.status === 429 ? "Trop de signalements à la suite. Patientez une minute."
      : res.status === 422 ? "Le message est refusé : vérifiez son contenu."
      : `Erreur ${res.status}.`;
    throw new ApiError(msg, res.status);
  }
  return (await res.json()) as SignalementEnvoye;
}
