import {
  useState,
  useMemo,
  useCallback,
  useEffect,
  useRef,
} from "react";
import {
  Pencil,
  Copy,
  Check,
  Trash2,
  FileDown,
  FileText,
  FileType,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { exportDocx, getSections } from "../services/api";
import type { DonneeManquante } from "../services/api";

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
/*  Markdown preprocessing                                             */
/* ------------------------------------------------------------------ */

const A_COMPLETER_REGEX = /\[(?:[AÀ]\s*COMPL[EÉ]TER)\s*:\s*([^\]]+)\]/gi;

/**
 * Pre-process ACP markdown conventions into standard HTML
 * that react-markdown + rehype-raw can render.
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
/*  MarkdownReport component                                           */
/* ------------------------------------------------------------------ */

function MarkdownReport({ content }: { content: string }) {
  const processed = useMemo(() => preprocessMarkdown(content), [content]);

  return (
    <div className="report-typography">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          // Style tables properly
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
          // Render [A COMPLETER] fields as styled inline elements
          span: ({ className, children, ...props }) => {
            if (className === "acp-missing") {
              return (
                <span className="inline-block rounded border border-dashed border-amber-500 bg-amber-500/10 px-2 py-0.5 text-amber-300 dark:text-amber-400">
                  {children}
                </span>
              );
            }
            return <span className={className} {...props}>{children}</span>;
          },
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section utilities                                                  */
/* ------------------------------------------------------------------ */

/**
 * Retire la premiere ligne du contenu si c'est un titre de section
 * (ex: **__CONCLUSION :__**) pour eviter le doublon avec le label du SectionCard.
 */
function stripSectionTitle(content: string, sectionKey: string): string {
  const lines = content.split("\n");
  if (lines.length === 0) return content;

  const firstLine = lines[0].trim().toLowerCase()
    .replace(/[*_#:]/g, "")
    .trim();

  // Verifier si la premiere ligne est le titre de cette section
  const sectionNames: Record<string, string[]> = {
    titre: [],  // ne pas toucher au titre principal
    renseignements_cliniques: ["renseignements cliniques", "renseignement clinique"],
    macroscopie: ["macroscopie", "examen macroscopique"],
    microscopie: ["microscopie", "etude histologique", "l'etude histologique", "letude histologique"],
    ihc: ["immunomarquage", "immunohistochimie"],
    biologie_moleculaire: ["biologie moleculaire"],
    conclusion: ["conclusion"],
  };

  const names = sectionNames[sectionKey];
  if (!names || names.length === 0) return content;

  for (const name of names) {
    if (firstLine.includes(name)) {
      // Retirer la premiere ligne
      return lines.slice(1).join("\n").trimStart();
    }
  }

  return content;
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
  for (const key of Object.keys(sections)) {
    if (!SECTION_ORDER.includes(key) && sections[key]?.trim()) {
      result.push({ key, content: sections[key] });
    }
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
/*  SectionCard                                                        */
/* ------------------------------------------------------------------ */

interface SectionCardProps {
  sectionKey: string;
  content: string;
  onContentChange: (key: string, newContent: string) => void;
  onDelete: (key: string) => void;
}

function SectionCard({
  sectionKey,
  content,
  onContentChange,
  onDelete,
}: SectionCardProps) {
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const editRef = useRef<HTMLDivElement>(null);

  const label = SECTION_LABELS[sectionKey] ?? sectionKey;
  const displayContent = stripSectionTitle(content, sectionKey);

  const handleStartEdit = () => {
    setEditing(true);
  };

  const handleSave = () => {
    if (editRef.current) {
      const newText = editRef.current.innerText;
      onContentChange(sectionKey, newText);
    }
    setEditing(false);
  };

  const handleCancel = () => {
    setEditing(false);
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(displayContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative border-b border-border/50 transition-colors last:border-b-0 hover:bg-accent/30">
      {/* Section header */}
      <div className="flex items-center justify-between px-0 pb-1 pt-3">
        <span className="text-[0.68rem] font-bold uppercase tracking-widest text-muted-foreground">
          {label}
        </span>
        <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {!editing ? (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={handleStartEdit}
                title={`Modifier ${label}`}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
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
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={handleCancel}>
                Annuler
              </Button>
              <Button size="sm" onClick={handleSave}>
                Enregistrer
              </Button>
            </>
          )}
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

      {/* Content - editable inline (no raw markdown) */}
      <div className="pb-4">
        {editing ? (
          <div
            ref={editRef}
            contentEditable
            suppressContentEditableWarning
            className="report-typography rounded-md border-2 border-primary/30 bg-background p-3 outline-none focus:border-primary"
            onKeyDown={(e) => {
              if (e.key === "Escape") handleCancel();
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                handleSave();
              }
            }}
            dangerouslySetInnerHTML={{
              __html: preprocessMarkdown(displayContent)
                ? (() => {
                    const processed = preprocessMarkdown(displayContent);
                    // Simple render for editable - strip [A COMPLETER] spans
                    return processed
                      .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
                      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                      .replace(/\*(.+?)\*/g, "<em>$1</em>")
                      .replace(/\n/g, "<br>");
                  })()
                : "",
            }}
          />
        ) : (
          <MarkdownReport content={displayContent} />
        )}
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
  donneesManquantes: DonneeManquante[];
  organeDetecte: string;
}

export default function ReportPanel({
  report,
  onReportChange,
  donneesManquantes: _donneesManquantes,
  organeDetecte,
}: ReportPanelProps) {
  void _donneesManquantes;
  const [sections, setSections] = useState<Record<string, string> | null>(null);
  const [loadingSections, setLoadingSections] = useState(false);
  const [copied, setCopied] = useState(false);

  const aCompleterCount = useMemo(() => {
    if (!report) return 0;
    return countACompleter(report);
  }, [report]);

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

  useEffect(() => {
    if (report) {
      fetchSections();
    }
  }, [report]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSectionChange = useCallback(
    (key: string, newContent: string) => {
      if (!sections) return;
      const updated = { ...sections, [key]: newContent };
      setSections(updated);
      onReportChange(rebuildReport(updated));
    },
    [sections, onReportChange]
  );

  const handleSectionDelete = useCallback(
    (key: string) => {
      if (!sections) return;
      const updated = { ...sections };
      delete updated[key];
      setSections(updated);
      onReportChange(rebuildReport(updated));
    },
    [sections, onReportChange]
  );

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
      // Silent fail
    }
  };

  const handleExportTxt = () => {
    if (!report) return;
    const blob = new Blob([report], { type: "text/plain;charset=utf-8" });
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

  // Empty state
  if (!report) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <FileText className="h-10 w-10 text-muted-foreground/30" />
          <p className="max-w-[280px] text-sm text-muted-foreground">
            Le compte-rendu formate apparaitra ici apres transcription.
          </p>
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
              {aCompleterCount} champ{aCompleterCount > 1 ? "s" : ""} a
              completer
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
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

      {/* Content */}
      <div className="flex-1 overflow-y-auto pb-10">
        <div className="mx-auto max-w-[860px] rounded-md border bg-card p-12 shadow-sm">
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
                />
              ))}
            </div>
          ) : (
            <MarkdownReport content={report} />
          )}
        </div>
      </div>
    </div>
  );
}
