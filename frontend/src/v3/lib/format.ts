// Petits formateurs et helpers DOM partagés par les composants.
import type { Projet, SourceRef } from "../types";

export const chrono = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

export const duree = (ms?: number | null) => (ms == null ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} s`);

export function focaliserTrou(id: string) {
  const b = document.querySelector<HTMLElement>(`[data-trou="${id}"]`);
  b?.focus();
  b?.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

export interface Agregat { source: SourceRef; nb: number }

/** Sources externes citées (hors dictée), dédupliquées, triées par fiabilité puis fréquence. */
export function agregerSources(p: Projet): Agregat[] {
  const map = new Map<string, Agregat>();
  const ajouter = (s: SourceRef) => {
    if (s.kind === "dictee") return;
    const k = `${s.kind}:${s.ref}`;
    const a = map.get(k);
    if (a) a.nb++;
    else map.set(k, { source: s, nb: 1 });
  };
  p.elements.forEach((e) => e.sources.forEach(ajouter));
  p.alertes.forEach((a) => a.sources.forEach(ajouter));
  p.codes.forEach((c) => c.sources.forEach(ajouter));
  p.corrections.forEach((c) => c.sources.forEach(ajouter));
  const rang = { A: 0, B: 1, C: 2, D: 3 } as Record<string, number>;
  return [...map.values()].sort((a, b) => (rang[a.source.fiabilite ?? "D"] ?? 4) - (rang[b.source.fiabilite ?? "D"] ?? 4) || b.nb - a.nb);
}
