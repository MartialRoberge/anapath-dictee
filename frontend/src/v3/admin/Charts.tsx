// Graphiques fins faits main en SVG (pas de bibliotheque).
import { useState } from "react";
import type { JourStat } from "./types";

/** Barres verticales en filets fins, une par jour (style Harvey). */
export function BarresFilets({ data, cle, titre }: { data: JourStat[]; cle: "projets" | "utilisateurs"; titre: string }) {
  const [survol, setSurvol] = useState<number | null>(null);
  const W = 640, H = 150, base = H - 18;
  const max = Math.max(1, ...data.map((d) => d[cle]));
  const pas = W / Math.max(1, data.length);
  const larg = Math.min(4, Math.max(1.5, pas * 0.4));
  const pick = survol !== null ? data[survol] : null;
  return (
    <figure className="m-0">
      <div className="mb-2 flex items-baseline justify-between text-[12px]" style={{ color: "var(--adm-doux)" }}>
        <span>{titre}</span>
        <span aria-live="polite" style={{ color: "var(--adm-encre)" }}>{pick ? `${pick.jour} : ${pick[cle]}` : `max ${max}`}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${titre} par jour`}>
        {[0, 0.5, 1].map((f) => <line key={f} x1="0" x2={W} y1={base - f * (base - 6)} y2={base - f * (base - 6)} stroke="var(--adm-filet)" strokeWidth="1" />)}
        {data.map((d, i) => {
          const h = (d[cle] / max) * (base - 6);
          const x = i * pas + pas / 2 - larg / 2;
          return (
            <g key={d.jour} onMouseEnter={() => setSurvol(i)} onMouseLeave={() => setSurvol(null)}>
              <rect x={i * pas} y="0" width={pas} height={base} fill="transparent" />
              <rect className="adm-barre" x={x} y={base - h} width={larg} height={Math.max(h, 0)} fill="var(--adm-accent)" opacity={survol === null || survol === i ? 1 : 0.35} style={{ animationDelay: `${Math.min(i * 6, 160)}ms` }} />
            </g>
          );
        })}
        <text x="0" y={H - 3} fontSize="10" fill="var(--adm-doux)">{data[0]?.jour.slice(5)}</text>
        <text x={W} y={H - 3} fontSize="10" textAnchor="end" fill="var(--adm-doux)">{data[data.length - 1]?.jour.slice(5)}</text>
      </svg>
    </figure>
  );
}

/** Barres horizontales fines (top utilisateurs, organes, retouches). */
export function BarresH({ lignes, suffixe = "" }: { lignes: { label: string; valeur: number; note?: string }[]; suffixe?: string }) {
  const max = Math.max(1, ...lignes.map((l) => l.valeur));
  return (
    <ul className="m-0 list-none space-y-3 p-0">
      {lignes.map((l, i) => (
        <li key={l.label}>
          <div className="mb-1 flex justify-between gap-3 text-[13px]">
            <span className="truncate">{l.label}</span>
            <span className="tabular-nums" style={{ color: "var(--adm-doux)" }}>{l.note ?? `${l.valeur}${suffixe}`}</span>
          </div>
          <svg viewBox="0 0 100 2" preserveAspectRatio="none" className="block h-[3px] w-full" aria-hidden="true">
            <rect width="100" height="2" fill="var(--adm-filet)" />
            <rect className="adm-hbar" width={(l.valeur / max) * 100} height="2" fill="var(--adm-encre)" style={{ animationDelay: `${i * 40}ms` }} />
          </svg>
        </li>
      ))}
    </ul>
  );
}

/** Comparaison resolues (encre) / ignorees (accent) : une barre empilee par ligne + taux d'ignore. */
export function Comparaison({ lignes }: { lignes: { label: string; a: number; b: number }[] }) {
  return (
    <ul className="m-0 list-none space-y-3 p-0">
      {lignes.map((l, i) => {
        const tot = l.a + l.b;
        const pct = tot ? Math.round((l.b / tot) * 100) : 0;
        return (
          <li key={l.label}>
            <div className="mb-1 flex justify-between gap-3 text-[13px]">
              <span className="truncate">{l.label}</span>
              <span className="tabular-nums" style={{ color: pct >= 40 ? "var(--adm-accent)" : "var(--adm-doux)" }}>{l.a} / {l.b} · {pct} % ignorés</span>
            </div>
            <svg viewBox="0 0 100 2" preserveAspectRatio="none" className="block h-[3px] w-full" aria-hidden="true">
              <rect className="adm-hbar" width={tot ? (l.a / tot) * 100 : 0} height="2" fill="var(--adm-encre)" style={{ animationDelay: `${i * 40}ms` }} />
              <rect className="adm-hbar" x={tot ? (l.a / tot) * 100 : 0} width={tot ? (l.b / tot) * 100 : 0} height="2" fill="var(--adm-accent)" style={{ animationDelay: `${i * 40 + 60}ms` }} />
            </svg>
          </li>
        );
      })}
    </ul>
  );
}
