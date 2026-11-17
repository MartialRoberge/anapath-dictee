// Tableau de bord administrateur de la telemetrie MARC v3 (« Pilotage »).
// Donnees : GET /v3/admin/telemetrie/{synthese,recommandations}. Mode ?demo=1 sans backend.
import { useEffect, useState } from "react";
import "./admin.css";
import { chargerTout, fetchParDefaut, type FetchAuth } from "./api";
import { BarresFilets, BarresH, Comparaison } from "./Charts";
import { telechargerCsv } from "./csv";
import { KpiCard } from "./KpiCard";
import { Recommandations } from "./Recommandations";
import type { Periode, Recommandation, Synthese } from "./types";

const PERIODES: Periode[] = ["7j", "30j", "90j"];
const pct = (v: number | null) => (v == null ? "n/d" : `${Math.round(v * 100)} %`);
const secondes = (ms: number | null) => (ms == null ? "n/d" : ms >= 60_000 ? `${Math.floor(ms / 60_000)} min ${String(Math.round((ms % 60_000) / 1000)).padStart(2, "0")}` : `${(ms / 1000).toFixed(1)} s`);

function Panneau({ titre, children }: { titre: string; children: React.ReactNode }) {
  return (
    <section className="adm-carte adm-entree">
      <h2 className="adm-label m-0 mb-4 font-normal">{titre}</h2>
      {children}
    </section>
  );
}

export default function AdminV3({ fetchAuth = fetchParDefaut }: { fetchAuth?: FetchAuth }) {
  const demo = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("demo") === "1";
  const [periode, setPeriode] = useState<Periode>("30j");
  const [s, setS] = useState<Synthese | null>(null);
  const [recos, setRecos] = useState<Recommandation[]>([]);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    setErreur(null);
    chargerTout(periode, fetchAuth, demo)
      .then((r) => { if (actif) { setS(r.s); setRecos(r.recos); } })
      .catch((e: unknown) => { if (actif) setErreur(e instanceof Error ? e.message : "Chargement impossible."); });
    return () => { actif = false; };
  }, [periode, fetchAuth, demo]);

  const k = s?.kpi;
  return (
    <div className="adm px-6 py-10 sm:px-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="adm-label">Administration · aide à la rédaction</div>
          <h1 className="adm-serif m-0 mt-2 text-[40px] leading-[1.1]">Pilotage</h1>
        </div>
        <div className="flex items-center gap-2">
          <div role="group" aria-label="Période" className="flex">
            {PERIODES.map((p) => <button key={p} type="button" className="adm-btn" aria-pressed={periode === p} onClick={() => setPeriode(p)}>{p}</button>)}
          </div>
          <button type="button" className="adm-btn" disabled={!s} onClick={() => s && telechargerCsv(s)}>Exporter CSV</button>
          <a className="adm-btn" href="/?legacy=1">Administration de l'étude</a>
        </div>
      </header>

      {demo && <p className="mb-4 text-[12px]" style={{ color: "var(--adm-doux)" }}>Données de démonstration.</p>}
      {erreur && <p role="alert" className="adm-carte mb-6 text-[14px]">{erreur}</p>}
      {!s && !erreur && <p className="text-[14px]" style={{ color: "var(--adm-doux)" }}>Chargement…</p>}

      {s && k && (
        <div className="space-y-6">
          <Recommandations recos={recos} />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard label="Projets générés" valeur={String(k.projets_generes)} variation={k.variation.projets_generes} />
            <KpiCard label="Utilisateurs actifs" valeur={String(k.utilisateurs_actifs)} variation={k.variation.utilisateurs_actifs} note={`DAU moyen ${k.dau_moyen} · MAU ${k.mau}`} />
            <KpiCard label="Génération médiane" valeur={secondes(k.temps_median_generation_ms)} variation={k.variation.temps_median_generation_ms} hausseBonne={false} />
            <KpiCard label="Jusqu'à l'export" valeur={secondes(k.temps_median_export_ms)} variation={k.variation.temps_median_export_ms} hausseBonne={false} />
            <KpiCard label="Exports sans retouche" valeur={pct(k.taux_exports_sans_retouche)} variation={k.variation.taux_exports_sans_retouche} />
            <KpiCard label="Retouches par projet" valeur={k.retouches_moyennes_par_projet?.toFixed(1) ?? "n/d"} note={`${k.retouches_total} retouches`} />
            <KpiCard label="Précision du correcteur" valeur={pct(s.corrections.precision)} note={`${s.corrections.acceptees} acceptées · ${s.corrections.rejetees} rejetées`} />
            <KpiCard label="Retours" valeur={`${k.feedback_positif} / ${k.feedback_negatif}`} note="positifs / négatifs" />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Panneau titre="Projets par jour"><BarresFilets data={s.series} cle="projets" titre="Projets générés" /></Panneau>
            <Panneau titre="Utilisateurs actifs par jour"><BarresFilets data={s.series} cle="utilisateurs" titre="Utilisateurs" /></Panneau>
            <Panneau titre="Trous : comblés contre ignorés"><Comparaison lignes={s.trous.map((t) => ({ label: t.champ_id, a: t.combles, b: t.ignores }))} /></Panneau>
            <Panneau titre="Alertes : résolues contre ignorées"><Comparaison lignes={s.alertes.map((a) => ({ label: a.alerte_type, a: a.resolues, b: a.ignorees }))} /></Panneau>
            <Panneau titre="Retouches par type d'element"><BarresH lignes={s.retouches.par_type_element.map((r) => ({ label: r.valeur, valeur: r.retouches, note: `${r.retouches} · ${r.par_projet ?? "n/d"} / projet` }))} /></Panneau>
            <Panneau titre="Retouches par niveau de confiance"><BarresH lignes={s.retouches.par_niveau.map((r) => ({ label: r.valeur, valeur: r.retouches, note: `${r.retouches} · ${r.par_projet ?? "n/d"} / projet` }))} /></Panneau>
            <Panneau titre="Top utilisateurs (jours actifs)"><BarresH lignes={s.top_utilisateurs.map((u) => ({ label: u.compte, valeur: u.jours_actifs, note: `${u.jours_actifs} j · ${u.projets} projets` }))} /></Panneau>
            <Panneau titre="Organes les plus fréquents"><BarresH lignes={s.organes.map((o) => ({ label: o.organe, valeur: o.n }))} /></Panneau>
            <Panneau titre="Niveaux de service"><BarresH lignes={s.service.niveaux.map((n) => ({ label: n.niveau, valeur: n.projets }))} /></Panneau>
            <Panneau titre="Motifs de retours négatifs et erreurs">
              <BarresH lignes={[...s.feedback.motifs.map((m) => ({ label: m.motif, valeur: m.n })), ...s.service.erreurs.map((e) => ({ label: `erreur ${e.code}`, valeur: e.n }))]} />
            </Panneau>
          </div>
        </div>
      )}
    </div>
  );
}
