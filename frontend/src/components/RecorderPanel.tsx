import { useState, useCallback, useRef, useEffect } from "react";
import { Mic, Upload, RotateCcw, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useSoundFeedback } from "../hooks/useSoundFeedback";
import {
  transcribeAudio,
  formatTranscription,
  iterateReport,
} from "../services/api";
import type { DonneeManquante } from "../services/api";
import Pipeline from "./Pipeline";
import type { PipelineStep } from "./Pipeline";

const ACCEPTED_EXTENSIONS = ".mp3,.mp4,.m4a,.mov,.wav,.webm,.ogg,.flac,.aac";
const ACCEPTED_MIME = "audio/*,video/mp4,video/quicktime,video/x-m4v";

interface RecorderPanelProps {
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
}: RecorderPanelProps) {
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

  // Reset interne quand le parent reset (report passe a null)
  useEffect(() => {
    if (report === null && rawTranscription === null) {
      reset();
      setError(null);
      setStep("idle");
      setDroppedFileName(null);
      processedBlobRef.current = null;
    }
  }, [report, rawTranscription, reset]);

  const isIteration = report !== null;
  const isRecording = state === "recording";

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

  // Push-to-talk handlers
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

  // Process recorded audio blob
  useEffect(() => {
    if (state !== "stopped" || !audioBlob) return;
    if (processedBlobRef.current === audioBlob) return;
    if (processing) return;
    processedBlobRef.current = audioBlob;
    processAudioBlob(audioBlob, "recording.webm");
  }, [state, audioBlob, processAudioBlob, processing]);

  // File handlers
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
        ? "Espace pour completer le compte-rendu"
        : step === "done"
          ? "Espace pour redicter"
          : report
            ? "Espace pour completer le compte-rendu"
            : "Maintenir espace pour dicter";

  return (
    <div className="flex flex-col gap-3">
      {/* Push-to-talk zone */}
      <div
        className={cn(
          "relative flex h-[90px] cursor-pointer select-none items-center justify-center overflow-hidden rounded-xl border-2 border-dashed transition-all",
          isRecording
            ? "border-solid border-primary"
            : "border-border hover:border-primary/50"
        )}
        onMouseDown={handleStart}
        onMouseUp={handleStop}
        onMouseLeave={handleStop}
        onTouchStart={handleStart}
        onTouchEnd={handleStop}
      >
        <div className="relative z-10 flex flex-col items-center gap-1.5">
          <Mic
            className={cn(
              "h-6 w-6 transition-colors",
              isRecording ? "text-primary" : "text-muted-foreground"
            )}
          />
          <span
            className={cn(
              "text-xs tabular-nums transition-colors",
              isRecording
                ? "font-semibold text-primary"
                : "text-muted-foreground"
            )}
          >
            {recHint}
          </span>
        </div>
        {isRecording && (
          <div className="absolute inset-0 animate-pulse-glow rounded-xl bg-gradient-radial from-primary/10 to-transparent" />
        )}
      </div>

      {/* Drop zone */}
      <div
        className={cn(
          "flex h-[58px] cursor-pointer select-none items-center justify-center gap-2.5 rounded-lg border border-dashed transition-all",
          dragOver
            ? "border-solid border-primary bg-primary/5"
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
            dragOver ? "text-primary" : "text-muted-foreground"
          )}
        />
        <div className="flex flex-col">
          <span
            className={cn(
              "text-xs",
              dragOver ? "font-semibold text-primary" : "text-muted-foreground"
            )}
          >
            {droppedFileName
              ? droppedFileName
              : dragOver
                ? "Deposer le fichier"
                : "Glisser un fichier audio ou cliquer"}
          </span>
          <span className="text-[0.6rem] text-muted-foreground/60">
            MP3, MP4, M4A, MOV, WAV, OGG, FLAC
          </span>
        </div>
      </div>

      {/* Workflow */}
      <div className="space-y-2">
        <span className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Workflow
        </span>
        <Pipeline currentStep={step} isIteration={isIteration} />
      </div>

      {error && (
        <div className="rounded-lg bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Raw transcription */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
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
              <RefreshCw
                className={cn("h-3.5 w-3.5", reformatting && "animate-spin")}
              />
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
        <Button
          variant="secondary"
          className="w-full"
          onClick={handleReset}
        >
          <RotateCcw className="h-4 w-4" />
          Nouveau compte-rendu
        </Button>
      )}
    </div>
  );
}
