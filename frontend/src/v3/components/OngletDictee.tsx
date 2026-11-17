// Élément sélectionné : explication, confiance, sources, empan exact de dictée surligné,
// dictée brute vs corrigée, corrections phonétiques acceptables ou rejetables avec candidats.
import { useMemo } from "react";
import { segmenter, type Empan } from "../lib/segments";
import type { ProjetLocal } from "../lib/session";
import { texteElement } from "../lib/session";
import type { Correction, Element, SourceRef } from "../types";
import { SourceLien } from "./Source";

const NIVEAU = { haute: "Confiance haute", moyenne: "Confiance moyenne", basse: "Confiance basse" } as const;
const STATUT = { dicte: "Dicté tel quel", reformule: "Reformulé", normalise: "Normalisé", a_completer: "À compléter" } as const;

interface Props {
  local: ProjetLocal;
  element: Element | null;
  correctionActive: string | null;
  onCorrectionActive: (id: string | null) => void;
  onDecision: (c: Correction, choix: string | "original") => void;
  onConsulte: (s: SourceRef) => void;
}

export default function OngletDictee({ local, element, correctionActive, onCorrectionActive, onDecision, onConsulte }: Props) {
  const { dictee, corrections } = local.projet;
  const empansDictee: Empan[] = useMemo(
    () => (element?.sources ?? []).filter((s) => s.kind === "dictee" && s.debut != null && s.fin != null).map((s, i) => ({ debut: s.debut!, fin: s.fin!, cle: `d${i}` })),
    [element],
  );
  const segCorrigee = useMemo(() => segmenter(dictee.corrigee, empansDictee), [dictee.corrigee, empansDictee]);
  const segBrute = useMemo(() => segmenter(dictee.brute, corrections.map((c) => ({ debut: c.debut, fin: c.fin, cle: c.id }))), [dictee.brute, corrections]);
  const autres = (element?.sources ?? []).filter((s) => s.kind !== "dictee");

  return (
    <div className="space-y-7 px-5 py-5">
      {element ? (
        <section className="enter" aria-label="Élément sélectionné">
          <p className="label mb-2">Élément sélectionné</p>
          <p className="font-medium leading-snug text-[15px]">{texteElement(local, element)}</p>
          <p className="mt-2 text-[13px] text-[var(--mute)]">
            {STATUT[element.statut]}
            {element.type !== "trou" && <> · {NIVEAU[element.niveau]} <span className="num">({Math.round(element.confiance * 100)} %)</span></>}
          </p>
          {element.explication && <p className="mt-2.5 text-[13px] leading-relaxed">{element.explication}</p>}
          {autres.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {autres.map((s, i) => (
                <li key={i}><SourceLien source={s} onConsulte={s.kind === "agent" ? undefined : onConsulte} /></li>
              ))}
            </ul>
          )}
          {empansDictee.length === 0 && element.type !== "titre" && <p className="mt-3 text-[13px] text-[var(--faint)]">Aucun passage de la dictée n'est rattaché à cet élément.</p>}
        </section>
      ) : (
        <p className="text-[13px] leading-relaxed text-[var(--mute)]">Cliquez sur un élément du projet pour voir d'où il vient, sa confiance et le passage exact de la dictée.</p>
      )}

      <section aria-label="Dictée corrigée">
        <p className="label mb-2">Dictée corrigée</p>
        <p className="rounded-xl border border-[var(--line)] bg-[var(--card)] p-4 text-[15px] leading-[1.7]">
          {segCorrigee.map((s, i) => s.cle ? <mark key={i} className="rounded-[3px] bg-[var(--mark)] px-px text-[var(--ink)]">{s.texte}</mark> : <span key={i}>{s.texte}</span>)}
        </p>
      </section>

      <section aria-label="Dictée brute">
        <p className="label mb-2">Dictée brute (reconnaissance vocale)</p>
        <p className="rounded-xl border border-[var(--line)] bg-[var(--card)] p-4 text-[15px] leading-[1.7] text-[var(--mute)]">
          {segBrute.map((s, i) => s.cle ? (
            <button key={i} type="button" onClick={() => onCorrectionActive(correctionActive === s.cle ? null : s.cle!)}
              className={`inline rounded-[3px] px-px underline decoration-[var(--amber-line)] underline-offset-[3px] ${correctionActive === s.cle ? "bg-[var(--amber-soft)] text-[var(--ink)]" : "text-[var(--ink)]"}`}>{s.texte}</button>
          ) : <span key={i}>{s.texte}</span>)}
        </p>
      </section>

      {corrections.length > 0 && (
        <section aria-label="Corrections phonétiques">
          <p className="label mb-2.5">Corrections phonétiques · {corrections.length}</p>
          <ul className="space-y-2.5">
            {corrections.map((c) => {
              const d = local.corrections[c.id];
              const appliquee = d ? d.appliquee : c.appliquee;
              const courant = appliquee ? (d?.choix ?? c.corrige) : c.original;
              return (
                <li key={c.id} className={`rounded-xl border bg-[var(--card)] px-4 py-3.5 ${correctionActive === c.id ? "border-[var(--ink)]" : "border-[var(--line)]"}`} onClick={() => onCorrectionActive(c.id)}>
                  <p className="text-[15px]"><span className="text-[var(--faint)] line-through">{c.original}</span> <span className="text-[var(--faint)]">devient</span> <span className="font-medium">{courant}</span></p>
                  <p className="mt-1 text-[12px] leading-relaxed text-[var(--mute)]">{c.raison} · <span className="num">{Math.round(c.confiance * 100)} %</span></p>
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    <button type="button" className="btn btn-sm" aria-pressed={appliquee && !d?.choix} onClick={(e) => { e.stopPropagation(); onDecision(c, c.corrige); }}>Accepter</button>
                    <button type="button" className="btn btn-sm" aria-pressed={!appliquee} onClick={(e) => { e.stopPropagation(); onDecision(c, "original"); }}>Rejeter</button>
                    {c.candidats.filter((k) => k !== c.corrige).map((k) => (
                      <button key={k} type="button" className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); onDecision(c, k); }}>{k}</button>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
