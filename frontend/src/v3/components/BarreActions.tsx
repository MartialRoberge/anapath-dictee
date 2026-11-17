// Barre d'actions : Copier tout, Exporter DOCX, Compléter par la voix, feedback +/- avec motif en enum.
import { useEffect, useRef, useState } from "react";
import { trousOuverts, alertesOuvertes, type ProjetLocal } from "../lib/session";
import { touche } from "../lib/raccourcis";
import Completer from "./Completer";
import BlocConformite from "./conformite/BlocConformite";

export const MOTIFS = {
  plus: [["fidele", "Fidèle à ma dictée"], ["gain_temps", "Gain de temps"], ["codes_justes", "Codes pertinents"], ["alertes_utiles", "Alertes utiles"]],
  moins: [["info_inventee", "Information inventée"], ["info_omise", "Information omise"], ["codes_errones", "Codes erronés"], ["alertes_inutiles", "Alertes inutiles"], ["mise_en_forme", "Mise en forme"], ["trop_lent", "Trop lent"]],
} as const;

interface Props {
  local: ProjetLocal;
  occupe: boolean;
  exportEnCours: boolean;
  onCopier: () => void;
  onExporter: () => void;
  onCompleter: (texte: string) => void;
  onFeedback: (sens: "plus" | "moins", motif: string) => void;
  onNotifier: (m: string) => void;
}

export function Feedback({ local, onFeedback }: { local: ProjetLocal; onFeedback: Props["onFeedback"] }) {
  const [sens, setSens] = useState<"plus" | "moins" | null>(null);
  const racine = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sens) return;
    const f = (e: MouseEvent) => { if (!racine.current?.contains(e.target as Node)) setSens(null); };
    document.addEventListener("mousedown", f);
    return () => document.removeEventListener("mousedown", f);
  }, [sens]);
  const fb = local.feedback;
  return (
    <div ref={racine} className="relative flex items-center gap-0.5" onKeyDown={(e) => e.key === "Escape" && setSens(null)}>
      {fb ? <span className="px-2 text-[12.5px] text-[var(--mute)]" role="status">Merci pour votre retour</span> : (
        <>
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={sens === "plus"} onClick={() => setSens(sens === "plus" ? null : "plus")}>Utile</button>
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={sens === "moins"} onClick={() => setSens(sens === "moins" ? null : "moins")}>À améliorer</button>
        </>
      )}
      {sens && !fb && (
        <div className="pop bottom-full right-0 mb-2" role="group" aria-label={sens === "plus" ? "Ce qui a bien fonctionné" : "Ce qui peut être amélioré"}>
          <p className="label px-2.5 pb-1 pt-1.5">{sens === "plus" ? "Ce qui a bien fonctionné" : "Ce qui doit être amélioré"}</p>
          {MOTIFS[sens].map(([cle, titre]) => (
            <button key={cle} type="button" className="opt" onClick={() => { onFeedback(sens, cle); setSens(null); }}>{titre}</button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BarreActions(p: Props) {
  const trous = trousOuverts(p.local);
  const alertes = alertesOuvertes(p.local).length;
  return (
    <div className="relative border-t border-[var(--line)] bg-[color-mix(in_srgb,var(--paper)_92%,white)] px-4 py-3 sm:px-8" role="toolbar" aria-label="Actions sur le projet">
      <div className="mx-auto max-w-[760px]">
        <BlocConformite
          local={p.local} occupe={p.occupe}
          resume={<span className="num">{trous > 0 ? <b className="font-semibold text-[var(--amber)]">{trous} à compléter</b> : "Aucun trou"} · {alertes > 0 ? <b className="font-semibold text-[var(--ink)]">{alertes} à vérifier</b> : "rien à vérifier"}</span>}
          avant={<>
            <Completer disabled={p.occupe} onEnvoyer={p.onCompleter} onNotifier={p.onNotifier} />
            <button type="button" className="btn" disabled={p.exportEnCours || p.occupe} onClick={p.onExporter} aria-keyshortcuts="Alt+X" title={`Exporter en DOCX · ${touche("X")}`}>{p.exportEnCours ? "Export…" : "Exporter DOCX"}</button>
          </>}
          fin={<button type="button" className="btn btn-primary" onClick={p.onCopier} aria-keyshortcuts="Alt+C">Copier tout <span className="kbd">{touche("C")}</span></button>}
        />
      </div>
    </div>
  );
}
