import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useSoundFeedback } from "../hooks/useSoundFeedback";
import {
  transcribeAudio,
  formatTranscription,
  iterateReport,
} from "../services/api";
import type { DonneeManquante } from "../services/api";
import { useState, useCallback, useRef, useEffect } from "react";
import Pipeline from "./Pipeline";
import type { PipelineStep } from "./Pipeline";

const ACCEPTED_EXTENSIONS = ".mp3,.mp4,.m4a,.mov,.wav,.webm,.ogg,.flac,.aac";
const ACCEPTED_MIME =
  "audio/*,video/mp4,video/quicktime,video/x-m4v";

interface Props {
  rawTranscription: string | null;
  report: string | null;
  onTranscription: (raw: string) => void;
  onFormatted: (
    report: string,
    organe: string,
    manquantes: DonneeManquante[]
  ) => void;
  onReset: () => void;
  onRawChange: (raw: string) => void;
  onReformat: (text: string) => void;
  reformatting: boolean;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function truncateFilename(name: string, max: number = 28): string {
  if (name.length <= max) return name;
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  return name.slice(0, max - ext.length - 3) + "..." + ext;
}

export default function RecorderPanel({
  rawTranscription,
  report,
  onTranscription,
  onFormatted,
  onReset,
  onRawChange,
  onReformat,
  reformatting,
}: Props) {
  const { state, audioBlob, duration, startRecording, stopRecording, reset } =
    useAudioRecorder();
  const { playStart, playStop, playStepDone, playAllDone } =
    useSoundFeedback();
  const [step, setStep] = useState<PipelineStep>("idle");
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [droppedFileName, setDroppedFileName] = useState<string | null>(null);
  const holdingRef = useRef(false);
  const processedBlobRef = useRef<Blob | null>(null);
  const reportRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    reportRef.current = report;
  }, [report]);

  const isIteration = report !== null;

  // ─── Shared processing pipeline ───────────────────────────────────
  const processAudioBlob = useCallback(
    async (blob: Blob, filename: string) => {
      setProcessing(true);
      setError(null);
      setDroppedFileName(truncateFilename(filename));
      try {
        setStep("uploading");
        await new Promise((r) => setTimeout(r, 400));
        playStepDone();

        setStep("transcribing");
        const raw = await transcribeAudio(blob, filename);
        onTranscription(raw);
        playStepDone();

        setStep("formatting");
        const currentReport = reportRef.current;

        if (currentReport) {
          const [result] = await Promise.all([
            iterateReport(currentReport, raw),
            new Promise((r) => setTimeout(r, 3000)),
          ]);
          onFormatted(
            result.formatted_report,
            result.organe_detecte,
            result.donnees_manquantes
          );
        } else {
          const [result] = await Promise.all([
            formatTranscription(raw),
            new Promise((r) => setTimeout(r, 3000)),
          ]);
          onFormatted(
            result.formatted_report,
            result.organe_detecte,
            result.donnees_manquantes
          );
        }
        playStepDone();

        await new Promise((r) => setTimeout(r, 1000));
        setStep("done");
        playAllDone();
      } catch (err: unknown) {
        setStep("error");
        setError(err instanceof Error ? err.message : "Erreur inconnue");
      } finally {
        setProcessing(false);
      }
    },
    [onTranscription, onFormatted, playStepDone, playAllDone]
  );

  // ─── Push-to-talk handlers ────────────────────────────────────────
  const handleStart = useCallback(async () => {
    if (processing || holdingRef.current || state === "recording") return;
    holdingRef.current = true;
    playStart();
    setStep("recording");
    setError(null);
    setDroppedFileName(null);
    await startRecording();
  }, [processing, state, startRecording, playStart]);

  const handleStop = useCallback(() => {
    if (!holdingRef.current || state !== "recording") return;
    holdingRef.current = false;
    playStop();
    stopRecording();
  }, [state, stopRecording, playStop]);

  // Keyboard: spacebar push-to-talk
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") return;
      e.preventDefault();
      handleStart();
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") return;
      e.preventDefault();
      handleStop();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [handleStart, handleStop]);

  // Process recorded audio blob (dictaphone only, NOT file drops)
  useEffect(() => {
    if (state !== "stopped" || !audioBlob) return;
    if (processedBlobRef.current === audioBlob) return;
    if (processing) return;
    processedBlobRef.current = audioBlob;
    processAudioBlob(audioBlob, "recording.webm");
  }, [state, audioBlob, processAudioBlob, processing]);

  // ─── File drop / upload handlers ──────────────────────────────────
  const handleFileSelected = useCallback(
    (file: File) => {
      if (processing) return;
      // Ne PAS toucher processedBlobRef — il ne concerne que le dictaphone
      processAudioBlob(file, file.name);
    },
    [processing, processAudioBlob]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFileSelected(file);
    },
    [handleFileSelected]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFileSelected(file);
      // Reset input so same file can be re-selected
      e.target.value = "";
    },
    [handleFileSelected]
  );

  const handleReset = () => {
    reset();
    setError(null);
    setStep("idle");
    setDroppedFileName(null);
    processedBlobRef.current = null;
    onReset();
  };

  const isRecording = state === "recording";

  const recHint = isRecording
    ? formatDuration(duration)
    : processing
      ? "Traitement en cours..."
      : step === "done" && report
        ? "Espace pour completer le compte-rendu"
        : step === "done"
          ? "Espace pour redicter"
          : report
            ? "Espace pour completer le compte-rendu"
            : "Maintenir espace pour dicter";

  return (
    <div className="recorder-panel">
      {/* Push-to-talk zone */}
      <div
        className={`rec-zone ${isRecording ? "rec-zone--active" : ""}`}
        onMouseDown={handleStart}
        onMouseUp={handleStop}
        onMouseLeave={handleStop}
        onTouchStart={handleStart}
        onTouchEnd={handleStop}
      >
        <div className="rec-zone-content">
          <svg
            className="rec-mic-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="9" y="1" width="6" height="11" rx="3" />
            <path d="M5 10a7 7 0 0 0 14 0" />
            <line x1="12" y1="17" x2="12" y2="21" />
            <line x1="8" y1="21" x2="16" y2="21" />
          </svg>
          <span className="rec-hint">{recHint}</span>
        </div>
        {isRecording && <div className="rec-glow" />}
      </div>

      {/* Drop zone for audio files */}
      <div
        className={`drop-zone ${dragOver ? "drop-zone--active" : ""} ${processing ? "drop-zone--disabled" : ""}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !processing && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={`${ACCEPTED_EXTENSIONS},${ACCEPTED_MIME}`}
          onChange={handleFileInputChange}
          className="drop-zone-input"
        />
        <div className="drop-zone-content">
          <svg
            className="drop-zone-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span className="drop-zone-text">
            {droppedFileName
              ? droppedFileName
              : dragOver
                ? "Deposer le fichier"
                : "Glisser un fichier audio ou cliquer"}
          </span>
          <span className="drop-zone-formats">
            MP3, MP4, M4A, MOV, WAV, OGG, FLAC
          </span>
        </div>
      </div>

      <div className="section-label">Workflow</div>
      <Pipeline currentStep={step} isIteration={isIteration} />
      {error && <p className="error-message">{error}</p>}

      <div className="section-label-row">
        <span className="section-label" style={{ margin: 0 }}>
          Transcription brute
        </span>
        {rawTranscription && (
          <button
            className="btn-reformat"
            onClick={() => onReformat(rawTranscription)}
            disabled={reformatting}
            title="Relancer la mise en forme"
          >
            {reformatting ? "..." : "\u21BB"}
          </button>
        )}
      </div>
      <div className="transcription-raw">
        {rawTranscription ? (
          <textarea
            className="raw-textarea"
            value={rawTranscription}
            onChange={(e) => onRawChange(e.target.value)}
          />
        ) : (
          <p className="placeholder-text">
            La transcription apparaitra ici...
          </p>
        )}
      </div>

      {step === "done" && (
        <div className="recorder-bottom-actions">
          <button className="btn btn-new" onClick={handleReset}>
            Nouveau compte-rendu
          </button>
        </div>
      )}
    </div>
  );
}
