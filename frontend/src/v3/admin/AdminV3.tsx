// Administration MARC v3 : cinq sections (vue d'ensemble, retours, utilisateurs, étude, santé) sur l'API /v3/admin (contrat 11_contrat_admin.md).
// Mode ?demo=1 : données de démonstration conformes au contrat. La page ne défile pas : seule la zone de contenu défile.
import { useMemo, useRef, useState } from "react";
import "./admin.css";
import { choisirApi } from "./api";
import Etude from "./Etude";
import Retours from "./Retours";
import Sante from "./Sante";
import type { AdminApi } from "./types";
import Utilisateurs from "./Utilisateurs";
import VueEnsemble from "./VueEnsemble";

export const SECTIONS = [["ensemble", "Vue d'ensemble"], ["retours", "Retours"], ["utilisateurs", "Utilisateurs"], ["etude", "Étude"], ["sante", "Santé"]] as const;
type Section = (typeof SECTIONS)[number][0];

export default function AdminV3({ api: apiFournie }: { api?: AdminApi }) {
  const demo = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("demo") === "1";
  const api = useMemo(() => apiFournie ?? choisirApi(demo), [apiFournie, demo]);
  const [section, setSection] = useState<Section>("ensemble");
  const onglets = useRef<(HTMLButtonElement | null)[]>([]);
  const clavier = (e: React.KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const j = (i + d + SECTIONS.length) % SECTIONS.length;
    setSection(SECTIONS[j][0]); onglets.current[j]?.focus();
  };
  return (
    <div className="adm-t adm">
      <header className="adm-entete">
        <div className="adm-label">Administration{demo && " · données de démonstration"}</div>
        <h1 className="adm-serif adm-titre mt-1">Pilotage</h1>
        <div className="adm-onglets" role="tablist" aria-label="Sections de l'administration">
          {SECTIONS.map(([k, l], i) => (
            <button key={k} ref={(el) => { onglets.current[i] = el; }} type="button" role="tab" id={`onglet-${k}`} aria-selected={section === k} aria-controls="panneau-admin" tabIndex={section === k ? 0 : -1}
              className="adm-onglet" onClick={() => setSection(k)} onKeyDown={(e) => clavier(e, i)}>{l}</button>
          ))}
        </div>
      </header>
      <div id="panneau-admin" role="tabpanel" aria-labelledby={`onglet-${section}`} className="adm-contenu">
        <div className="mx-auto max-w-[1080px]">
          {section === "ensemble" && <VueEnsemble api={api} />}
          {section === "retours" && <Retours api={api} />}
          {section === "utilisateurs" && <Utilisateurs api={api} />}
          {section === "etude" && <Etude api={api} />}
          {section === "sante" && <Sante api={api} />}
        </div>
      </div>
    </div>
  );
}
