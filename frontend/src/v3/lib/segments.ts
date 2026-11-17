// Découpe d'un texte en segments surlignés (empans de dictée, corrections). Pur et testable.
export interface Empan { debut: number; fin: number; cle: string }
export interface Segment { texte: string; cle?: string }

/** Bornes invalides ou chevauchantes ignorées : on ne surligne jamais de façon approximative. */
export function segmenter(texte: string, empans: Empan[]): Segment[] {
  const valides = empans
    .filter((e) => Number.isInteger(e.debut) && Number.isInteger(e.fin) && e.debut >= 0 && e.fin > e.debut && e.fin <= texte.length)
    .sort((a, b) => a.debut - b.debut);
  const out: Segment[] = [];
  let pos = 0;
  for (const e of valides) {
    if (e.debut < pos) continue;
    if (e.debut > pos) out.push({ texte: texte.slice(pos, e.debut) });
    out.push({ texte: texte.slice(e.debut, e.fin), cle: e.cle });
    pos = e.fin;
  }
  if (pos < texte.length) out.push({ texte: texte.slice(pos) });
  return out;
}
