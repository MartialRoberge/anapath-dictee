const API_BASE = import.meta.env.VITE_API_URL ?? "";

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem("iris_access_token");
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/* ------------------------------------------------------------------ */
/*  Types v4 — miroir des schemas.py backend                           */
/* ------------------------------------------------------------------ */

export interface TranscriptionResult {
  raw_transcription: string;
}

export type MarkerSection =
  | "titre"
  | "renseignements_cliniques"
  | "macroscopie"
  | "microscopie"
  | "immunomarquage"
  | "biologie_moleculaire"
  | "conclusion";

export interface Marker {
  field: string;
  section: MarkerSection;
  rule_id: string;
  severity: "error" | "warning" | "info";
  message: string;
  auto_filled: boolean;
  auto_filled_value: string;
}

export interface IhcRow {
  anticorps: string;
  resultat: string;
  temoin: string;
}

export interface IhcTable {
  phrase_introduction: string;
  lignes: IhcRow[];
}

export interface Prelevement {
  numero: number;
  titre_court: string;
  macroscopie: string;
  microscopie: string;
  immunomarquage: IhcTable | null;
  biologie_moleculaire: string;
}

export interface CRDocument {
  titre: string;
  renseignements_cliniques: string;
  prelevements: Prelevement[];
  conclusion: string;
  ptnm: string;
  commentaire_final: string;
  code_adicap: string;
  codes_snomed: string[];
}

export interface ClassificationCandidate {
  organe: string;
  sous_type: string;
  est_carcinologique: boolean;
  diagnostic_presume: string;
  confidence: number;
}

export interface Classification {
  top: ClassificationCandidate;
  alternative: ClassificationCandidate | null;
  transcript_normalise: string;
  confidence_threshold: number;
}

export interface FormatResult {
  trace_id: string;
  formatted_report: string;
  document: CRDocument;
  classification: Classification;
  markers: Marker[];
}

export type IterationResult = FormatResult;

export interface SectionsResult {
  sections: Record<string, string>;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const DEFAULT_TIMEOUT_MS = 120_000; // 2 min pour les appels Claude

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

export async function formatTranscription(
  rawText: string,
): Promise<FormatResult> {
  const body: Record<string, string> = { raw_text: rawText };

  const response = await fetchWithTimeout(`${API_BASE}/format`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

  return handleResponse<FormatResult>(response);
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

  return handleResponse<IterationResult>(response);
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
