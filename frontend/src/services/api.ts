const API_BASE = import.meta.env.VITE_API_URL ?? "";

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("iris_access_token");
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/* ------------------------------------------------------------------ */
/*  Types — miroir du backend v3                                       */
/* ------------------------------------------------------------------ */

export interface TranscriptionResult {
  raw_transcription: string;
}

export interface DonneeManquante {
  champ: string;
  description: string;
  section: string;
  obligatoire: boolean;
}

/** Marker unifie pour le CompletionPanel (adapte depuis DonneeManquante). */
export interface Marker {
  field: string;
  section: string;
  rule_id: string;
  severity: "error" | "warning" | "info";
  message: string;
  auto_filled: boolean;
  auto_filled_value: string;
}

export interface FormatResult {
  formatted_report: string;
  organe_detecte: string;
  markers: Marker[];
}

export type IterationResult = FormatResult;

export interface SectionsResult {
  sections: Record<string, string>;
}

/* ------------------------------------------------------------------ */
/*  Conversion v3 -> Marker unifie                                     */
/* ------------------------------------------------------------------ */

function donneeToMarker(d: DonneeManquante): Marker {
  return {
    field: d.champ,
    section: d.section as Marker["section"],
    rule_id: `v3.${d.section}.${d.champ}`,
    severity: d.obligatoire ? "error" : "warning",
    message: d.description,
    auto_filled: false,
    auto_filled_value: "",
  };
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const DEFAULT_TIMEOUT_MS = 120_000;

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", ...getAuthHeaders() };
}

function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() =>
    clearTimeout(timer),
  );
}

/* ------------------------------------------------------------------ */
/*  Endpoints                                                          */
/* ------------------------------------------------------------------ */

export async function transcribeAudio(
  audioBlob: Blob,
  filename: string = "recording.webm",
): Promise<string> {
  const formData = new FormData();
  formData.append("file", audioBlob, filename);

  const response = await fetch(`${API_BASE}/transcribe`, {
    method: "POST",
    headers: { ...getAuthHeaders() },
    body: formData,
  });

  const data = await handleResponse<TranscriptionResult>(response);
  return data.raw_transcription;
}

interface V3FormatResponse {
  formatted_report: string;
  organe_detecte: string;
  donnees_manquantes: DonneeManquante[];
}

export async function formatTranscription(
  rawText: string,
  rapportPrecedent?: string,
): Promise<FormatResult> {
  const body: Record<string, string> = { raw_text: rawText };
  if (rapportPrecedent) body.rapport_precedent = rapportPrecedent;

  const response = await fetchWithTimeout(`${API_BASE}/format`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  const v3 = await handleResponse<V3FormatResponse>(response);
  return {
    formatted_report: v3.formatted_report,
    organe_detecte: v3.organe_detecte,
    markers: v3.donnees_manquantes.map(donneeToMarker),
  };
}

interface V3IterationResponse {
  formatted_report: string;
  organe_detecte: string;
  donnees_manquantes: DonneeManquante[];
}

export async function iterateReport(
  rapportActuel: string,
  nouveauTranscript: string,
): Promise<IterationResult> {
  const response = await fetchWithTimeout(`${API_BASE}/iterate`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      rapport_actuel: rapportActuel,
      nouveau_transcript: nouveauTranscript,
    }),
  });

  const v3 = await handleResponse<V3IterationResponse>(response);
  return {
    formatted_report: v3.formatted_report,
    organe_detecte: v3.organe_detecte,
    markers: v3.donnees_manquantes.map(donneeToMarker),
  };
}

export async function getSections(
  formattedReport: string,
): Promise<SectionsResult> {
  const response = await fetch(`${API_BASE}/sections`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ formatted_report: formattedReport }),
  });

  return handleResponse<SectionsResult>(response);
}

export async function exportDocx(
  formattedReport: string,
  title?: string,
): Promise<Blob> {
  const body: Record<string, string> = { formatted_report: formattedReport };
  if (title) body.title = title;

  const response = await fetch(`${API_BASE}/export`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }

  return response.blob();
}
