import { useState, useEffect, useRef } from "react";
import { Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type PipelineStep =
  | "idle"
  | "recording"
  | "uploading"
  | "transcribing"
  | "formatting"
  | "done"
  | "error";

interface StepDef {
  key: PipelineStep;
  label: string;
}

const STEPS: StepDef[] = [
  { key: "uploading", label: "Envoi de l'audio" },
  { key: "transcribing", label: "Transcription" },
  { key: "formatting", label: "Iris Intelligence" },
  { key: "done", label: "Termine" },
];

const IRIS_MESSAGES_INITIAL: string[] = [
  "Correction phonetique medicale...",
  "Identification de l'organe...",
  "Chargement du template INCa...",
  "Application des standards...",
  "Recherche des acronymes...",
  "Expansion des termes nosologiques...",
  "Verification des negations...",
  "Structuration du compte-rendu...",
  "Generation du tableau IHC...",
  "Verification des donnees obligatoires...",
  "Redaction de la conclusion...",
];

const IRIS_MESSAGES_ITERATION: string[] = [
  "Analyse du nouveau contenu...",
  "Fusion avec le rapport existant...",
  "Mise a jour des sections...",
  "Verification des donnees completees...",
];

type StepStatus = "pending" | "active" | "done" | "error";

function getStepIndex(step: PipelineStep): number {
  return STEPS.findIndex((s) => s.key === step);
}

function computeStatus(
  idx: number,
  activeIdx: number,
  currentStep: PipelineStep
): StepStatus {
  if (currentStep === "error") return idx <= activeIdx ? "error" : "pending";
  if (currentStep === "done") return "done";
  if (idx < activeIdx) return "done";
  if (idx === activeIdx) return "active";
  return "pending";
}

interface PipelineProps {
  currentStep: PipelineStep;
  isIteration?: boolean;
}

export default function Pipeline({
  currentStep,
  isIteration = false,
}: PipelineProps) {
  const activeIdx = getStepIndex(currentStep);
  const isVisible = currentStep !== "idle" && currentStep !== "recording";

  return (
    <div className="flex flex-col items-center gap-0">
      {STEPS.map((step, idx) => {
        const status: StepStatus = isVisible
          ? computeStatus(idx, activeIdx, currentStep)
          : "pending";
        const isIris = step.key === "formatting";

        return (
          <div key={step.key} className="flex flex-col items-center">
            <div
              className={cn(
                "flex w-[180px] flex-col justify-center rounded-lg border p-2.5 transition-all duration-200",
                isIris && "h-[72px]",
                !isIris && "min-h-[52px]",
                status === "pending" && "border-border bg-card",
                status === "active" &&
                  "border-primary/40 bg-primary/5 shadow-sm shadow-primary/10",
                status === "done" && "border-success/30 bg-success/5",
                status === "error" && "border-destructive/30 bg-destructive/5"
              )}
            >
              <div className="flex items-center gap-2.5">
                <StepIcon status={status} isIris={isIris} />
                <span
                  className={cn(
                    "text-[0.8rem] font-medium",
                    status === "pending" && "text-muted-foreground",
                    status === "active" && "font-semibold text-primary",
                    status === "done" && "text-success",
                    status === "error" && "text-destructive"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {isIris && (status === "active" || status === "done") && (
                <div className="mt-1 flex h-5 items-center gap-1.5 overflow-hidden">
                  {status === "active" ? (
                    <IrisAnimation isIteration={isIteration} />
                  ) : (
                    <span className="text-[0.68rem] font-medium text-success">
                      Analyse terminee
                    </span>
                  )}
                </div>
              )}
            </div>
            {idx < STEPS.length - 1 && (
              <div
                className={cn(
                  "py-1 text-muted-foreground/40 transition-colors",
                  status === "done" && "text-success/60"
                )}
              >
                <svg width="10" height="10" viewBox="0 0 10 10">
                  <path
                    d="M5 2 L5 8 M2 5.5 L5 8 L8 5.5"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StepIcon({
  status,
  isIris,
}: {
  status: StepStatus;
  isIris: boolean;
}) {
  const baseClass =
    "flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[0.6rem] font-bold";

  if (status === "done") {
    return (
      <div className={cn(baseClass, "bg-success text-white")}>
        <Check className="h-3 w-3" />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className={cn(baseClass, "bg-destructive text-white")}>
        <AlertCircle className="h-3 w-3" />
      </div>
    );
  }
  if (status === "active" && isIris) {
    return (
      <div className={cn(baseClass, "bg-primary text-white")}>
        <span className="animate-pulse-brain text-[0.65rem]">{"\u25C6"}</span>
      </div>
    );
  }
  if (status === "active") {
    return (
      <div className={cn(baseClass, "bg-primary text-white")}>
        <span className="block h-3 w-3 animate-spin-slow rounded-full border-2 border-white/30 border-t-white" />
      </div>
    );
  }
  return (
    <div className={cn(baseClass, "bg-muted text-muted-foreground")}>
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
    </div>
  );
}

function IrisAnimation({ isIteration }: { isIteration: boolean }) {
  const messages = isIteration
    ? IRIS_MESSAGES_ITERATION
    : IRIS_MESSAGES_INITIAL;
  const [msgIdx, setMsgIdx] = useState(0);
  const [visible, setVisible] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    setMsgIdx(0);
    setVisible(true);
  }, [isIteration]);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setMsgIdx((prev) => (prev + 1) % messages.length);
        setVisible(true);
      }, 250);
    }, 2000);
    return () => clearInterval(intervalRef.current);
  }, [messages]);

  return (
    <div className="flex items-center gap-1.5">
      <span className="h-1 w-1 shrink-0 animate-pulse-brain rounded-full bg-primary/60" />
      <span
        className={cn(
          "max-w-[140px] truncate text-[0.68rem] text-muted-foreground transition-opacity duration-200",
          visible ? "opacity-100" : "opacity-0"
        )}
      >
        {messages[msgIdx]}
      </span>
    </div>
  );
}
