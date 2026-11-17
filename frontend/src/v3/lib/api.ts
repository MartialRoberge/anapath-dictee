// Appels API v3. Auth : même jeton que l'app existante (localStorage « iris_access_token »).
// Seuls les appels de génération envoient des données médicales ; rien d'autre ne quitte le navigateur.
import { API_BASE } from "@/lib/config";
import type { Projet, ProjetEvent } from "../types";
import { normaliserDetail, type SourceDetail } from "./sources";
import { demoExporter, demoFlux, demoIterer, demoSource } from "../fixtures/streamDemo";
import { lireFluxSse } from "./sse";
import { projetPourExport } from "./exportProjet";
import type { ProjetLocal } from "./session";

export const TOKEN_KEY = "iris_access_token";

export const modeDemo = (): boolean => {
  try {
    return new URLSearchParams(window.location.search).get("demo") === "1";
  } catch {
    return false;
  }
};

export class ApiError extends Error {
  status: number;
  recuperable: boolean;
  constructor(message: string, status: number, recuperable = true) {
    super(message);
    this.status = status;
    this.recuperable = recuperable;
  }
}

function enTetes(json = true): Record<string, string> {
  const h: Record<string, string> = {};
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) h.Authorization = `Bearer ${t}`;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

function messageHttp(status: number, detail?: string): string {
  if (status === 401) return "Votre session a expiré. Reconnectez-vous.";
  if (status === 413) return "L'enregistrement est trop volumineux.";
  if (status === 429) return "Trop de demandes à la suite. Patientez quelques secondes.";
  if (status >= 500) return "Le service est momentanément indisponible. Votre dictée n'est pas perdue : réessayez.";
  return detail || `Erreur ${status}.`;
}

async function verifier(res: Response): Promise<Response> {
  if (res.ok) return res;
  const corps = await res.json().catch(() => ({}));
  const detail = typeof corps?.detail === "string" ? corps.detail : undefined;
  throw new ApiError(messageHttp(res.status, detail), res.status, res.status !== 401);
}

async function flux(url: string, init: RequestInit, onEvent: (e: ProjetEvent) => void, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${url}`, { ...init, signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Connexion impossible. Vérifiez votre réseau puis réessayez.", 0);
  }
  await verifier(res);
  await lireFluxSse(res, onEvent, signal);
}

/** Dictée collée ou tapée -> flux SSE. */
export function genererTexte(dictee: string, onEvent: (e: ProjetEvent) => void, signal?: AbortSignal) {
  if (modeDemo()) return demoFlux(onEvent, signal);
  return flux("/v3/projets", { method: "POST", headers: enTetes(), body: JSON.stringify({ dictee }) }, onEvent, signal);
}

/** Dictée vocale (MediaRecorder) -> flux SSE. L'audio n'est pas conservé côté serveur. */
export function genererAudio(blob: Blob, onEvent: (e: ProjetEvent) => void, signal?: AbortSignal) {
  if (modeDemo()) return demoFlux(onEvent, signal);
  const fd = new FormData();
  fd.append("audio", blob, blob.type.includes("mp4") ? "dictee.m4a" : "dictee.webm");
  return flux("/v3/projets/audio", { method: "POST", headers: enTetes(false), body: fd }, onEvent, signal);
}

/** Compléter par une dictée d'appoint (texte) : le projet courant est renvoyé avec sa dictée complémentaire. */
export function iterer(projet: Projet, complement: string, onEvent: (e: ProjetEvent) => void, signal?: AbortSignal) {
  if (modeDemo()) return demoIterer(projet, onEvent, signal);
  return flux("/v3/projets/iterer", { method: "POST", headers: enTetes(), body: JSON.stringify({ projet, dictee_complementaire: complement }) }, onEvent, signal);
}

/** Transcription d'un complément vocal (endpoint existant /transcribe). */
export async function transcrire(blob: Blob): Promise<string> {
  if (modeDemo()) return "La taille tumorale sur le fragment le plus important est de vingt-quatre millimètres.";
  const fd = new FormData();
  fd.append("file", blob, blob.type.includes("mp4") ? "complement.m4a" : "complement.webm");
  const res = await verifier(await fetch(`${API_BASE}/transcribe`, { method: "POST", headers: enTetes(false), body: fd }));
  const j = await res.json();
  return String(j.raw_transcription ?? "");
}

/** Fiche de consultation d'une source de la base de connaissances. Lève une erreur si le service ne répond pas : l'appelant garde alors le SourceRef. */
export async function consulterSource(ref: string, signal?: AbortSignal): Promise<SourceDetail> {
  if (modeDemo()) return demoSource(ref);
  const res = await verifier(await fetch(`${API_BASE}/v3/kb/sources/${encodeURIComponent(ref)}`, { headers: enTetes(false), signal }));
  return normaliserDetail(await res.json());
}

/** Export DOCX du projet tel qu'il est à l'écran (éditions et trous comblés appliqués). */
export async function exporterDocx(l: ProjetLocal): Promise<Blob> {
  if (modeDemo()) return demoExporter();
  const res = await verifier(
    await fetch(`${API_BASE}/v3/projets/export/docx`, { method: "POST", headers: enTetes(), body: JSON.stringify(projetPourExport(l)) }),
  );
  return res.blob();
}

export function telecharger(blob: Blob, nom: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nom;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
