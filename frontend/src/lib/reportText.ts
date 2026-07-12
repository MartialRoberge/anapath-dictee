/**
 * Conversion du compte-rendu Markdown vers texte propre et HTML riche,
 * pour que la copie/le collage ne laisse jamais apparaître de marqueurs
 * Markdown (**, __, |, *) dans Word ou un éditeur texte.
 */

function stripInline(text: string): string {
  return text
    // titres **__X__** / __**X**__ / __X__ -> X
    .replace(/\*\*__(.+?)__\*\*/g, "$1")
    .replace(/__\*\*(.+?)\*\*__/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    // gras/italique
    .replace(/\*\*\*(.+?)\*\*\*/g, "$1")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    // marqueurs résiduels isolés
    .replace(/\*\*/g, "")
    .replace(/__/g, "");
}

function isTableRow(line: string): boolean {
  return line.trim().startsWith("|");
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes("-");
}

function tableCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => stripInline(c.trim()));
}

/** Markdown -> texte lisible (aucun marqueur Markdown résiduel). */
export function markdownToPlainText(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  for (const line of lines) {
    if (isTableSeparator(line)) continue;
    if (isTableRow(line)) {
      out.push(tableCells(line).join(" : "));
      continue;
    }
    out.push(stripInline(line.replace(/^#{1,6}\s+/, "")));
  }
  // collapse 3+ sauts de ligne
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inlineToHtml(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*__(.+?)__\*\*/g, "<b><u>$1</u></b>")
    .replace(/__\*\*(.+?)\*\*__/g, "<b><u>$1</u></b>")
    .replace(/__(.+?)__/g, "<u>$1</u>")
    .replace(/\*\*\*(.+?)\*\*\*/g, "<b><i>$1</i></b>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>");
}

/** Markdown -> HTML riche (collage formaté dans Word). */
export function markdownToHtml(md: string): string {
  const lines = md.split("\n");
  const html: string[] = [];
  let table: string[][] | null = null;

  const flushTable = () => {
    if (!table || table.length === 0) {
      table = null;
      return;
    }
    const rows = table
      .map(
        (cells) =>
          "<tr>" +
          cells.map((c) => `<td style="border:1px solid #ccc;padding:4px">${inlineToHtml(c)}</td>`).join("") +
          "</tr>",
      )
      .join("");
    html.push(`<table style="border-collapse:collapse">${rows}</table>`);
    table = null;
  };

  for (const line of lines) {
    if (isTableSeparator(line)) continue;
    if (isTableRow(line)) {
      (table ??= []).push(tableCells(line));
      continue;
    }
    flushTable();
    if (!line.trim()) {
      html.push("<br>");
      continue;
    }
    html.push(`<p style="margin:0 0 4px 0">${inlineToHtml(line.replace(/^#{1,6}\s+/, ""))}</p>`);
  }
  flushTable();
  return html.join("");
}

/** Copie le CR dans le presse-papier en texte propre + HTML riche. */
export async function copyReportRich(md: string): Promise<void> {
  const plain = markdownToPlainText(md);
  const html = markdownToHtml(md);
  try {
    if (navigator.clipboard && "write" in navigator.clipboard && typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/plain": new Blob([plain], { type: "text/plain" }),
          "text/html": new Blob([html], { type: "text/html" }),
        }),
      ]);
      return;
    }
  } catch {
    /* repli texte plain ci-dessous */
  }
  await navigator.clipboard.writeText(plain);
}
