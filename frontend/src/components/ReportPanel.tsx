import {
  useState,
  useMemo,
  useCallback,
  useEffect,
  useRef,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { marked } from "marked";
import { exportDocx, getSections } from "../services/api";
import type { DonneeManquante } from "../services/api";
import "./ReportPanel.css";

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Props {
  report: string | null;
  onReportChange: (report: string) => void;
  donneesManquantes: DonneeManquante[];
  organeDetecte: string;
}

interface ACompleterField {
  id: string;
  fullMatch: string;
  placeholder: string;
}

/* ------------------------------------------------------------------ */
/*  Section labels                                                     */
/* ------------------------------------------------------------------ */

const SECTION_LABELS: Record<string, string> = {
  titre: "Titre",
  renseignements_cliniques: "Renseignements cliniques",
  macroscopie: "Macroscopie",
  microscopie: "Étude histologique",
  ihc: "Immunomarquage",
  biologie_moleculaire: "Biologie moléculaire",
  conclusion: "Conclusion",
};

const SECTION_ORDER = [
  "titre",
  "renseignements_cliniques",
  "macroscopie",
  "microscopie",
  "ihc",
  "biologie_moleculaire",
  "conclusion",
];

/* ------------------------------------------------------------------ */
/*  SVG icons (inline, no dependency)                                  */
/* ------------------------------------------------------------------ */

function IconEdit() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function IconCopy() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function IconTrash() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function IconDocx() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function IconRaw() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Markdown helpers                                                   */
/* ------------------------------------------------------------------ */

/**
 * Pre-process ACP markdown before passing to marked.
 * Converts anapath-specific conventions to HTML:
 * - **__TEXT__** -> bold + underline
 * - __TEXT__ -> bold + underline
 * - Ensures blank lines before ## so marked parses them
 */
function preprocessMarkdown(md: string): string {
  let result = md;

  // **__TEXT__** -> HTML bold+underline
  result = result.replace(
    /\*\*__([^_]+?)__\*\*/g,
    "<strong><u>$1</u></strong>"
  );

  // __TEXT__ (standalone, not inside **) -> HTML bold+underline
  result = result.replace(
    /(?<!\*\*)__([^_]+?)__(?!\*\*)/g,
    "<strong><u>$1</u></strong>"
  );

  // Ensure blank line before ## so marked parses as headers
  result = result.replace(/([^\n])\n(#{1,3} )/g, "$1\n\n$2");

  return result;
}

function sanitizeHtml(html: string): string {
  const div = document.createElement("div");
  div.innerHTML = html;
  div
    .querySelectorAll("script, iframe, object, embed, form")
    .forEach((el) => el.remove());
  div.querySelectorAll("*").forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      if (
        attr.name.startsWith("on") ||
        attr.value.trim().toLowerCase().startsWith("javascript:")
      ) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return div.innerHTML;
}

/** Render markdown to safe HTML (without [A COMPLETER] handling). */
function renderMarkdown(md: string): string {
  const preprocessed = preprocessMarkdown(md);
  const raw = marked.parse(preprocessed, { async: false }) as string;
  return sanitizeHtml(raw);
}

/* ------------------------------------------------------------------ */
/*  [A COMPLETER] parsing                                              */
/* ------------------------------------------------------------------ */

const A_COMPLETER_REGEX = /\[(?:[AÀ]\s*COMPL[EÉ]TER)\s*:\s*([^\]]+)\]/gi;

/** Extract all [A COMPLETER: xxx] markers from text. */
function extractACompleterFields(text: string): ACompleterField[] {
  const fields: ACompleterField[] = [];
  let match: RegExpExecArray | null;
  const regex = new RegExp(A_COMPLETER_REGEX.source, "gi");
  while ((match = regex.exec(text)) !== null) {
    fields.push({
      id: `ac-${fields.length}-${match[1].trim().replace(/\s+/g, "_")}`,
      fullMatch: match[0],
      placeholder: match[1].trim(),
    });
  }
  return fields;
}

/** Count [A COMPLETER] fields in text. */
function countACompleter(text: string): number {
  const regex = new RegExp(A_COMPLETER_REGEX.source, "gi");
  const matches = text.match(regex);
  return matches ? matches.length : 0;
}

/* ------------------------------------------------------------------ */
/*  SectionCard sub-component                                          */
/* ------------------------------------------------------------------ */

interface SectionCardProps {
  sectionKey: string;
  content: string;
  onContentChange: (key: string, newContent: string) => void;
  onDelete: (key: string) => void;
  onACompleterFill: (
    sectionKey: string,
    fullMatch: string,
    value: string
  ) => void;
}

function SectionCard({
  sectionKey,
  content,
  onContentChange,
  onDelete,
  onACompleterFill,
}: SectionCardProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(content);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const label = SECTION_LABELS[sectionKey] || sectionKey;

  // Sync edit value when content changes externally
  useEffect(() => {
    if (!editing) {
      setEditValue(content);
    }
  }, [content, editing]);

  // Focus textarea when entering edit mode
  useEffect(() => {
    if (editing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(
        textareaRef.current.value.length,
        textareaRef.current.value.length
      );
    }
  }, [editing]);

  const handleEdit = () => {
    setEditValue(content);
    setEditing(true);
  };

  const handleSave = () => {
    onContentChange(sectionKey, editValue);
    setEditing(false);
  };

  const handleCancel = () => {
    setEditValue(content);
    setEditing(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      handleCancel();
    }
    // Ctrl/Cmd + Enter to save
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      handleSave();
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDeleteClick = () => {
    setConfirmDelete(true);
  };

  const handleDeleteConfirm = () => {
    onDelete(sectionKey);
    setConfirmDelete(false);
  };

  const handleDeleteCancel = () => {
    setConfirmDelete(false);
  };

  // Render content with inline [A COMPLETER] fields
  const renderedContent = useMemo(() => {
    const fields = extractACompleterFields(content);
    if (fields.length === 0) {
      return renderMarkdown(content);
    }

    // Replace [A COMPLETER: xxx] with placeholder spans that will become inputs
    let processed = content;
    fields.forEach((field, idx) => {
      processed = processed.replace(
        field.fullMatch,
        `<span class="a-completer-field" data-ac-idx="${idx}" data-ac-match="${encodeURIComponent(field.fullMatch)}" data-ac-placeholder="${encodeURIComponent(field.placeholder)}"></span>`
      );
    });
    return renderMarkdown(processed);
  }, [content]);

  // After render, inject input elements into the placeholder spans
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing || !contentRef.current) return;

    const spans = contentRef.current.querySelectorAll(".a-completer-field");
    spans.forEach((span) => {
      const fullMatch = decodeURIComponent(
        span.getAttribute("data-ac-match") || ""
      );
      const placeholder = decodeURIComponent(
        span.getAttribute("data-ac-placeholder") || ""
      );

      // Clear any existing children
      span.innerHTML = "";

      const input = document.createElement("input");
      input.type = "text";
      input.className = "a-completer-input";
      input.placeholder = placeholder;
      input.title = `Champ à compléter : ${placeholder}`;
      // Dynamically size input based on placeholder
      input.style.width = `${Math.max(placeholder.length * 8 + 40, 120)}px`;

      input.addEventListener("blur", () => {
        const value = input.value.trim();
        if (value) {
          input.classList.add("a-completer-input--filled");
          onACompleterFill(sectionKey, fullMatch, value);
        }
      });

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          input.blur();
        }
      });

      input.addEventListener("input", () => {
        if (input.value.trim()) {
          input.classList.add("a-completer-input--filled");
        } else {
          input.classList.remove("a-completer-input--filled");
        }
      });

      span.appendChild(input);
    });
  }, [renderedContent, editing, sectionKey, onACompleterFill]);

  return (
    <div className="section-card">
      <div className="section-bar">
        <span className="section-label-text">{label}</span>
        <div className="section-actions">
          {!editing && (
            <>
              <button
                className="section-action-btn"
                onClick={handleEdit}
                title={`Modifier la section ${label}`}
              >
                <IconEdit />
              </button>
              <button
                className={`section-action-btn ${copied ? "section-action-btn--success" : ""}`}
                onClick={handleCopy}
                title={`Copier la section ${label}`}
              >
                {copied ? <IconCheck /> : <IconCopy />}
              </button>
              <button
                className="section-action-btn section-action-btn--danger"
                onClick={handleDeleteClick}
                title={`Supprimer la section ${label}`}
              >
                <IconTrash />
              </button>
            </>
          )}
        </div>
      </div>

      {confirmDelete && (
        <div className="section-delete-confirm">
          <span className="section-delete-text">
            Supprimer la section &laquo;&nbsp;{label}&nbsp;&raquo; ?
          </span>
          <button
            className="section-delete-btn section-delete-btn--confirm"
            onClick={handleDeleteConfirm}
          >
            Supprimer
          </button>
          <button className="section-delete-btn" onClick={handleDeleteCancel}>
            Annuler
          </button>
        </div>
      )}

      <div className="section-body">
        {editing ? (
          <>
            <textarea
              ref={textareaRef}
              className="section-edit-area"
              value={editValue}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
                setEditValue(e.target.value)
              }
              onKeyDown={handleKeyDown}
            />
            <div className="section-edit-actions">
              <button className="section-edit-btn" onClick={handleCancel}>
                Annuler
              </button>
              <button
                className="section-edit-btn section-edit-btn--save"
                onClick={handleSave}
              >
                Enregistrer
              </button>
            </div>
          </>
        ) : (
          <div
            ref={contentRef}
            className="section-rendered"
            dangerouslySetInnerHTML={{ __html: renderedContent }}
          />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main ReportPanel component                                         */
/* ------------------------------------------------------------------ */

export default function ReportPanel({
  report,
  onReportChange,
  donneesManquantes: _donneesManquantes,
  organeDetecte,
}: Props) {
  void _donneesManquantes; // Used by parent for state tracking
  const [sections, setSections] = useState<Record<string, string> | null>(null);
  const [loadingSections, setLoadingSections] = useState(false);
  const [rawEditing, setRawEditing] = useState(false);
  const [copied, setCopied] = useState(false);

  // Count [A COMPLETER] fields in the report
  const aCompleterCount = useMemo(() => {
    if (!report) return 0;
    return countACompleter(report);
  }, [report]);

  // Fetch sections when report is available
  const fetchSections = useCallback(async () => {
    if (!report) return;
    setLoadingSections(true);
    try {
      const result = await getSections(report);
      setSections(result.sections);
    } catch {
      setSections(null);
    } finally {
      setLoadingSections(false);
    }
  }, [report]);

  // Automatically fetch sections when report changes
  useEffect(() => {
    if (report && !rawEditing) {
      fetchSections();
    }
  }, [report]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---- Section editing ---- */

  const handleSectionChange = useCallback(
    (key: string, newContent: string) => {
      if (!sections) return;

      const updated = { ...sections, [key]: newContent };
      setSections(updated);

      // Reconstruct full report from sections
      const orderedKeys = SECTION_ORDER.filter((k) => updated[k]?.trim());
      // Also include any keys not in the standard order
      const extraKeys = Object.keys(updated).filter(
        (k) => !SECTION_ORDER.includes(k) && updated[k]?.trim()
      );
      const allKeys = [...orderedKeys, ...extraKeys];

      const fullReport = allKeys.map((k) => updated[k].trim()).join("\n\n");
      onReportChange(fullReport);
    },
    [sections, onReportChange]
  );

  const handleSectionDelete = useCallback(
    (key: string) => {
      if (!sections) return;

      const updated = { ...sections };
      delete updated[key];
      setSections(updated);

      // Reconstruct full report
      const orderedKeys = SECTION_ORDER.filter((k) => updated[k]?.trim());
      const extraKeys = Object.keys(updated).filter(
        (k) => !SECTION_ORDER.includes(k) && updated[k]?.trim()
      );
      const allKeys = [...orderedKeys, ...extraKeys];

      const fullReport = allKeys.map((k) => updated[k].trim()).join("\n\n");
      onReportChange(fullReport);
    },
    [sections, onReportChange]
  );

  const handleACompleterFill = useCallback(
    (sectionKey: string, fullMatch: string, value: string) => {
      if (!sections || !report) return;

      // Replace in the section content
      const sectionContent = sections[sectionKey];
      if (!sectionContent) return;

      const newSectionContent = sectionContent.replace(fullMatch, value);
      const updated = { ...sections, [sectionKey]: newSectionContent };
      setSections(updated);

      // Also replace in the full report
      const newReport = report.replace(fullMatch, value);
      onReportChange(newReport);
    },
    [sections, report, onReportChange]
  );

  /* ---- Actions ---- */

  const handleCopyAll = async () => {
    if (!report) return;
    await navigator.clipboard.writeText(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExportDocx = async () => {
    if (!report) return;
    try {
      const title = organeDetecte
        ? `Compte-rendu - ${organeDetecte}`
        : undefined;
      const blob = await exportDocx(report, title);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "compte-rendu.docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Erreur lors de l'export Word.");
    }
  };

  const handleToggleRawEdit = () => {
    setRawEditing(!rawEditing);
  };

  /* ---- Fallback rendering (if sections API fails) ---- */

  const fallbackHtml = useMemo(() => {
    if (!report) return "";
    // Render with [A COMPLETER] as highlighted spans (non-editable in fallback)
    let html = renderMarkdown(report);
    html = html.replace(
      /\[(?:[AÀ]\s*COMPL[EÉ]TER)\s*:\s*([^\]]+)\]/gi,
      '<span class="a-completer-input" style="display:inline;cursor:default;min-width:auto;padding:2px 8px;">$1</span>'
    );
    return html;
  }, [report]);

  /* ---- Ordered sections for display ---- */

  const orderedSections = useMemo(() => {
    if (!sections) return [];
    const result: { key: string; content: string }[] = [];

    // First, add sections in the standard order
    for (const key of SECTION_ORDER) {
      if (sections[key]?.trim()) {
        result.push({ key, content: sections[key] });
      }
    }

    // Then add any extra sections not in the standard order
    for (const key of Object.keys(sections)) {
      if (!SECTION_ORDER.includes(key) && sections[key]?.trim()) {
        result.push({ key, content: sections[key] });
      }
    }

    return result;
  }, [sections]);

  /* ---- Render ---- */

  if (!report) {
    return (
      <div className="report-panel report-empty">
        <p>
          Le compte-rendu formaté apparaîtra ici après
          transcription.
        </p>
      </div>
    );
  }

  return (
    <div className="report-panel">
      {/* -- Toolbar -- */}
      <div className="report-toolbar">
        <div className="report-toolbar-left">
          <h2 className="report-toolbar-title">Compte-rendu</h2>
          {organeDetecte && (
            <span className="organe-badge">{organeDetecte}</span>
          )}
          {aCompleterCount > 0 && (
            <span className="missing-badge">
              <span className="missing-badge-dot" />
              {aCompleterCount} champ{aCompleterCount > 1 ? "s" : ""}{" "}
              à compléter
            </span>
          )}
        </div>
        <div className="report-toolbar-actions">
          <button
            className={`toolbar-btn ${rawEditing ? "toolbar-btn--active" : ""}`}
            onClick={handleToggleRawEdit}
            title={rawEditing ? "Retour à la vue document" : "Modifier le markdown brut"}
          >
            <IconRaw />
            {rawEditing ? "Vue document" : "Modifier tout"}
          </button>
          <button
            className={`toolbar-btn ${copied ? "toolbar-btn--success" : ""}`}
            onClick={handleCopyAll}
            title="Copier tout le compte-rendu"
          >
            {copied ? <IconCheck /> : <IconCopy />}
            {copied ? "Copié !" : "Copier tout"}
          </button>
          <button
            className="toolbar-btn toolbar-btn--primary"
            onClick={handleExportDocx}
            title="Exporter en fichier Word"
          >
            <IconDocx />
            Exporter .docx
          </button>
        </div>
      </div>

      {/* -- Content area -- */}
      {rawEditing ? (
        <div className="report-raw-edit">
          <textarea
            className="report-raw-textarea"
            value={report}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
              onReportChange(e.target.value)
            }
          />
        </div>
      ) : (
        <div className="report-document">
          <div className="report-page">
            {loadingSections ? (
              <div className="report-loading">
                <div className="report-loading-spinner" />
                <span className="report-loading-text">
                  Analyse des sections...
                </span>
              </div>
            ) : sections && orderedSections.length > 0 ? (
              <div className="report-sections-list">
                {orderedSections.map(({ key, content }) => (
                  <SectionCard
                    key={key}
                    sectionKey={key}
                    content={content}
                    onContentChange={handleSectionChange}
                    onDelete={handleSectionDelete}
                    onACompleterFill={handleACompleterFill}
                  />
                ))}
              </div>
            ) : (
              /* Fallback: render full report if sections failed or unavailable */
              <div
                className="report-fallback-content"
                dangerouslySetInnerHTML={{ __html: fallbackHtml }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
