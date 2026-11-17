// Étude : synthèse (critères du protocole, corpus) et accès aux routes existantes de dossiers et d'export.
import { useState } from "react";
import { dateHeure, nombre, pct } from "./format";
import type { AdminApi, Critere, EtudeData, LigneDossierEtude } from "./types";
import { useCharge } from "./useCharge";

const valeurCritere = (c: Critere): string => (c.valeur == null ? "n/d" : c.unite === "taux" ? pct(c.valeur) : nombre(c.valeur, c.unite === "score" ? 1 : 0));
const seuilCritere = (c: Critere): string => (c.seuil == null ? "—" : `${c.sens === "au_plus" ? "≤" : "≥"} ${c.unite === "taux" ? pct(c.seuil) : nombre(c.seuil, 1)}`);

export function EtudeVue({ data }: { data: EtudeData }) {
  const c = data.corpus;
  const corpus: [string, number][] = [
    ["Praticiens", c.nb_praticiens], ["Dossiers", c.nb_dossiers], ["Dossiers clos", c.nb_dossiers_clos], ["Dossiers commentés", c.nb_commentes], ["Abandons", c.nb_abandons], ["Exclus", c.nb_exclus],
  ];
  return (
    <div className="space-y-6">
      <div className="adm-grille">
        {corpus.map(([l, v]) => (
          <div key={l} className="adm-carte"><div className="adm-label">{l}</div><div className="adm-serif adm-kpi-valeur num">{nombre(v)}</div></div>
        ))}
        {data.praticiens_favorables && (
          <div className="adm-carte"><div className="adm-label">Praticiens souhaitant continuer</div>
            <div className="adm-serif adm-kpi-valeur num">{data.praticiens_favorables.numerateur} / {data.praticiens_favorables.denominateur}</div></div>
        )}
      </div>
      <section className="adm-carte adm-defile-x" aria-label="Critères du protocole">
        <h2 className="adm-label m-0 mb-2 font-normal">Critères du protocole</h2>
        <table className="adm-table">
          <thead><tr><th scope="col">Critère</th><th scope="col" className="num">Valeur</th><th scope="col" className="num">Seuil</th><th scope="col" className="num">Effectif</th><th scope="col">Lecture</th></tr></thead>
          <tbody>
            {data.couverture.map((k) => (
              <tr key={k.cle}>
                <td><div>{k.libelle}</div>{k.note && <div className="text-[12px] adm-doux">{k.note}</div>}</td>
                <td className="num">{valeurCritere(k)}</td>
                <td className="num">{seuilCritere(k)}</td>
                <td className="num">{k.effectif} / {k.effectif_minimal}</td>
                <td>{!k.donnees_suffisantes ? <span className="adm-faible">Données insuffisantes</span> : k.atteint === false ? <span className="adm-ambre">À regarder</span> : k.atteint ? "Atteint" : "n/d"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export function TableDossiers({ lignes }: { lignes: LigneDossierEtude[] }) {
  if (!lignes.length) return <p className="m-0 adm-doux">Aucun dossier.</p>;
  return (
    <div className="adm-defile-x">
      <table className="adm-table">
        <thead><tr><th scope="col">Praticien</th><th scope="col">Organe</th><th scope="col">Créé</th><th scope="col">Statut</th><th scope="col" className="num">Décisions</th></tr></thead>
        <tbody>
          {lignes.map((d) => (
            <tr key={d.id}>
              <td>{d.praticien_nom ?? "—"}</td><td>{d.organe ?? "—"}</td><td className="whitespace-nowrap">{dateHeure(d.cree_a)}</td>
              <td>{d.exclu ? `Exclu${d.motif_exclusion ? ` (${d.motif_exclusion})` : ""}` : d.abandonne ? "Abandonné" : d.statut}</td>
              <td className="num">{d.nb_decidees} / {d.nb_propositions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Etude({ api }: { api: AdminApi }) {
  const { data, erreur } = useCharge(() => api.etude(), [api]);
  const [dossiers, setDossiers] = useState<LigneDossierEtude[] | null>(null);
  const [alerte, setAlerte] = useState("");
  const agir = async (f: () => Promise<unknown>) => { setAlerte(""); try { await f(); } catch (e) { setAlerte((e as Error).message); } };
  return (
    <section aria-label="Étude">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button type="button" className="adm-btn" onClick={() => agir(async () => setDossiers(await api.dossiersEtude()))}>Afficher les dossiers</button>
        <button type="button" className="adm-btn" onClick={() => agir(() => api.exporter("/admin/etude/export", "marc-etude.zip"))}>Exporter (ZIP de CSV)</button>
        <button type="button" className="adm-btn" onClick={() => agir(() => api.exporter("/admin/etude/export.xlsx", "marc-etude.xlsx"))}>Exporter (Excel)</button>
        <button type="button" className="adm-btn" onClick={() => agir(() => api.exporter("/admin/etude/ergonomie", "marc-etude-ergonomie.json"))}>Profil d'usage (JSON)</button>
      </div>
      {alerte && <p role="alert" className="mb-4 text-[13px] adm-erreur">{alerte}</p>}
      {erreur && <p role="alert" className="adm-carte adm-erreur m-0">{erreur}</p>}
      {!data && !erreur && <p className="adm-doux">Chargement…</p>}
      {data && <EtudeVue data={data} />}
      {dossiers && <section className="adm-carte mt-6" aria-label="Dossiers de l'étude"><h2 className="adm-label m-0 mb-2 font-normal">Dossiers de l'étude</h2><TableDossiers lignes={dossiers} /></section>}
    </section>
  );
}
