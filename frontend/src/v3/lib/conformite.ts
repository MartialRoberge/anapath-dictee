// Conformité ISO 15189:2022 côté navigateur : empreinte du texte final, validation.
// Le texte du compte rendu ne quitte jamais le navigateur : seul son SHA-256 est transmis.
import { API_BASE } from "@/lib/config";
import type { Projet } from "../types";
import { ApiError, modeDemo, TOKEN_KEY } from "./api";
import { projetPourExport } from "./exportProjet";
import { alertesOuvertes, etatTrou, estTrou, type ProjetLocal } from "./session";

export const DEROGATIONS = [
  ["information_indisponible_au_dossier", "Information indisponible au dossier"],
  ["trou_non_applicable_au_cas", "Trou non applicable à ce cas"],
  ["alerte_evaluee_non_pertinente", "Alerte évaluée, non pertinente"],
  ["urgence_clinique_documentee_au_laboratoire", "Urgence clinique, documentée au laboratoire"],
  ["autre_motif_trace_par_le_laboratoire", "Autre motif, tracé par le laboratoire"],
] as const;
export type Derogation = (typeof DEROGATIONS)[number][0];

export interface BlocageValidation { alertes_bloquantes: number; trous_obligatoires: number }
export interface ValidationEnregistree { id: string; ts: string; revision: number; empreinte_sha256: string; derogation: string | null }

/** Texte final = titre + éléments dans l'ordre du document, après éditions du praticien. */
export function texteFinal(l: ProjetLocal): string {
  const p = projetPourExport(l);
  return [p.titre, ...p.elements.map((e) => e.texte)].join("\n");
}

export async function sha256Hex(texte: string): Promise<string> {
  const octets = new TextEncoder().encode(texte);
  const sub = globalThis.crypto?.subtle;
  if (!sub) throw new Error("Calcul d'empreinte indisponible sur ce navigateur.");
  const h = new Uint8Array(await sub.digest("SHA-256", octets));
  return Array.from(h, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function blocages(l: ProjetLocal): BlocageValidation {
  return {
    alertes_bloquantes: alertesOuvertes(l).filter((a) => a.gravite === "bloquant").length,
    trous_obligatoires: l.projet.elements.filter((e) => estTrou(e) && e.obligatoire && etatTrou(l, e) === "ouvert").length,
  };
}

export function versionsDe(p: Projet) {
  const t = p.tracabilite ?? {};
  return { pipeline: t.version_pipeline ?? "", kb: t.kb_version ?? "", kb_empreinte_sha256: t.kb_empreinte_sha256 ?? "", modeles: t.modeles ?? {} };
}

async function appel<T>(chemin: string, init: RequestInit = {}): Promise<T> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) h.Authorization = `Bearer ${t}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v3/conformite${chemin}`, { ...init, headers: h });
  } catch {
    throw new ApiError("Connexion impossible. Réessayez.", 0);
  }
  if (!res.ok) {
    const corps = await res.json().catch(() => ({}));
    const d = corps?.detail;
    const msg = typeof d === "string" ? d : typeof d?.message === "string" ? d.message : `Erreur ${res.status}.`;
    const e = new ApiError(msg, res.status);
    (e as ApiError & { blocages?: BlocageValidation }).blocages = d?.blocages;
    throw e;
  }
  return res.json() as Promise<T>;
}

export const moi = (): Promise<{ habilite: boolean; admin: boolean }> =>
  modeDemo() ? Promise.resolve({ habilite: true, admin: false }) : appel("/moi");

const enregistrees = new Set<string>();
/** Journalise la génération (métadonnées uniquement), une fois par projet. Silencieux en cas d'échec. */
export async function enregistrerGeneration(p: Projet): Promise<void> {
  if (modeDemo() || enregistrees.has(p.id)) return;
  enregistrees.add(p.id);
  try {
    await appel("/generations", { method: "POST", body: JSON.stringify({
      projet_id: p.id, versions: versionsDe(p), niveau_service: p.contexte.niveau_service,
      empreinte_dictee_corrigee_sha256: p.tracabilite?.empreinte_dictee_corrigee_sha256 ?? "" }) });
  } catch { enregistrees.delete(p.id); }
}

export async function validerProjet(l: ProjetLocal, empreinte: string, derogation?: Derogation): Promise<ValidationEnregistree> {
  const b = blocages(l);
  if (modeDemo()) return { id: "demo", ts: new Date().toISOString(), revision: 1, empreinte_sha256: empreinte, derogation: derogation ?? null };
  return appel("/validations", { method: "POST", body: JSON.stringify({
    projet_id: l.projet.id, empreinte_sha256: empreinte, nb_alertes_bloquantes_ouvertes: b.alertes_bloquantes,
    nb_trous_ouverts: b.trous_obligatoires, versions: versionsDe(l.projet), ...(derogation ? { derogation } : {}) }) });
}
