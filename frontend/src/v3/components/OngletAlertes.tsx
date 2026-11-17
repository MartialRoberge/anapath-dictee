// À vérifier : alertes groupées par gravité. Un clic surligne les éléments concernés dans le document.
import { useState } from "react";
import type { DecisionAlerte } from "../lib/session";
import { touche } from "../lib/raccourcis";
import { alerteTextes } from "../lib/pourquoi";
import type { Alerte, SourceRef } from "../types";
import { ListeSources } from "./Source";

const GRAVITES: Array<{ cle: Alerte["gravite"]; titre: string; point: string }> = [
  { cle: "bloquant", titre: "Bloquant", point: "text-[var(--red)]" },
  { cle: "attention", titre: "Attention", point: "text-[var(--amber)]" },
  { cle: "info", titre: "Information", point: "text-[var(--faint)]" },
];

interface Props {
  alertes: Alerte[];
  decisions: Record<string, DecisionAlerte>;
  active: string | null;
  onActiver: (a: Alerte) => void;
  onDecider: (a: Alerte, d: DecisionAlerte | null) => void;
  onConsulte?: (s: SourceRef) => void;
}

function Carte({ a, d, active, onActiver, onDecider, onConsulte }: { a: Alerte; d?: DecisionAlerte; active: boolean; onActiver: Props["onActiver"]; onDecider: Props["onDecider"]; onConsulte?: Props["onConsulte"] }) {
  const t = alerteTextes(a);
  return (
    <li className={`enter rounded-xl border bg-[var(--card)] px-4 py-3.5 transition-colors ${active ? "border-[var(--ink)]" : "border-[var(--line)]"} ${d ? "opacity-60" : ""}`}>
      <button type="button" onClick={() => onActiver(a)} aria-pressed={active} className="block w-full text-left">
        <span className={`block text-[15px] font-medium leading-snug ${d ? "line-through decoration-[var(--faint)]" : ""}`}>{t.titre}</span>
        {t.pourquoi && <span className="mt-1.5 block text-[13px] leading-relaxed text-[var(--mute)]">{t.pourquoi}</span>}
        {t.calcul && <span className="num mt-1.5 block text-[13px] text-[var(--ink)]">{t.calcul}</span>}
        {t.action && <span className="mt-2 block text-[13px] leading-snug"><span className="text-[var(--faint)]">À faire : </span>{t.action}</span>}
      </button>
      <ListeSources sources={a.sources} onConsulte={onConsulte} />
      <div className="mt-3 flex items-center gap-1.5">
        {d ? (
          <>
            <span className="text-[12px] text-[var(--faint)]">{d === "resolue" ? "Résolue" : "Ignorée"}</span>
            <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={() => onDecider(a, null)}>Rouvrir</button>
          </>
        ) : (
          <>
            <button type="button" className="btn btn-sm" onClick={() => onDecider(a, "resolue")}>Résoudre{active && <> <span className="kbd">{touche("R")}</span></>}</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onDecider(a, "ignoree")}>Ignorer{active && <> <span className="kbd">{touche("I")}</span></>}</button>
            {a.element_ids.length > 0 && <span className="num ml-auto text-[12px] text-[var(--faint)]">{a.element_ids.length} élément{a.element_ids.length > 1 ? "s" : ""}</span>}
          </>
        )}
      </div>
    </li>
  );
}

export default function OngletAlertes({ alertes, decisions, active, onActiver, onDecider, onConsulte }: Props) {
  const [traitees, setTraitees] = useState(false);
  const ouvertes = alertes.filter((a) => !decisions[a.id]);
  const fermees = alertes.filter((a) => decisions[a.id]);
  if (alertes.length === 0) return <p className="px-5 py-6 text-[15px] leading-relaxed text-[var(--mute)]">Aucun point à vérifier signalé. Relisez tout de même le projet : la validation reste la vôtre.</p>;
  return (
    <div className="space-y-6 px-5 py-5">
      {ouvertes.length === 0 && <p className="text-[15px] text-[var(--mute)]">Tous les points sont traités. Vous pouvez valider : <span className="kbd">{touche("V")}</span></p>}
      {GRAVITES.map((g) => {
        const liste = ouvertes.filter((a) => a.gravite === g.cle);
        if (!liste.length) return null;
        return (
          <section key={g.cle} aria-label={g.titre}>
            <h3 className={`label mb-2.5 !font-semibold ${g.point}`}>{g.titre} <span className="num">· {liste.length}</span></h3>
            <ul className="space-y-2.5">{liste.map((a) => <Carte key={a.id} a={a} active={active === a.id} onActiver={onActiver} onDecider={onDecider} onConsulte={onConsulte} />)}</ul>
          </section>
        );
      })}
      {fermees.length > 0 && (
        <section>
          <button type="button" className="label hover:text-[var(--ink)]" aria-expanded={traitees} onClick={() => setTraitees(!traitees)}>
            Traités · {fermees.length} · {traitees ? "masquer" : "afficher"}
          </button>
          {traitees && <ul className="mt-2.5 space-y-2.5">{fermees.map((a) => <Carte key={a.id} a={a} d={decisions[a.id]} active={active === a.id} onActiver={onActiver} onDecider={onDecider} onConsulte={onConsulte} />)}</ul>}
        </section>
      )}
    </div>
  );
}
