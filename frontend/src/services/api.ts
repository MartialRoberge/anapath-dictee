import { API_BASE } from "@/lib/config";

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

/** Reponse brute du backend v3 pour /format et /iterate (structure identique). */
interface V3ReportResponse {
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

  const v3 = await handleResponse<V3ReportResponse>(response);
  return {
    formatted_report: v3.formatted_report,
    organe_detecte: v3.organe_detecte,
    markers: v3.donnees_manquantes.map(donneeToMarker),
  };
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

  const v3 = await handleResponse<V3ReportResponse>(response);
  return {
    formatted_report: v3.formatted_report,
    organe_detecte: v3.organe_detecte,
    markers: v3.donnees_manquantes.map(donneeToMarker),
  };
}

/* ------------------------------------------------------------------ */
/*  Codification ADICAP / SNOMED CT                                    */
/* ------------------------------------------------------------------ */

export interface AdicapResult {
  code: string;
  prelevement: string;
  prelevement_code: string;
  technique: string;
  technique_code: string;
  organe: string;
  organe_code: string;
  lesion: string;
  lesion_code: string;
  confidence?: "haute" | "organe_seul" | "aucune";
  note?: string;
}

export interface SnomedCode {
  code: string;
  display: string;
  system: string;
}

export interface SnomedResult {
  topography: SnomedCode;
  morphology: SnomedCode;
}

export interface CodificationResult {
  adicap: AdicapResult;
  snomed: SnomedResult;
}

export async function getAdicap(
  formattedReport: string,
  organeDetecte: string,
): Promise<AdicapResult> {
  const response = await fetch(`${API_BASE}/adicap`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      formatted_report: formattedReport,
      organe_detecte: organeDetecte,
    }),
  });
  return handleResponse<AdicapResult>(response);
}

export async function getSnomed(
  formattedReport: string,
  organeDetecte: string,
): Promise<SnomedResult> {
  const response = await fetch(`${API_BASE}/snomed`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      formatted_report: formattedReport,
      organe_detecte: organeDetecte,
    }),
  });
  return handleResponse<SnomedResult>(response);
}

/** Recupere ADICAP + SNOMED en parallele. */
export async function getCodification(
  formattedReport: string,
  organeDetecte: string,
): Promise<CodificationResult> {
  const [adicap, snomed] = await Promise.all([
    getAdicap(formattedReport, organeDetecte),
    getSnomed(formattedReport, organeDetecte),
  ]);
  return { adicap, snomed };
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

/* ------------------------------------------------------------------ */
/*  Comptes-rendus sauvegardes (historique, detail, sauvegarde)        */
/* ------------------------------------------------------------------ */

export interface ReportSummary {
  id: string;
  organe_detecte: string;
  status: string;
  created_at: string;
  excerpt: string;
  has_feedback: boolean;
  rating: number | null;
}

export interface ReportDetail {
  id: string;
  raw_transcription: string | null;
  structured_report: string;
  organe_detecte: string;
  feedback_rating: number | null;
}

export interface SavedReport {
  id: string;
}

/** Liste des comptes-rendus de l'utilisateur (historique). */
export async function getReports(): Promise<ReportSummary[]> {
  const response = await fetch(`${API_BASE}/reports`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<ReportSummary[]>(response);
}

/** Detail complet d'un compte-rendu sauvegarde. */
export async function getReport(reportId: string): Promise<ReportDetail> {
  const response = await fetch(`${API_BASE}/reports/${reportId}`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<ReportDetail>(response);
}

/** Sauvegarde (creation) d'un compte-rendu, renvoie son identifiant. */
export async function saveReport(input: {
  raw_transcription: string;
  structured_report: string;
  organe_detecte: string;
}): Promise<SavedReport> {
  const response = await fetch(`${API_BASE}/reports`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(input),
  });
  return handleResponse<SavedReport>(response);
}

/** Envoi d'un feedback (note + commentaire) sur un compte-rendu. */
export async function sendFeedback(
  reportId: string,
  rating: number,
  comment: string,
): Promise<void> {
  await fetch(`${API_BASE}/reports/${reportId}/feedback`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ rating, comment }),
  });
}

/* ------------------------------------------------------------------ */
/*  Administration (tableau de bord)                                   */
/* ------------------------------------------------------------------ */

export interface AdminStats {
  total_reports: number;
  total_users: number;
  average_rating: number | null;
  reports_with_feedback: number;
  reports_with_corrections: number;
  reports_by_organ: Record<string, number>;
}

export interface AdminReport {
  id: string;
  user_name: string;
  user_email: string;
  organe_detecte: string;
  status: string;
  created_at: string;
  rating: number | null;
  feedback_comment: string | null;
  correction_count: number;
}

export interface AdminCorrection {
  report_id: string;
  user_name: string;
  organe: string;
  timestamp: string;
  before_excerpt: string;
  after_excerpt: string;
}

export async function getAdminStats(): Promise<AdminStats> {
  const response = await fetch(`${API_BASE}/admin/stats`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<AdminStats>(response);
}

export async function getAdminReports(): Promise<AdminReport[]> {
  const response = await fetch(`${API_BASE}/admin/reports`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<AdminReport[]>(response);
}

export async function getAdminCorrections(): Promise<AdminCorrection[]> {
  const response = await fetch(`${API_BASE}/admin/corrections`, {
    headers: getAuthHeaders(),
  });
  return handleResponse<AdminCorrection[]>(response);
}
