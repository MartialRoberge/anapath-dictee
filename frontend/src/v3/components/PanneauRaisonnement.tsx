// Panneau droit « Raisonnement » : onglets sobres (Pourquoi, À vérifier, Codes, Dictée, Progression).
import { useEffect, useRef } from "react";
import type { EtatGeneration } from "../hooks/useGeneration";
import { alertesOuvertes, type ProjetLocal } from "../lib/session";
import type { Alerte, Code, Correction, Element, SourceRef, TraceStep } from "../types";
import OngletAlertes from "./OngletAlertes";
import OngletCodes from "./OngletCodes";
import OngletDictee from "./OngletDictee";
import OngletProgression from "./OngletProgression";
import OngletPourquoi from "./OngletPourquoi";
import { touche } from "../lib/raccourcis";
import type { DecisionAlerte } from "../lib/session";

export type NomOnglet = "pourquoi" | "alertes" | "codes" | "dictee" | "progression";
/** Ordre des onglets = Alt+1 à Alt+5 (voir lib/raccourcis.ts). */
export const ORDRE_ONGLETS: NomOnglet[] = ["pourquoi", "alertes", "codes", "dictee", "progression"];

interface Props {
  onglet: NomOnglet;
  onOnglet: (o: NomOnglet) => void;
  local: ProjetLocal | null;
  generation: EtatGeneration;
  etapes: TraceStep[];
  element: Element | null;
  alerteActive: string | null;
  correctionActive: string | null;
  onAlerte: (a: Alerte) => void;
  onDecider: (a: Alerte, d: DecisionAlerte | null) => void;
  onCorrectionActive: (id: string | null) => void;
  onDecision: (c: Correction, choix: string | "original") => void;
  onCopieCode: (c: Code, texte: string) => void;
  onModifierCode: (c: Code, nouveau: string) => void;
  onConsulte: (s: SourceRef) => void;
  onNotifier: (m: string) => void;
  onDocument: () => void;
  onRemplir?: (el: Element, valeur: string) => void;
  onFermer?: () => void;
}

export default function PanneauRaisonnement(p: Props) {
  const { local } = p;
  const ouvertes = local ? alertesOuvertes(local).length : 0;
  const onglets: Array<{ cle: NomOnglet; titre: string; n?: number }> = [
    { cle: "pourquoi", titre: "Pourquoi" },
    { cle: "alertes", titre: "À vérifier", n: local ? ouvertes : undefined },
    { cle: "codes", titre: "Codes", n: local?.projet.codes.length },
    { cle: "dictee", titre: "Dictée" },
    { cle: "progression", titre: "Progression" },
  ];
  const liste = useRef<HTMLDivElement>(null);

  // Nouvel onglet : on repart du haut et l'onglet actif reste visible.
  const corps = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (corps.current) corps.current.scrollTop = 0;
    liste.current?.querySelector<HTMLElement>(`#tab-${p.onglet}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [p.onglet]);

  const fleches = (e: React.KeyboardEvent) => {
    const i = onglets.findIndex((o) => o.cle === p.onglet);
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const suivant = onglets[(i + d + onglets.length) % onglets.length];
    p.onOnglet(suivant.cle);
    liste.current?.querySelector<HTMLElement>(`#tab-${suivant.cle}`)?.focus();
  };

  return (
    <aside className="flex h-full min-h-0 flex-col border-l-[0.5px] border-[var(--line)] bg-[var(--card)]" aria-label="Raisonnement">
      <div className="flex items-center px-4 pt-5">
        <h2 className="titre-serif flex-1 text-[22px] leading-[1.2]">Raisonnement</h2>
        {p.onFermer && <div className="min-[1180px]:hidden"><button type="button" className="btn btn-ghost btn-sm" onClick={p.onFermer}>Fermer <span className="kbd">Échap</span></button></div>}
      </div>
      <div ref={liste} role="tablist" aria-label="Raisonnement des agents" onKeyDown={fleches} className="mx-4 mt-3">
        {onglets.map((o) => (
          <button key={o.cle} id={`tab-${o.cle}`} role="tab" type="button" className="tab" aria-selected={p.onglet === o.cle} aria-controls="panneau-raisonnement"
            tabIndex={p.onglet === o.cle ? 0 : -1} aria-keyshortcuts={`Alt+${onglets.indexOf(o) + 1}`} title={`${o.titre} · ${touche(String(onglets.indexOf(o) + 1))}`} onClick={() => p.onOnglet(o.cle)}>
            {o.titre}{o.n != null && o.n > 0 && <span className={`num ml-1 text-[12px] ${o.cle === "alertes" && ouvertes > 0 ? "font-semibold text-[var(--amber)]" : "text-[var(--faint)]"}`}>{o.n}</span>}
          </button>
        ))}
      </div>
      <div ref={corps} id="panneau-raisonnement" role="tabpanel" aria-labelledby={`tab-${p.onglet}`} tabIndex={0} className="scroll min-h-0 flex-1 overflow-y-auto">
        {p.onglet === "progression" && (
          <OngletProgression etapes={p.etapes} projet={local?.projet} generation={p.generation} alertesOuvertes={ouvertes} onDocument={p.onDocument}
            onOnglet={(o) => p.onOnglet(o)} />
        )}
        {p.onglet === "alertes" && local && <OngletAlertes alertes={local.projet.alertes} decisions={local.alertes} active={p.alerteActive} onActiver={p.onAlerte} onDecider={p.onDecider} onConsulte={p.onConsulte} />}
        {p.onglet === "codes" && local && <OngletCodes local={local} onCopie={p.onCopieCode} onModifier={p.onModifierCode} onNotifier={p.onNotifier} onConsulte={p.onConsulte} />}
        {p.onglet === "pourquoi" && local && <OngletPourquoi local={local} element={p.element} onConsulte={p.onConsulte} onRemplir={p.onRemplir} />}
        {p.onglet === "dictee" && local && (
          <OngletDictee local={local} element={p.element} correctionActive={p.correctionActive} onCorrectionActive={p.onCorrectionActive} onDecision={p.onDecision} onConsulte={p.onConsulte} />
        )}
        {!local && p.onglet !== "progression" && <p className="px-5 py-6 text-[15px] text-[var(--mute)]">Disponible dès que le projet est prêt.</p>}
      </div>
    </aside>
  );
}
