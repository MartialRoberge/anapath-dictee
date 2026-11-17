// Progression : pendant le traitement, l'avancement en direct (étapes en langage clair) ;
// ensuite, un résumé de ce qui a été fait. Détails techniques (agent, modèle, durée) dans un repli.
import { useState } from "react";
import { duree } from "../lib/format";
import { resumeProjet } from "../lib/pourquoi";
import type { Projet, TraceStep } from "../types";
import type { EtatGeneration } from "../hooks/useGeneration";

function Marqueur({ statut }: { statut: TraceStep["statut"] }) {
  const c = { ok: "etape-coche", en_cours: "etape-cours", en_attente: "etape-attente", avertissement: "etape-warn", erreur: "etape-err", saute: "etape-saute" }[statut];
  return <span className={c} aria-hidden />;
}

const LIBELLE: Record<TraceStep["statut"], string> = { ok: "terminé", en_cours: "en cours", en_attente: "à venir", avertissement: "terminé avec avertissement", erreur: "erreur", saute: "ignoré" };

/** Une étape. `technique` : affiche agent, modèle et durée (repli de détails) au lieu du résumé en clair. */
function Etape({ s, dernier, technique }: { s: TraceStep; dernier: boolean; technique: boolean }) {
  const [ouvert, setOuvert] = useState(false);
  const aDetails = technique && (s.details.length > 0 || !!s.resume);
  const classe = s.statut === "ok" || s.statut === "avertissement" ? "fait" : s.statut === "en_attente" ? "a-venir" : "";
  return (
    <li className={`enter relative pb-4 pl-7 ${classe}`}>
      {!dernier && <span className="rail" aria-hidden />}
      <span className="absolute left-0 top-[3px]"><Marqueur statut={s.statut} /></span>
      <button type="button" onClick={() => aDetails && setOuvert(!ouvert)} aria-expanded={aDetails ? ouvert : undefined} disabled={!aDetails} className="w-full text-left !opacity-100">
        <span className="flex items-baseline gap-2">
          <span className="etape-titre flex-1 text-[15px] leading-snug">{s.titre}</span>
          {technique && <span className="num flex-none text-[12px] text-[var(--faint)]">{duree(s.duree_ms)}</span>}
        </span>
        <span className="mt-0.5 block text-[12px] text-[var(--faint)]">
          <span className="sr-only-v3">{LIBELLE[s.statut]}. </span>
          {technique ? <>{s.agent}{s.modele ? ` · ${s.modele}` : ""}</> : s.statut === "en_cours" ? "En cours…" : s.resume}
        </span>
      </button>
      {ouvert && (
        <div className="fade mt-2 rounded-lg bg-[var(--paper)] px-3 py-2.5 text-[13px] leading-relaxed text-[var(--mute)]">
          {s.resume && <p>{s.resume}</p>}
          {s.details.length > 0 && <ul className="mt-1.5 list-disc space-y-0.5 pl-4">{s.details.map((d, i) => <li key={i}>{d}</li>)}</ul>}
        </div>
      )}
    </li>
  );
}

interface Props {
  etapes: TraceStep[];
  projet?: Projet;
  generation: EtatGeneration;
  alertesOuvertes: number;
  onOnglet: (o: "alertes" | "codes" | "dictee") => void;
  onDocument: () => void;
}

export default function OngletProgression({ etapes, projet, generation, alertesOuvertes, onOnglet, onDocument }: Props) {
  const enCours = generation.phase === "en_cours";
  const m = projet?.metriques;
  const resume = projet && !enCours ? resumeProjet(projet) : [];
  return (
    <div className="px-5 py-5">
      {etapes.length === 0 && enCours && (
        <p className="text-[13px] text-[var(--mute)]" role="status">{generation.audio ? "Envoi de l'enregistrement au service…" : "Envoi de la dictée au service…"}</p>
      )}
      {etapes.length === 0 && !enCours && !projet && <p className="text-[13px] text-[var(--faint)]">Aucune trace pour ce projet.</p>}

      {enCours && <ol aria-label="Avancement du traitement">{etapes.map((s, i) => <Etape key={s.id} s={s} dernier={i === etapes.length - 1} technique={false} />)}</ol>}

      {projet && !enCours && (
        <section className="enter" aria-label="Ce que MARC a fait">
          <p className="label mb-2.5">Ce qui a été fait</p>
          <ul className="text-[15px] leading-snug">
            {resume.map((l) => (
              <li key={l.texte}>
                {l.onglet ? (
                  <button type="button" onClick={() => onOnglet(l.onglet!)} className="-mx-2 flex w-[calc(100%+16px)] items-baseline gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[var(--paper)]">
                    <span className={`flex-1 ${l.alerte ? "text-[var(--amber)]" : ""}`}>{l.texte}</span>
                  </button>
                ) : <p className={`py-1.5 ${l.alerte ? "text-[var(--amber)]" : ""}`}>{l.texte}</p>}
              </li>
            ))}
            {resume.length === 0 && <li className="py-1.5 text-[var(--mute)]">Projet rédigé à partir de la dictée.</li>}
          </ul>
          <p className="mt-3 text-[13px] text-[var(--faint)]">
            {alertesOuvertes ? `${alertesOuvertes} point${alertesOuvertes > 1 ? "s" : ""} à vérifier avant de valider.` : "Tous les points sont traités."}
          </p>
          <button type="button" className="btn btn-sm mt-4" onClick={onDocument}>Relire le projet</button>
        </section>
      )}

      {etapes.length > 0 && !enCours && (
        <details className="mt-6 border-t border-[var(--line)] pt-3">
          <summary className="cursor-pointer text-[12px] text-[var(--faint)] hover:text-[var(--ink)]">Détails techniques</summary>
          {m && (
            <p className="mt-2.5 text-[13px] leading-relaxed text-[var(--mute)]">
              Terminé en <b className="num font-semibold text-[var(--ink)]">{duree(m.duree_totale_ms)}</b>
              {m.appels_llm > 0 && <> · {m.appels_llm} appels de modèle</>}
              {m.confiance_moyenne > 0 && <> · confiance moyenne <span className="num">{Math.round(m.confiance_moyenne * 100)} %</span></>}
            </p>
          )}
          <ol className="mt-4" aria-label="Étapes techniques">{etapes.map((s, i) => <Etape key={s.id} s={s} dernier={i === etapes.length - 1} technique />)}</ol>
        </details>
      )}
    </div>
  );
}
