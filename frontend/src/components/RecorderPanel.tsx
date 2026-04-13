import { useState, useCallback, useRef, useEffect } from "react";
import { Mic, Upload, RotateCcw, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useSoundFeedback } from "../hooks/useSoundFeedback";
import { useToast } from "./Toast";
import {
  transcribeAudio,
  formatTranscription,
  iterateReport,
} from "../services/api";
import type { FormatResult } from "../services/api";
import Pipeline from "./Pipeline";
import type { PipelineStep } from "./Pipeline";

const ACCEPTED_EXTENSIONS = ".mp3,.mp4,.m4a,.mov,.wav,.webm,.ogg,.flac,.aac";
const ACCEPTED_MIME = "audio/*,video/mp4,video/quicktime,video/x-m4v";

interface RecorderPanelProps {
  rawTranscription: string | null;
  report: string | null;
  onTranscription: (raw: string) => void;
  onFormatted: (result: FormatResult) => void;
  onReset: () => void;
  onRawChange: (raw: string) => void;
  onReformat: (text: string) => void;
  reformatting: boolean;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function truncateFilename(name: string, max: number = 28): string {
  if (name.length <= max) return name;
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  return name.slice(0, max - ext.length - 3) + "..." + ext;
}

/* ------------------------------------------------------------------ */
/*  Floating botanical leaves (CSS animated SVG)                       */
/* ------------------------------------------------------------------ */

function FloatingLeaves() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-[0.07]">
      {/* Leaf 1 — slow drift */}
      <svg className="absolute left-[10%] top-[15%] h-12 w-12 animate-float text-iris-600" style={{ animationDuration: "7s" }} viewBox="0 0 40 40" fill="currentColor">
        <path d="M20 2C24 8 34 14 36 22C38 30 28 36 20 38C12 36 2 30 4 22C6 14 16 8 20 2Z" />
        <path d="M20 8V34" stroke="white" strokeWidth="0.5" fill="none" opacity="0.5" />
        <path d="M12 18Q20 22 28 18" stroke="white" strokeWidth="0.3" fill="none" opacity="0.4" />
        <path d="M10 26Q20 28 30 24" stroke="white" strokeWidth="0.3" fill="none" opacity="0.3" />
      </svg>
      {/* Leaf 2 — medium drift */}
      <svg className="absolute right-[15%] top-[30%] h-8 w-8 animate-float text-iris-500" style={{ animationDuration: "9s", animationDelay: "2s" }} viewBox="0 0 40 40" fill="currentColor">
        <path d="M20 4C26 10 32 18 30 26C28 34 22 36 20 36C18 36 12 34 10 26C8 18 14 10 20 4Z" />
        <path d="M20 10V32" stroke="white" strokeWidth="0.4" fill="none" opacity="0.4" />
      </svg>
      {/* Leaf 3 — slow sway */}
      <svg className="absolute left-[60%] top-[60%] h-10 w-10 animate-leaf-sway text-iris-400" style={{ animationDuration: "11s" }} viewBox="0 0 40 40" fill="currentColor">
        <path d="M8 20Q14 6 28 4Q34 16 28 28Q20 36 8 20Z" />
        <path d="M14 16Q22 18 26 12" stroke="white" strokeWidth="0.3" fill="none" opacity="0.3" />
      </svg>
      {/* Petal — gentle float */}
      <svg className="absolute left-[30%] top-[75%] h-6 w-6 animate-float text-violet-400" style={{ animationDuration: "8s", animationDelay: "4s" }} viewBox="0 0 24 24" fill="currentColor">
        <ellipse cx="12" cy="12" rx="5" ry="10" transform="rotate(-30 12 12)" opacity="0.6" />
      </svg>
      {/* Small circles — cell structures */}
      <svg className="absolute right-[25%] top-[10%] h-5 w-5 animate-float text-iris-300" style={{ animationDuration: "10s", animationDelay: "1s" }} viewBox="0 0 20 20">
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1" fill="none" />
        <circle cx="10" cy="10" r="3" fill="currentColor" opacity="0.3" />
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export default function RecorderPanel({
  rawTranscription,
  report,
  onTranscription,
  onFormatted,
  onReset,
  onRawChange,
  onReformat,
  reformatting,
}: RecorderPanelProps) {
  const { state, audioBlob, duration, startRecording, stopRecording, reset } =
    useAudioRecorder();
  const { playStart, playStop, playStepDone, playAllDone } =
    useSoundFeedback();
  const { toast } = useToast();
  const [step, setStep] = useState<PipelineStep>("idle");
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [droppedFileName, setDroppedFileName] = useState<string | null>(null);
  const holdingRef = useRef(false);
  const processedBlobRef = useRef<Blob | null>(null);
  const reportRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    reportRef.current = report;
  }, [report]);

  useEffect(() => {
    if (report === null && rawTranscription === null) {
      // "Nouveau CR" clique — annuler toute requete en vol
      cancelledRef.current = true;
      reset();
      setError(null);
      setStep("idle");
      setProcessing(false);
      setDroppedFileName(null);
      processedBlobRef.current = null;
    }
  }, [report, rawTranscription, reset]);

  const isIteration = report !== null;
  const isRecording = state === "recording";

  const processAudioBlob = useCallback(
    async (blob: Blob, filename: string) => {
      cancelledRef.current = false;
      setProcessing(true);
      setError(null);
      setDroppedFileName(truncateFilename(filename));
      try {
        setStep("uploading");
        playStepDone();

        setStep("transcribing");
        const raw = await transcribeAudio(blob, filename);
        if (cancelledRef.current) return;
        onTranscription(raw);
        playStepDone();

        setStep("formatting");
        const currentReport = reportRef.current;

        if (currentReport) {
          const result = await iterateReport(currentReport, raw);
          if (cancelledRef.current) return;
          onFormatted(result);
        } else {
          const result = await formatTranscription(raw);
          if (cancelledRef.current) return;
          onFormatted(result);
        }
        playStepDone();
        setStep("done");
        playAllDone();
      } catch (err: unknown) {
        if (cancelledRef.current) return;
        setStep("error");
        const msg = err instanceof Error ? err.message : "Erreur inconnue";
        setError(msg);
        toast(msg, "error");
      } finally {
        if (!cancelledRef.current) setProcessing(false);
      }
    },
    [onTranscription, onFormatted, playStepDone, playAllDone, toast]
  );

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

  useEffect(() => {
    if (state !== "stopped" || !audioBlob) return;
    if (processedBlobRef.current === audioBlob) return;
    if (processing) return;
    processedBlobRef.current = audioBlob;
    processAudioBlob(audioBlob, "recording.webm");
  }, [state, audioBlob, processAudioBlob, processing]);

  const handleFileSelected = useCallback(
    (file: File) => {
      if (processing) return;
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

  const recHint = isRecording
    ? formatDuration(duration)
    : processing
      ? "Traitement en cours..."
      : step === "done" && report
        ? "Espace pour completer le CR"
        : step === "done"
          ? "Espace pour redicter"
          : report
            ? "Espace pour completer le CR"
            : "Maintenir espace pour dicter";

  return (
    <div className="flex flex-col gap-3">
      {/* Push-to-talk zone — full width, with floating botanical elements */}
      <div
        className={cn(
          "relative flex h-[100px] cursor-pointer select-none items-center justify-center overflow-hidden rounded-xl border-2 transition-all",
          isRecording
            ? "border-iris-500 bg-iris-50 dark:bg-iris-950/30"
            : "border-dashed border-border hover:border-iris-400/50 hover:bg-iris-50/30 dark:hover:bg-iris-950/10"
        )}
        onMouseDown={handleStart}
        onMouseUp={handleStop}
        onMouseLeave={handleStop}
        onTouchStart={handleStart}
        onTouchEnd={handleStop}
      >
        {/* Botanical floating elements */}
        <FloatingLeaves />

        <div className="relative z-10 flex flex-col items-center gap-1.5">
          <Mic
            className={cn(
              "h-6 w-6 transition-colors",
              isRecording ? "text-iris-600" : "text-muted-foreground"
            )}
          />
          <span
            className={cn(
              "text-xs tabular-nums transition-colors",
              isRecording
                ? "font-semibold text-iris-700 dark:text-iris-400"
                : "text-muted-foreground"
            )}
          >
            {recHint}
          </span>
        </div>

        {/* Recording glow */}
        {isRecording && (
          <div className="absolute inset-0 animate-pulse-glow bg-iris-500/5" />
        )}
      </div>

      {/* Drop zone — compact */}
      <div
        className={cn(
          "flex h-[50px] cursor-pointer select-none items-center justify-center gap-2.5 rounded-lg border border-dashed transition-all",
          dragOver
            ? "border-iris-500 bg-iris-50 dark:bg-iris-950/20"
            : "border-border hover:border-muted-foreground hover:bg-accent/50",
          processing && "pointer-events-none opacity-50"
        )}
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
          className="hidden"
        />
        <Upload
          className={cn(
            "h-4 w-4 shrink-0",
            dragOver ? "text-iris-600" : "text-muted-foreground"
          )}
        />
        <div className="flex flex-col">
          <span className={cn("text-xs", dragOver ? "font-semibold text-iris-600" : "text-muted-foreground")}>
            {droppedFileName ?? (dragOver ? "Deposer le fichier" : "Glisser un fichier audio ou cliquer")}
          </span>
          <span className="text-[0.6rem] text-muted-foreground/60">
            MP3, MP4, M4A, WAV, OGG, FLAC
          </span>
        </div>
      </div>

      {/* Pipeline — always visible once started */}
      <div className="space-y-2">
        <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Workflow
        </span>
        <Pipeline currentStep={step} isIteration={isIteration} />
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Raw transcription — always visible */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted-foreground">
            Transcription brute
          </span>
          {rawTranscription && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onReformat(rawTranscription)}
              disabled={reformatting}
              title="Relancer la mise en forme"
              className="h-6 w-6"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", reformatting && "animate-spin")} />
            </Button>
          )}
        </div>
        <div className="rounded-lg border bg-card">
          {rawTranscription ? (
            <Textarea
              value={rawTranscription}
              onChange={(e) => onRawChange(e.target.value)}
              className="min-h-[80px] resize-y border-0 bg-transparent text-[0.82rem] leading-relaxed focus-visible:ring-0 focus-visible:ring-offset-0"
            />
          ) : (
            <p className="px-3 py-3 text-sm italic text-muted-foreground/50">
              La transcription apparaitra ici...
            </p>
          )}
        </div>
      </div>

      {step === "done" && (
        <Button variant="secondary" className="w-full" onClick={handleReset}>
          <RotateCcw className="h-4 w-4" />
          Nouveau compte-rendu
        </Button>
      )}
    </div>
  );
}
