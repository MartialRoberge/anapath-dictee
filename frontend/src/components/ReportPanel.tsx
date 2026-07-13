import {
  useState,
  useMemo,
  useCallback,
  useEffect,
  useRef,
} from "react";
import {
  Copy,
  Check,
  Trash2,
  FileDown,
  FileText,
  FileType,
  Undo2,
  Redo2,
  Mic,
  Upload,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { exportDocx, getSections } from "../services/api";
import CodificationPanel from "./CodificationPanel";
import { copyReportRich, markdownToPlainText } from "../lib/reportText";

/* ------------------------------------------------------------------ */
/*  Section config                                                     */
/* ------------------------------------------------------------------ */

const SECTION_LABELS: Record<string, string> = {
  titre: "Titre",
  renseignements_cliniques: "Renseignements cliniques",
  macroscopie: "Macroscopie",
  microscopie: "Etude histologique",
  ihc: "Immunomarquage",
  biologie_moleculaire: "Biologie moleculaire",
  conclusion: "Conclusion",
};

/** Genere un label lisible pour les sections dynamiques (prelevements). */
function getSectionLabel(key: string): string {
  if (SECTION_LABELS[key]) return SECTION_LABELS[key];
  // prelevement_1, prelevement_2, etc.
  const match = key.match(/^prelevement_(\d+)$/);
  if (match) return `Prelevement ${match[1]}`;
  return key;
}

const SECTION_ORDER: string[] = [
  "titre",
  "renseignements_cliniques",
  "macroscopie",
  "microscopie",
  "ihc",
  "biologie_moleculaire",
  "conclusion",
];

/* ------------------------------------------------------------------ */
/*  Markdown conventions ACP                                           */
/* ------------------------------------------------------------------ */

const A_COMPLETER_REGEX = /\[(?:[AÀ]\s*COMPL[EÉ]TER)\s*:\s*([^\]]+)\]/gi;

/**
 * Pre-process ACP markdown conventions into standard HTML
 * (utilise uniquement pour le rendu lecture seule de secours).
 */
function preprocessMarkdown(md: string): string {
  let result = md;

  // **__TEXT__** -> HTML bold+underline
  result = result.replace(
    /\*\*__([^_]+?)__\*\*/g,
    "<strong><u>$1</u></strong>"
  );

  // __TEXT__ (standalone) -> HTML bold+underline
  result = result.replace(
    /(?<!\*\*)__([^_]+?)__(?!\*\*)/g,
    "<strong><u>$1</u></strong>"
  );

  // Ensure blank line before ## so markdown parses as headers
  result = result.replace(/([^\n])\n(#{1,3} )/g, "$1\n\n$2");

  // [A COMPLETER: xxx] -> styled inline span
  result = result.replace(
    A_COMPLETER_REGEX,
    '<span class="acp-missing" data-field="$1">$1</span>'
  );

  return result;
}

function countACompleter(text: string): number {
  const regex = new RegExp(A_COMPLETER_REGEX.source, "gi");
  const matches = text.match(regex);
  return matches ? matches.length : 0;
}

/* ------------------------------------------------------------------ */
/*  useUndoStack — historique undo/redo pour l'edition de sections     */
/* ------------------------------------------------------------------ */

const MAX_UNDO_DEPTH = 50;

interface UndoState {
  past: Record<string, string>[];
  present: Record<string, string> | null;
  future: Record<string, string>[];
}

function useUndoStack(initial: Record<string, string> | null) {
  const [state, setState] = useState<UndoState>({
    past: [],
    present: initial,
    future: [],
  });

  // Synchroniser quand le rapport change de l'exterieur (nouveau formatage)
  const lastExternalRef = useRef(initial);
  useEffect(() => {
    if (initial !== lastExternalRef.current) {
      lastExternalRef.current = initial;
      setState({ past: [], present: initial, future: [] });
    }
  }, [initial]);

  const push = useCallback((next: Record<string, string>) => {
    setState((prev) => ({
      past: [...prev.past.slice(-MAX_UNDO_DEPTH), ...(prev.present ? [prev.present] : [])],
      present: next,
      future: [],
    }));
  }, []);

  // Remplace l'etat courant SANS empiler (coalescence de la frappe continue).
  const replace = useCallback((next: Record<string, string>) => {
    setState((prev) => ({ ...prev, present: next, future: [] }));
  }, []);

  const undo = useCallback(() => {
    setState((prev) => {
      if (prev.past.length === 0) return prev;
      const previous = prev.past[prev.past.length - 1];
      return {
        past: prev.past.slice(0, -1),
        present: previous,
        future: [prev.present!, ...prev.future],
      };
    });
  }, []);

  const redo = useCallback(() => {
    setState((prev) => {
      if (prev.future.length === 0) return prev;
      const next = prev.future[0];
      return {
        past: [...prev.past, prev.present!],
        present: next,
        future: prev.future.slice(1),
      };
    });
  }, []);

  return {
    sections: state.present,
    push,
    replace,
    undo,
    redo,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
  };
}

/* ------------------------------------------------------------------ */
/*  Read-only markdown (rendu de secours si /sections indisponible)    */
/* ------------------------------------------------------------------ */

const SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    "strong", "em", "u", "span", "br", "table", "thead", "tbody",
    "tr", "th", "td", "p", "h1", "h2", "h3", "ul", "ol", "li",
  ],
  attributes: {
    ...defaultSchema.attributes,
    span: ["className", "class", "dataField", "data-field", "data-*"],
  },
};

function MarkdownReport({ content }: { content: string }) {
  const processed = useMemo(() => preprocessMarkdown(content), [content]);

  return (
    <div className="report-typography">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, SANITIZE_SCHEMA]]}
        components={{
          table: ({ children }) => (
            <table className="w-full border-collapse my-3">{children}</table>
          ),
          th: ({ children }) => (
            <th className="border border-border bg-muted px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-3 py-2">{children}</td>
          ),
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Conversion Markdown <-> HTML editable (contentEditable propre)      */
/* ------------------------------------------------------------------ */

interface TableData {
  headers: string[];
  rows: string[][];
}

function parseMarkdownTable(tableBlock: string): TableData | null {
  const lines = tableBlock.trim().split("\n").filter((l) => l.trim());
  if (lines.length < 2) return null;

  const parseLine = (line: string): string[] =>
    line
      .trim()
      .replace(/^\||\|$/g, "")
      .split("|")
      .map((c) => c.trim());

  const headers = parseLine(lines[0]);
  const separator = parseLine(lines[1]);
  if (!separator.every((s) => /^:?-+:?$/.test(s))) return null;

  const rows = lines.slice(2).map(parseLine);
  return { headers, rows };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Markdown inline -> HTML propre (jamais de **, __, | visibles). */
function inlineMdToHtml(text: string): string {
  let h = escapeHtml(text);

  // Pastilles [A COMPLETER: xxx] — non editables, cliquables
  h = h.replace(A_COMPLETER_REGEX, (_m, field: string) => {
    const clean = field.trim();
    return `<span class="acp-missing" contenteditable="false" data-field="${escapeHtml(
      clean
    )}">${escapeHtml(clean)}</span>`;
  });

  // Gras + souligne (titres)
  h = h.replace(/\*\*__(.+?)__\*\*/g, "<strong><u>$1</u></strong>");
  h = h.replace(/__(.+?)__/g, "<strong><u>$1</u></strong>");
  // Gras
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italique
  h = h.replace(/\*([^*\n]+?)\*/g, "<em>$1</em>");

  return h;
}

function tableMdToHtml(tableLines: string[]): string {
  const table = parseMarkdownTable(tableLines.join("\n"));
  if (!table) {
    return `<p>${tableLines.map(inlineMdToHtml).join("<br>")}</p>`;
  }
  const head =
    "<thead><tr>" +
    table.headers.map((h) => `<th>${inlineMdToHtml(h)}</th>`).join("") +
    "</tr></thead>";
  const body =
    "<tbody>" +
    table.rows
      .map(
        (row) =>
          "<tr>" +
          row.map((c) => `<td>${inlineMdToHtml(c)}</td>`).join("") +
          "</tr>"
      )
      .join("") +
    "</tbody>";
  return `<table>${head}${body}</table>`;
}

/** Markdown d'une section -> HTML editable joliment rendu. */
function markdownToEditableHtml(md: string): string {
  const lines = md.split("\n");
  const blocks: string[] = [];
  let para: string[] = [];
  let table: string[] = [];

  const flushPara = () => {
    if (para.length) {
      blocks.push(`<p>${para.map(inlineMdToHtml).join("<br>")}</p>`);
      para = [];
    }
  };
  const flushTable = () => {
    if (table.length) {
      blocks.push(tableMdToHtml(table));
      table = [];
    }
  };

  for (const line of lines) {
    const t = line.trim();
    const isTableLine = t.startsWith("|") && t.endsWith("|");
    if (isTableLine) {
      flushPara();
      table.push(line);
      continue;
    }
    flushTable();
    if (t === "") {
      flushPara();
      continue;
    }
    para.push(line);
  }
  flushPara();
  flushTable();

  return blocks.join("") || "<p><br></p>";
}

/** Serialise une cellule de tableau (inline, sans pipe ni saut de ligne). */
function cellToMarkdown(cell: Element): string {
  return htmlNodeToMarkdown(cell)
    .replace(/\n+/g, " ")
    .replace(/\|/g, "\\|")
    .trim();
}

function serializeTable(tableEl: Element): string {
  const rowEls = Array.from(tableEl.querySelectorAll("tr"));
  if (rowEls.length === 0) return "";
  const rows = rowEls.map((tr) =>
    Array.from(tr.querySelectorAll("th,td")).map(cellToMarkdown)
  );
  const header = rows[0];
  const sep = header.map(() => "---");
  const bodyRows = rows.slice(1);
  const line = (cells: string[]) => `| ${cells.join(" | ")} |`;
  return [line(header), line(sep), ...bodyRows.map(line)].join("\n");
}

function htmlNodeToMarkdown(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  if (node.nodeType !== Node.ELEMENT_NODE) return "";

  const el = node as HTMLElement;
  const tag = el.tagName.toLowerCase();

  if (tag === "table") return serializeTable(el);
  if (el.classList.contains("acp-missing")) {
    const field = el.getAttribute("data-field") ?? el.textContent ?? "";
    return `[A COMPLETER: ${field.trim()}]`;
  }

  const inner = Array.from(el.childNodes).map(htmlNodeToMarkdown).join("");

  switch (tag) {
    case "strong":
    case "b":
      return `**${inner}**`;
    case "u":
      return `__${inner}__`;
    case "em":
    case "i":
      return `*${inner}*`;
    case "br":
      return "\n";
    case "p":
      return inner + "\n\n";
    case "div":
      return inner + "\n";
    default:
      return inner;
  }
}

/** HTML editable -> Markdown propre. */
function editableHtmlToMarkdown(html: string): string {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const root = doc.body.firstElementChild;
  if (!root) return "";
  return htmlNodeToMarkdown(root)
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/* ------------------------------------------------------------------ */
/*  InlineSectionEditor — edition au curseur, sans bouton, sans markdown*/
/* ------------------------------------------------------------------ */

function InlineSectionEditor({
  value,
  onChange,
  onReplaceField,
  onDismissField,
}: {
  value: string;
  onChange: (md: string) => void;
  onReplaceField?: (fieldName: string, value: string) => void;
  onDismissField?: (fieldName: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const lastEmitted = useRef<string | null>(null);
  const [pill, setPill] = useState<{ field: string; x: number; y: number } | null>(
    null
  );
  const [pillValue, setPillValue] = useState("");

  // (Re)synchronise le HTML uniquement sur changement externe (pas notre echo).
  useEffect(() => {
    if (!ref.current) return;
    if (value === lastEmitted.current) return;
    ref.current.innerHTML = markdownToEditableHtml(value);
  }, [value]);

  const handleInput = useCallback(() => {
    if (!ref.current) return;
    const md = editableHtmlToMarkdown(ref.current.innerHTML);
    lastEmitted.current = md;
    onChange(md);
  }, [onChange]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    const pillEl = target.closest?.(".acp-missing") as HTMLElement | null;
    if (pillEl) {
      e.preventDefault();
      const rect = pillEl.getBoundingClientRect();
      setPill({
        field: pillEl.getAttribute("data-field") ?? "",
        x: rect.left,
        y: rect.bottom + 4,
      });
      setPillValue("");
    }
  }, []);

  const submitPill = () => {
    if (pill && pillValue.trim() && onReplaceField) {
      onReplaceField(pill.field, pillValue.trim());
    }
    setPill(null);
    setPillValue("");
  };

  const dismissPill = () => {
    if (pill && onDismissField) onDismissField(pill.field);
    setPill(null);
    setPillValue("");
  };

  return (
    <>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        spellCheck={false}
        onInput={handleInput}
        onMouseDown={handleMouseDown}
        data-placeholder="Cliquez pour ecrire..."
        className="report-typography acp-editable min-h-[28px] rounded-md px-1 py-0.5 outline-none transition-colors focus:bg-primary/[0.03]"
      />
      {pill && (
        <>
          <div
            className="fixed inset-0 z-40"
            onMouseDown={(e) => {
              e.preventDefault();
              setPill(null);
            }}
          />
          <div
            className="fixed z-50 flex items-center gap-1 rounded-lg border border-warning/40 bg-card p-1 shadow-lg"
            style={{ left: pill.x, top: pill.y }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <input
              type="text"
              autoFocus
              value={pillValue}
              placeholder={pill.field}
              onChange={(e) => setPillValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitPill();
                if (e.key === "Escape") setPill(null);
              }}
              className="w-48 bg-transparent px-2 py-1 text-sm text-foreground outline-none placeholder:text-muted-foreground/60"
            />
            <button
              onClick={submitPill}
              className="rounded px-2 py-1 text-xs font-bold text-success hover:bg-success/10"
              title="Valider"
            >
              OK
            </button>
            <button
              onClick={dismissPill}
              className="rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              title="Retirer ce champ"
            >
              &times;
            </button>
          </div>
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Section utilities                                                  */
/* ------------------------------------------------------------------ */

const SECTION_TITLE_NAMES: Record<string, string[]> = {
  titre: [],
  renseignements_cliniques: [
    "renseignements cliniques",
    "renseignement clinique",
  ],
  macroscopie: ["macroscopie", "examen macroscopique"],
  microscopie: [
    "microscopie",
    "etude histologique",
    "l'etude histologique",
    "letude histologique",
  ],
  ihc: ["immunomarquage", "immunohistochimie"],
  biologie_moleculaire: ["biologie moleculaire"],
  conclusion: ["conclusion"],
};

/**
 * Separe la ligne de titre de section de son corps.
 * Le titre reste stocke dans le markdown (export/copie), mais n'est pas
 * dupplique a l'affichage : la carte montre un label discret + le corps editable.
 */
function splitSectionTitle(
  content: string,
  sectionKey: string
): { title: string; body: string } {
  const lines = content.split("\n");
  if (lines.length <= 1) return { title: "", body: content };

  const firstNorm = lines[0]
    .trim()
    .toLowerCase()
    .replace(/[*_#:]/g, "")
    .trim();

  const names = SECTION_TITLE_NAMES[sectionKey];
  if (!names || names.length === 0) return { title: "", body: content };

  if (names.some((n) => firstNorm.includes(n))) {
    return {
      title: lines[0],
      body: lines.slice(1).join("\n").replace(/^\n+/, ""),
    };
  }

  return { title: "", body: content };
}

function buildOrderedSections(
  sections: Record<string, string>
): Array<{ key: string; content: string }> {
  const result: Array<{ key: string; content: string }> = [];

  for (const key of SECTION_ORDER) {
    if (sections[key]?.trim()) {
      result.push({ key, content: sections[key] });
    }
  }

  const dynamicKeys = Object.keys(sections)
    .filter((k) => !SECTION_ORDER.includes(k) && sections[k]?.trim())
    .sort((a, b) => {
      const na = parseInt(a.replace(/\D/g, "") || "999", 10);
      const nb = parseInt(b.replace(/\D/g, "") || "999", 10);
      return na - nb;
    });

  const conclusionIdx = result.findIndex((s) => s.key === "conclusion");
  let insertAt = conclusionIdx >= 0 ? conclusionIdx : result.length;

  for (const key of dynamicKeys) {
    result.splice(insertAt, 0, { key, content: sections[key] });
    insertAt++;
  }

  return result;
}

function rebuildReport(sections: Record<string, string>): string {
  const orderedKeys = SECTION_ORDER.filter((k) => sections[k]?.trim());
  const extraKeys = Object.keys(sections).filter(
    (k) => !SECTION_ORDER.includes(k) && sections[k]?.trim()
  );
  return [...orderedKeys, ...extraKeys]
    .map((k) => sections[k].trim())
    .join("\n\n");
}

/* ------------------------------------------------------------------ */
/*  SectionCard — label discret + edition au curseur (pas de crayon)   */
/* ------------------------------------------------------------------ */

interface SectionCardProps {
  sectionKey: string;
  content: string;
  onContentChange: (key: string, newContent: string) => void;
  onDelete: (key: string) => void;
  onDismissField?: (fieldName: string) => void;
  onReplaceField?: (fieldName: string, value: string) => void;
}

function SectionCard({
  sectionKey,
  content,
  onContentChange,
  onDelete,
  onDismissField,
  onReplaceField,
}: SectionCardProps) {
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const label = getSectionLabel(sectionKey);
  const { title, body } = splitSectionTitle(content, sectionKey);

  const handleBodyChange = useCallback(
    (newBody: string) => {
      const full = title ? `${title}\n${newBody}` : newBody;
      onContentChange(sectionKey, full);
    },
    [title, sectionKey, onContentChange]
  );

  const handleCopy = async () => {
    await copyReportRich(body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative border-b border-border/50 transition-colors last:border-b-0 hover:bg-accent/20">
      {/* Section header : label + actions discretes (aucun crayon) */}
      <div className="flex items-center justify-between px-0 pb-1 pt-3">
        <span className="text-[0.68rem] font-bold uppercase tracking-widest text-muted-foreground">
          {label}
        </span>
        <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-7 w-7", copied && "text-success")}
            onClick={handleCopy}
            title={`Copier ${label}`}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 hover:text-destructive"
            onClick={() => setConfirmDelete(true)}
            title={`Supprimer ${label}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="my-2 flex items-center gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
          <span className="flex-1 text-sm text-destructive">
            Supprimer &laquo;&nbsp;{label}&nbsp;&raquo; ?
          </span>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              onDelete(sectionKey);
              setConfirmDelete(false);
            }}
          >
            Supprimer
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirmDelete(false)}
          >
            Annuler
          </Button>
        </div>
      )}

      {/* Contenu : editable directement au clic */}
      <div className="pb-4">
        <InlineSectionEditor
          value={body}
          onChange={handleBodyChange}
          onReplaceField={onReplaceField}
          onDismissField={onDismissField}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main ReportPanel                                                   */
/* ------------------------------------------------------------------ */

interface ReportPanelProps {
  report: string | null;
  onReportChange: (report: string) => void;
  organeDetecte: string;
}

export default function ReportPanel({
  report,
  onReportChange,
  organeDetecte,
}: ReportPanelProps) {
  const [rawSections, setRawSections] = useState<Record<string, string> | null>(null);
  const [loadingSections, setLoadingSections] = useState(false);
  const [copied, setCopied] = useState(false);

  const { sections, push: pushUndo, replace: replaceUndo, undo, redo, canUndo, canRedo } =
    useUndoStack(rawSections);

  const aCompleterCount = useMemo(() => {
    if (!report) return 0;
    return countACompleter(report);
  }, [report]);

  const isUserEditRef = useRef(false);
  const lastEditRef = useRef<{ key: string; t: number }>({ key: "", t: 0 });

  const fetchSections = useCallback(async () => {
    if (!report) return;
    setLoadingSections(true);
    try {
      const result = await getSections(report);
      setRawSections(result.sections);
    } catch {
      setRawSections(null);
    } finally {
      setLoadingSections(false);
    }
  }, [report]);

  useEffect(() => {
    if (report && !isUserEditRef.current) {
      fetchSections();
    }
    isUserEditRef.current = false;
  }, [report]); // eslint-disable-line react-hooks/exhaustive-deps

  // Raccourcis clavier undo/redo
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          redo();
        } else {
          undo();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [undo, redo]);

  // Synchroniser l'undo stack vers le rapport parent
  useEffect(() => {
    if (sections && isUserEditRef.current) {
      onReportChange(rebuildReport(sections));
    }
  }, [sections]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSectionChange = useCallback(
    (key: string, newContent: string) => {
      if (!sections) return;
      const updated = { ...sections, [key]: newContent };
      // Coalescence : la frappe continue dans une meme section ne cree
      // qu'un seul point d'annulation (undo par mot/pause, pas par lettre).
      const now = Date.now();
      const coalesce =
        lastEditRef.current.key === key && now - lastEditRef.current.t < 700;
      lastEditRef.current = { key, t: now };
      isUserEditRef.current = true;
      if (coalesce) {
        replaceUndo(updated);
      } else {
        pushUndo(updated);
      }
      onReportChange(rebuildReport(updated));
    },
    [sections, onReportChange, pushUndo, replaceUndo]
  );

  const handleSectionDelete = useCallback(
    (key: string) => {
      if (!sections) return;
      const updated = { ...sections };
      delete updated[key];
      lastEditRef.current = { key: "", t: 0 };
      pushUndo(updated);
      isUserEditRef.current = true;
      onReportChange(rebuildReport(updated));
    },
    [sections, onReportChange, pushUndo]
  );

  const _buildFieldRegex = (fieldName: string) =>
    new RegExp(
      `\\[(?:[AÀ]\\s*COMPL[EÉ]TER)\\s*:\\s*${fieldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\]`,
      "gi"
    );

  const handleDismissField = useCallback(
    (fieldName: string) => {
      if (!sections) return;
      const markerRegex = _buildFieldRegex(fieldName);
      const updated = { ...sections };
      for (const key of Object.keys(updated)) {
        const lines = updated[key].split("\n");
        const cleaned: string[] = [];
        for (const line of lines) {
          if (!markerRegex.test(line)) {
            cleaned.push(line);
            continue;
          }
          markerRegex.lastIndex = 0;
          const isTableRow = line.trimStart().startsWith("|");
          if (isTableRow) {
            cleaned.push(line.replace(markerRegex, "").trim());
          }
        }
        updated[key] = cleaned.join("\n").replace(/\n{3,}/g, "\n\n").trim();
      }
      lastEditRef.current = { key: "", t: 0 };
      pushUndo(updated);
      isUserEditRef.current = true;
      onReportChange(rebuildReport(updated));
    },
    [sections, onReportChange, pushUndo]
  );

  const handleReplaceField = useCallback(
    (fieldName: string, value: string) => {
      if (!sections) return;
      const regex = _buildFieldRegex(fieldName);
      const updated = { ...sections };
      for (const key of Object.keys(updated)) {
        updated[key] = updated[key].replace(regex, value);
      }
      lastEditRef.current = { key: "", t: 0 };
      pushUndo(updated);
      isUserEditRef.current = true;
      onReportChange(rebuildReport(updated));
    },
    [sections, onReportChange, pushUndo]
  );

  const handleCopyAll = async () => {
    if (!report) return;
    await copyReportRich(report);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const [exportError, setExportError] = useState<string | null>(null);

  const handleExportDocx = async () => {
    if (!report) return;
    setExportError(null);
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
      setExportError("Erreur lors de l'export Word");
    }
  };

  const handleExportTxt = () => {
    if (!report) return;
    const blob = new Blob([markdownToPlainText(report)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "compte-rendu.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const orderedSections = useMemo(() => {
    if (!sections) return [];
    return buildOrderedSections(sections);
  }, [sections]);

  // Empty state — accueil invitant à dicter
  if (!report) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="flex max-w-[360px] flex-col items-center gap-5 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <FileText className="h-8 w-8" />
          </div>
          <div className="space-y-1.5">
            <h2 className="font-heading text-lg font-bold tracking-tight text-foreground">
              Votre compte-rendu apparaitra ici
            </h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Dictez votre observation ou importez un fichier audio depuis le
              panneau de gauche&nbsp;: MARC structure le compte-rendu
              automatiquement.
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Mic className="h-3.5 w-3.5 text-primary" />
              Maintenir Espace
            </span>
            <span className="h-3 w-px bg-border" />
            <span className="inline-flex items-center gap-1.5">
              <Upload className="h-3.5 w-3.5 text-primary" />
              Importer un audio
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 pb-4">
        <div className="flex items-center gap-2.5">
          <h2 className="text-base font-bold tracking-tight">Compte-rendu</h2>
          {organeDetecte && (
            <Badge variant="default" className="text-[0.7rem]">
              {organeDetecte}
            </Badge>
          )}
          {aCompleterCount > 0 && (
            <Badge variant="warning" className="gap-1.5 text-[0.7rem]">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" />
              {aCompleterCount} champ{aCompleterCount > 1 ? "s" : ""} obligatoire{aCompleterCount > 1 ? "s" : ""}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="flex items-center gap-0.5 border-r pr-2 mr-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={undo}
              disabled={!canUndo}
              title="Annuler (Ctrl+Z)"
            >
              <Undo2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={redo}
              disabled={!canRedo}
              title="Retablir (Ctrl+Shift+Z)"
            >
              <Redo2 className="h-4 w-4" />
            </Button>
          </div>
          <Button
            variant="outline"
            size="sm"
            className={cn(copied && "text-success border-success/30")}
            onClick={handleCopyAll}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
            {copied ? "Copie !" : "Copier tout"}
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportTxt}>
            <FileType className="h-3.5 w-3.5" />
            .txt
          </Button>
          <Button size="sm" onClick={handleExportDocx}>
            <FileDown className="h-3.5 w-3.5" />
            .docx
          </Button>
        </div>
      </div>

      {/* Error banner */}
      {exportError && (
        <div className="mb-3 flex items-center justify-between rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <span>{exportError}</span>
          <button onClick={() => setExportError(null)} className="ml-2 font-bold">&times;</button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto pb-10 scrollbar-thin">
        <div className="mx-auto max-w-[860px] rounded-md border bg-card p-6 shadow-sm sm:p-10 lg:p-12">
          {loadingSections ? (
            <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
              <div className="h-6 w-6 animate-spin-slow rounded-full border-[2.5px] border-muted border-t-primary" />
              <span className="text-sm font-medium">
                Analyse des sections...
              </span>
            </div>
          ) : sections && orderedSections.length > 0 ? (
            <div className="flex flex-col">
              {orderedSections.map(({ key, content }) => (
                <SectionCard
                  key={key}
                  sectionKey={key}
                  content={content}
                  onContentChange={handleSectionChange}
                  onDelete={handleSectionDelete}
                  onDismissField={handleDismissField}
                  onReplaceField={handleReplaceField}
                />
              ))}
            </div>
          ) : (
            <MarkdownReport content={report} />
          )}
        </div>

        {/* Codification ADICAP / SNOMED (auto, copiable) */}
        <CodificationPanel report={report} organe={organeDetecte} />
      </div>
    </div>
  );
}
