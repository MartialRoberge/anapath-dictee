// Source citée (titre entier, extrait, fiabilité en mots) et panneau de consultation de sa fiche.
// Le SourceRef reste affiché même si la fiche n'est pas disponible : la consultation ne bloque jamais.
import { useEffect, useId, useRef, useState } from "react";
import { consulterSource } from "../lib/api";
import { aUneFiche, FIABILITE_PHRASE, formeExtrait, motFiabilite, type SourceDetail } from "../lib/sources";
import { useDialogue } from "../hooks/useDialogue";
import type { SourceRef } from "../types";

const TYPE_SOURCE: Record<SourceRef["kind"], string> = { dictee: "Dictée", kb: "Base de connaissances", regle: "Règle", agent: "Traitement automatique", web: "Site web" };

/** Extrait sous le titre : citation entre guillemets, ou localisation en petit. */
export function ExtraitSource({ s, className = "" }: { s: Pick<SourceRef, "kind" | "extrait">; className?: string }) {
  const e = formeExtrait(s);
  if (!e) return null;
  return <span className={`block break-words text-[12px] leading-snug text-[var(--faint)] ${e.type === "citation" ? "italic" : ""} ${className}`}>{e.type === "citation" ? `« ${e.texte} »` : e.texte}</span>;
}

/** Fiabilité écrite en mots, discrète (jamais une lettre seule). */
export function FiabiliteMots({ f, className = "" }: { f?: string | null; className?: string }) {
  const m = motFiabilite(f);
  return m ? <span className={`text-[12px] text-[var(--faint)] ${className}`}>{m}</span> : null;
}

/** Titre complet, extrait, fiabilité : un seul bouton qui ouvre la consultation. */
export function SourceLien({ source: s, onConsulte, titre }: { source: SourceRef; onConsulte?: (s: SourceRef) => void; titre?: string }) {
  const contenu = (
    <>
      <span className="block break-words text-[15px] font-medium leading-snug">{titre || s.libelle}</span>
      <ExtraitSource s={s} className="mt-0.5" />
      <FiabiliteMots f={s.fiabilite} className="mt-0.5 block" />
    </>
  );
  if (!onConsulte) return <span className="block min-w-0">{contenu}</span>;
  return (
    <button type="button" aria-haspopup="dialog" onClick={() => onConsulte(s)}
      className="block min-w-0 max-w-full rounded text-left decoration-[var(--line)] underline-offset-[3px] hover:[&>span:first-child]:underline">
      {contenu}
    </button>
  );
}

/** Liste de sources consultables (hors dictée) sous une alerte, un code ou une correction. */
export function ListeSources({ sources, onConsulte }: { sources: SourceRef[]; onConsulte?: (s: SourceRef) => void }) {
  const l = sources.filter((s) => s.kind !== "dictee" && s.kind !== "agent");
  if (!l.length || !onConsulte) return null;
  return (
    <ul className="mt-3 space-y-2" aria-label="Sources">
      {l.map((s) => <li key={`${s.kind}${s.ref}`}><SourceLien source={s} onConsulte={onConsulte} /></li>)}
    </ul>
  );
}

export type EtatFiche = { phase: "chargement" } | { phase: "ok"; fiche: SourceDetail } | { phase: "indisponible" };

export default function ConsultationSource({ source: s, onFermer }: { source: SourceRef; onFermer: () => void }) {
  const [etat, setEtat] = useState<EtatFiche>(() => (aUneFiche(s) ? { phase: "chargement" } : { phase: "indisponible" }));
  const racine = useRef<HTMLDivElement>(null);
  useDialogue(racine, onFermer);

  useEffect(() => {
    if (!aUneFiche(s)) return;
    const c = new AbortController();
    setEtat({ phase: "chargement" });
    consulterSource(s.ref, c.signal).then((fiche) => setEtat({ phase: "ok", fiche }), () => { if (!c.signal.aborted) setEtat({ phase: "indisponible" }); });
    return () => c.abort();
  }, [s]);

  return (
    <div className="modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onFermer(); }}>
      <FicheSource ref_={racine} source={s} etat={etat} onFermer={onFermer} />
    </div>
  );
}

/** Contenu du dialogue : dépend uniquement de la source citée et de l'état de la fiche (testable sans réseau). */
export function FicheSource({ ref_, source: s, etat, onFermer }: { ref_?: React.Ref<HTMLDivElement>; source: SourceRef; etat: EtatFiche; onFermer: () => void }) {
  const idTitre = useId();
  const fiche = etat.phase === "ok" ? etat.fiche : null;
  const titre = fiche?.titre || s.libelle;
  const f = fiche?.fiabilite ?? s.fiabilite;
  const url = fiche?.url ?? s.url ?? undefined;
  const lignes: Array<[string, string]> = [];
  if (fiche?.editeur) lignes.push(["Éditeur", fiche.editeur]);
  if (fiche?.date) lignes.push(["Date", fiche.date]);
  if (fiche?.version) lignes.push(["Version", fiche.version]);
  lignes.push(["Type", TYPE_SOURCE[s.kind]]);

  return (
      <div ref={ref_} role="dialog" aria-modal="true" aria-labelledby={idTitre} className="!w-[min(520px,100%)] p-6">
        <p className="label">Source</p>
        <h2 id={idTitre} className="mt-1.5 break-words text-[17px] font-medium leading-snug">{titre}</h2>
        <ExtraitSource s={s} className="mt-1.5 !text-[13px]" />

        {fiche?.description && <p className="mt-4 text-[15px] leading-relaxed">{fiche.description}</p>}
        {etat.phase === "chargement" && <p role="status" className="mt-4 text-[13px] text-[var(--faint)]">Chargement de la fiche…</p>}
        {etat.phase === "indisponible" && aUneFiche(s) && <p role="status" className="mt-4 text-[13px] leading-relaxed text-[var(--mute)]">La fiche détaillée n'est pas disponible pour le moment. Les informations de la source citée restent affichées.</p>}

        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-5 gap-y-1.5 text-[13px]">
          {lignes.map(([k, v]) => (<div key={k} className="contents"><dt className="text-[var(--faint)]">{k}</dt><dd className="break-words">{v}</dd></div>))}
        </dl>

        {f && motFiabilite(f) && (
          <p className="mt-4 text-[13px] leading-relaxed text-[var(--mute)]">
            <span className="font-medium text-[var(--ink)]">{motFiabilite(f)}.</span> {fiche?.fiabilite_sens ?? FIABILITE_PHRASE[f]}
          </p>
        )}
        {fiche?.note && <p className="mt-2 text-[13px] leading-relaxed text-[var(--mute)]">{fiche.note}</p>}

        {fiche && fiche.cite_par.length > 0 && (
          <section className="mt-5" aria-label="Cité par">
            <h3 className="label mb-2">Cité par{(fiche.cite_total ?? fiche.cite_par.length) > Math.min(12, fiche.cite_par.length) ? ` · ${Math.min(12, fiche.cite_par.length)} sur ${fiche.cite_total ?? fiche.cite_par.length}` : ""}</h3>
            <ul className="space-y-1 text-[13px]">
              {fiche.cite_par.slice(0, 12).map((c, i) => <li key={i} className="break-words">{c.libelle}{c.type && <span className="text-[var(--faint)]"> · {c.type}</span>}</li>)}
            </ul>
          </section>
        )}

        <div className="mt-6 flex items-center gap-3">
          {url && <a href={url} target="_blank" rel="noopener noreferrer" className="btn btn-sm">Ouvrir la source</a>}
          <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={onFermer}>Fermer <span className="kbd">Échap</span></button>
        </div>
      </div>
  );
}
