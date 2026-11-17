// Sources citées par le projet (éléments, alertes, codes, corrections) : titre entier, extrait, fiabilité en mots ; un clic ouvre la fiche.
import { useMemo } from "react";
import { agregerSources } from "../lib/format";
import type { Projet, SourceRef } from "../types";
import { SourceLien } from "./Source";

export default function OngletSources({ projet, onConsulte }: { projet: Projet; onConsulte: (s: SourceRef) => void }) {
  const liste = useMemo(() => agregerSources(projet), [projet]);
  if (liste.length === 0) return <p className="px-5 py-6 text-[15px] text-[var(--mute)]">Aucune source externe citée. Les éléments reposent uniquement sur la dictée.</p>;
  return (
    <div className="px-5 py-5">
      <ul className="space-y-2.5">
        {liste.map(({ source: s, nb }) => (
          <li key={`${s.kind}${s.ref}`} className="enter rounded-xl border border-[var(--line)] bg-[var(--card)] px-4 py-3.5">
            <SourceLien source={s} onConsulte={onConsulte} />
            <p className="mt-1.5 text-[12px] text-[var(--faint)]">Citée {nb} fois</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
