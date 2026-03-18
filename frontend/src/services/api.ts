const API_BASE = import.meta.env.VITE_API_URL ?? "";

export interface TranscriptionResult {
  raw_transcription: string;
}

export interface DonneeManquante {
  champ: string;
  description: string;
  section: string;
  obligatoire: boolean;
}

export interface FormatResult {
  formatted_report: string;
  organe_detecte: string;
  donnees_manquantes: DonneeManquante[];
}

export interface IterationResult {
  formatted_report: string;
  organe_detecte: string;
  donnees_manquantes: DonneeManquante[];
}

export interface SectionsResult {
  sections: Record<string, string>;
}

export async function transcribeAudio(
  audioBlob: Blob,
  filename: string = "recording.webm"
): Promise<string> {
  const formData = new FormData();
  formData.append("file", audioBlob, filename);

  const response = await fetch(`${API_BASE}/transcribe`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }

  const data: TranscriptionResult = await response.json();
  return data.raw_transcription;
}

export async function formatTranscription(
  rawText: string,
  rapportPrecedent?: string
): Promise<FormatResult> {
  const body: Record<string, string> = { raw_text: rawText };
  if (rapportPrecedent) {
    body.rapport_precedent = rapportPrecedent;
  }

  const response = await fetch(`${API_BASE}/format`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }

  const data: FormatResult = await response.json();
  return data;
}

export async function iterateReport(
  rapportActuel: string,
  nouveauTranscript: string
): Promise<IterationResult> {
  const response = await fetch(`${API_BASE}/iterate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rapport_actuel: rapportActuel,
      nouveau_transcript: nouveauTranscript,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }

  const data: IterationResult = await response.json();
  return data;
}

export async function getSections(
  formattedReport: string
): Promise<SectionsResult> {
  const response = await fetch(`${API_BASE}/sections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ formatted_report: formattedReport }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }

  const data: SectionsResult = await response.json();
  return data;
}

export async function exportDocx(
  formattedReport: string,
  title?: string
): Promise<Blob> {
  const body: Record<string, string> = { formatted_report: formattedReport };
  if (title) {
    body.title = title;
  }

  const response = await fetch(`${API_BASE}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Erreur inconnue" }));
    throw new Error(error.detail ?? `Erreur HTTP ${response.status}`);
  }

  return response.blob();
}
