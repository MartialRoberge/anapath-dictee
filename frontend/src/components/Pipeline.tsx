import { useState, useEffect, useRef } from "react";

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
  { key: "formatting", label: "Lexia Intelligence" },
  { key: "done", label: "Termine" },
];

const LEXIA_MESSAGES_INITIAL = [
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

const LEXIA_MESSAGES_ITERATION = [
  "Analyse du nouveau contenu...",
  "Fusion avec le rapport existant...",
  "Mise a jour des sections...",
  "Verification des donnees completees...",
];

function stepIndex(step: PipelineStep): number {
  return STEPS.findIndex((s) => s.key === step);
}

function getStatus(idx: number, activeIdx: number, currentStep: PipelineStep) {
  if (currentStep === "error") return idx <= activeIdx ? "error" : "pending";
  if (currentStep === "done") return "done" as const;
  if (idx < activeIdx) return "done" as const;
  if (idx === activeIdx) return "active" as const;
  return "pending" as const;
}

interface Props {
  currentStep: PipelineStep;
  isIteration?: boolean;
}

export default function Pipeline({ currentStep, isIteration = false }: Props) {
  const activeIdx = stepIndex(currentStep);
  const isVisible = currentStep !== "idle" && currentStep !== "recording";

  return (
    <div className="workflow">
      {STEPS.map((step, idx) => {
        const status = isVisible
          ? getStatus(idx, activeIdx, currentStep)
          : "pending";
        const isLexia = step.key === "formatting";

        return (
          <div key={step.key} className="workflow-item">
            <div
              className={`wf-block wf-block--${status} ${isLexia ? "wf-block--lexia" : ""}`}
            >
              <div className="wf-block-top">
                <div className="wf-icon">
                  {status === "done" && "\u2713"}
                  {status === "active" && !isLexia && (
                    <span className="wf-spinner" />
                  )}
                  {status === "active" && isLexia && (
                    <span className="wf-brain">\u25C6</span>
                  )}
                  {status === "error" && "!"}
                  {status === "pending" && <span className="wf-dot" />}
                </div>
                <span className="wf-label">{step.label}</span>
              </div>
              {isLexia && (status === "active" || status === "done") && (
                <div className="wf-lexia-body">
                  {status === "active" ? (
                    <LexiaAnimation isIteration={isIteration} />
                  ) : (
                    <span className="wf-lexia-done">
                      Analyse terminee \u2713
                    </span>
                  )}
                </div>
              )}
            </div>
            {idx < STEPS.length - 1 && (
              <div
                className={`wf-arrow ${status === "done" ? "wf-arrow--done" : ""}`}
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

function LexiaAnimation({ isIteration }: { isIteration: boolean }) {
  const messages = isIteration
    ? LEXIA_MESSAGES_ITERATION
    : LEXIA_MESSAGES_INITIAL;
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
    <div className="lexia-anim">
      <span className="lexia-anim-dot" />
      <span
        className={`lexia-anim-text ${visible ? "lexia-anim-text--visible" : ""}`}
      >
        {messages[msgIdx]}
      </span>
    </div>
  );
}
