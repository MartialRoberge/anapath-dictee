// Export CSV de la synthese (une ligne par mesure : section;cle;valeur).
import type { Synthese } from "./types";

export function syntheseEnCsv(s: Synthese): string {
  const L: (string | number | null)[][] = [["section", "cle", "valeur"]];
  const k = s.kpi;
  for (const [cle, v] of Object.entries(k)) if (typeof v !== "object") L.push(["kpi", cle, v as number | null]);
  s.trous.forEach((t) => L.push(["trou_taux_ignore", t.champ_id, t.taux_ignore]));
  s.alertes.forEach((a) => L.push(["alerte_taux_ignore", a.alerte_type, a.taux_ignore]));
  s.retouches.par_type_element.forEach((x) => L.push(["retouches_type", x.valeur, x.retouches]));
  s.organes.forEach((o) => L.push(["organe", o.organe, o.n]));
  s.series.forEach((j) => L.push(["serie_projets", j.jour, j.projets]));
  s.top_utilisateurs.forEach((u) => L.push(["top_utilisateur_jours", u.compte, u.jours_actifs]));
  return L.map((l) => l.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";")).join("\n");
}

export function telechargerCsv(s: Synthese): void {
  const blob = new Blob(["﻿" + syntheseEnCsv(s)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `marc-telemetrie-${s.fin}.csv`; a.click();
  URL.revokeObjectURL(url);
}
