// Courbe d'activité sobre, faite main en SVG : trois séries distinguées par le trait (plein, tiret, pointillé), jamais par la couleur seule.
import { useState } from "react";
import { jourCourt } from "./format";
import type { JourSerie } from "./types";

const SERIES = [
  { cle: "projets_v3", nom: "Projets v3", trait: "none", epaisseur: 1.9, opacite: 1 },
  { cle: "comptes_rendus_anciens", nom: "Comptes rendus (ancienne version)", trait: "5 4", epaisseur: 1.6, opacite: 1 },
  { cle: "utilisateurs_actifs", nom: "Utilisateurs actifs", trait: "1.5 3.5", epaisseur: 1.6, opacite: 0.85 },
] as const;

export default function Courbe({ serie }: { serie: JourSerie[] }) {
  const [survol, setSurvol] = useState<number | null>(null);
  const W = 720, H = 200, G = 36, B = 22, T = 8;
  const max = Math.max(1, ...serie.flatMap((j) => SERIES.map((s) => j[s.cle])));
  const haut = Math.ceil(max / 5) * 5 || 5;
  const n = serie.length;
  const x = (i: number) => G + (n <= 1 ? 0 : (i / (n - 1)) * (W - G - 8));
  const y = (v: number) => T + (1 - v / haut) * (H - T - B);
  const pick = survol !== null ? serie[survol] : null;
  const resume = `Activité sur ${n} jours : ${serie.reduce((a, j) => a + j.projets_v3, 0)} projets v3, ${serie.reduce((a, j) => a + j.comptes_rendus_anciens, 0)} comptes rendus de l'ancienne version.`;
  return (
    <figure className="m-0">
      <figcaption className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 text-[12px]">
        <span className="flex flex-wrap gap-x-5 gap-y-1 adm-doux">
          {SERIES.map((s) => (
            <span key={s.cle} className="inline-flex items-center gap-2">
              <svg width="22" height="6" aria-hidden="true"><line x1="0" x2="22" y1="3" y2="3" stroke="var(--a-ink)" strokeWidth={s.epaisseur} strokeDasharray={s.trait} opacity={s.opacite} /></svg>{s.nom}
            </span>
          ))}
        </span>
        <span aria-live="polite" className="num min-h-[18px]">
          {pick ? `${jourCourt(pick.jour)} : ${pick.projets_v3} projets v3 · ${pick.comptes_rendus_anciens} anciens · ${pick.utilisateurs_actifs} actifs` : " "}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={resume} onMouseLeave={() => setSurvol(null)}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={G} x2={W - 8} y1={y(haut * f)} y2={y(haut * f)} stroke="var(--a-line)" strokeWidth="1" />
            <text x={G - 6} y={y(haut * f) + 3.5} fontSize="10" textAnchor="end" fill="var(--a-faint)">{Math.round(haut * f)}</text>
          </g>
        ))}
        {SERIES.map((s) => (
          <polyline key={s.cle} points={serie.map((j, i) => `${x(i)},${y(j[s.cle])}`).join(" ")}
            stroke="var(--a-ink)" strokeWidth={s.epaisseur} strokeDasharray={s.trait === "none" ? undefined : s.trait} opacity={s.opacite} />
        ))}
        {pick && <line x1={x(survol!)} x2={x(survol!)} y1={T} y2={H - B} stroke="var(--a-faint)" strokeWidth="1" />}
        {serie.map((j, i) => (
          <rect key={j.jour} x={x(i) - (W - G) / n / 2} y={T} width={(W - G) / n} height={H - T - B} fill="transparent" onMouseEnter={() => setSurvol(i)} />
        ))}
        <text x={G} y={H - 6} fontSize="10" fill="var(--a-faint)">{n ? jourCourt(serie[0].jour) : ""}</text>
        <text x={W - 8} y={H - 6} fontSize="10" textAnchor="end" fill="var(--a-faint)">{n ? jourCourt(serie[n - 1].jour) : ""}</text>
      </svg>
    </figure>
  );
}
