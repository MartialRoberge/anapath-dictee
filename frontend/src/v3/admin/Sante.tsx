// Santé : tables et leurs lignes, puis contrôles en liste « À regarder » / « OK » avec leur détail. Lecture seule.
import { nombre } from "./format";
import type { AdminApi, SanteData } from "./types";
import { useCharge } from "./useCharge";

export const LIBELLES_CONTROLES: Record<string, string> = {
  orphelins: "Données orphelines", doublons_comptes: "Comptes en double", comptes_de_test: "Comptes de test", chaine_audit: "Chaîne d'audit",
  signalements_en_double: "Signalements en double", recopie_non_conformites: "Recopie des non-conformités", tables_jamais_ecrites: "Tables jamais écrites",
};

export function SanteVue({ data }: { data: SanteData }) {
  const aRegarder = data.controles.filter((c) => !c.ok);
  const ok = data.controles.filter((c) => c.ok);
  const ordonnes = [...aRegarder, ...ok];
  return (
    <div className="space-y-6">
      <p className="m-0 text-[13px] adm-doux">Version <span className="num">{data.version}</span> · base <span>{data.base.type}</span> · {aRegarder.length ? `${aRegarder.length} contrôle${aRegarder.length > 1 ? "s" : ""} à regarder` : "tous les contrôles sont OK"}</p>
      <section className="adm-carte" aria-label="Contrôles">
        <h2 className="adm-label m-0 mb-2 font-normal">Contrôles</h2>
        <ul className="adm-liste">
          {ordonnes.map((c) => (
            <li key={c.nom} className="grid gap-1 py-3 sm:grid-cols-[160px_1fr]">
              <span className={c.ok ? "adm-label" : "adm-label adm-ambre"}>{c.ok ? "OK" : "À regarder"}</span>
              <div><div className="text-[14px] font-medium">{LIBELLES_CONTROLES[c.nom] ?? c.nom}</div><div className="text-[13px] adm-doux">{c.detail}</div></div>
            </li>
          ))}
        </ul>
      </section>
      <section className="adm-carte" aria-label="Tables">
        <h2 className="adm-label m-0 mb-2 font-normal">Tables · {data.base.tables.length}</h2>
        <ul className="adm-liste grid sm:grid-cols-2 sm:gap-x-10" style={{ borderTop: 0 }}>
          {data.base.tables.map((t) => (
            <li key={t.nom} className="flex items-baseline justify-between gap-4 !border-t py-2 text-[13px]" style={{ borderColor: "var(--a-line-soft)" }}>
              <span className="truncate">{t.nom}</span>
              {t.lignes == null ? <span className="adm-ambre" title={t.erreur}>illisible</span> : <span className={`num ${t.lignes === 0 ? "adm-faible" : ""}`}>{nombre(t.lignes)} ligne{t.lignes > 1 ? "s" : ""}</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default function Sante({ api }: { api: AdminApi }) {
  const { data, erreur } = useCharge(() => api.sante(), [api]);
  return (
    <section aria-label="Santé">
      {erreur && <p role="alert" className="adm-carte adm-erreur m-0">{erreur}</p>}
      {!data && !erreur && <p className="adm-doux">Chargement…</p>}
      {data && <SanteVue data={data} />}
    </section>
  );
}
