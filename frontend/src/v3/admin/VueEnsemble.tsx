// Vue d'ensemble : KPI avec l'origine de chaque chiffre, courbe d'activité, actions recommandées et export CSV de la télémétrie.
import { useState } from "react";
import Courbe from "./Courbe";
import { duree, nombre } from "./format";
import { telechargerCsv } from "./csv";
import type { AdminApi, Periode, Recommandation, VueEnsembleData } from "./types";
import { useCharge } from "./useCharge";

export const PERIODES: [Periode, string][] = [["7j", "7 j"], ["30j", "30 j"], ["90j", "90 j"], ["tout", "Tout"]];

function Kpi({ label, valeur, origine, note }: { label: string; valeur: string; origine: string; note?: string }) {
  return (
    <div className="adm-carte" role="group" aria-label={label}>
      <div className="adm-label">{label}</div>
      <div className="adm-serif adm-kpi-valeur num">{valeur}</div>
      <div className="adm-kpi-note">{origine}{note ? ` · ${note}` : ""}</div>
    </div>
  );
}

export function VueEnsembleVue({ data, recos }: { data: VueEnsembleData; recos: Recommandation[] }) {
  const k = data.kpi, o = data.origines;
  const notes = k.notes_utile + k.notes_a_ameliorer;
  return (
    <div className="space-y-6">
      <div className="adm-grille">
        <Kpi label="Utilisateurs actifs" valeur={nombre(k.utilisateurs_actifs)} origine="Toutes origines" note={`sur ${nombre(k.utilisateurs_total)} comptes`} />
        {o.v3 && <Kpi label="Projets générés" valeur={nombre(k.projets_v3)} origine="v3" />}
        {o.ancienne_version && <Kpi label="Comptes rendus" valeur={nombre(k.comptes_rendus_anciens)} origine="Ancienne version" />}
        {o.etude && <Kpi label="Dossiers d'étude" valeur={nombre(k.dossiers_etude)} origine="Étude" />}
        {o.v3 && <Kpi label="Notes rapides" valeur={notes ? `${k.notes_utile} / ${k.notes_a_ameliorer}` : "0"} origine="v3" note="utile / à améliorer" />}
        <Kpi label="Signalements ouverts" valeur={nombre(k.signalements_ouverts)} origine="v3" note="état actuel, hors période" />
        {o.v3 && <Kpi label="Génération médiane" valeur={duree(k.duree_mediane_generation_ms)} origine="v3" />}
        {o.v3 && <Kpi label="Modifications par projet" valeur={nombre(k.modifications_moyennes_par_projet, 1)} origine="v3" note="moyenne" />}
      </div>
      {!o.v3 && <p className="m-0 text-[13px] adm-doux">Aucune activité v3 enregistrée pour l'instant : les indicateurs v3 apparaîtront dès le premier projet généré.</p>}
      <section className="adm-carte" aria-label="Activité par jour">
        <h2 className="adm-label m-0 mb-4 font-normal">Activité par jour</h2>
        {data.serie.length ? <Courbe serie={data.serie} /> : <p className="m-0 adm-doux">Aucune donnée sur la période.</p>}
      </section>
      {recos.length > 0 && (
        <section className="adm-carte" aria-label="Actions recommandées">
          <h2 className="adm-label m-0 mb-2 font-normal">{recos.length} action{recos.length > 1 ? "s" : ""} recommandée{recos.length > 1 ? "s" : ""}</h2>
          <ol className="adm-liste">
            {recos.map((r) => (
              <li key={r.id} className="grid gap-1 py-3 sm:grid-cols-[110px_1fr]">
                <span className={`adm-label ${r.severite === "critique" ? "adm-ambre" : ""}`}>{r.severite}</span>
                <div><div className="text-[14px] font-medium">{r.titre}</div><div className="text-[13px] adm-doux">{r.detail}</div></div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

export default function VueEnsemble({ api }: { api: AdminApi }) {
  const [periode, setPeriode] = useState<Periode>("30j");
  const vue = useCharge(() => api.vueEnsemble(periode), [api, periode]);
  const recos = useCharge(() => api.recommandations(periode).catch(() => [] as Recommandation[]), [api, periode]);
  const [csvErreur, setCsvErreur] = useState("");
  const exporter = async () => {
    setCsvErreur("");
    try { telechargerCsv(await api.syntheseTelemetrie(periode)); } catch (e) { setCsvErreur((e as Error).message); }
  };
  return (
    <section aria-label="Vue d'ensemble">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="adm-seg" role="radiogroup" aria-label="Période">
          {PERIODES.map(([p, l]) => <button key={p} type="button" role="radio" aria-checked={periode === p} className="adm-seg-item" onClick={() => setPeriode(p)}>{l}</button>)}
        </div>
        <div className="flex items-center gap-3">
          {csvErreur && <span role="alert" className="text-[13px] adm-erreur">{csvErreur}</span>}
          <button type="button" className="adm-btn" onClick={exporter}>Exporter la télémétrie (CSV)</button>
        </div>
      </div>
      {vue.erreur && <p role="alert" className="adm-carte adm-erreur m-0">{vue.erreur}</p>}
      {!vue.data && !vue.erreur && <p className="adm-doux">Chargement…</p>}
      {vue.data && <VueEnsembleVue data={vue.data} recos={recos.data ?? []} />}
    </section>
  );
}
