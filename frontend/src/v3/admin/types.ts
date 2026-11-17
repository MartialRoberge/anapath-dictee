// Forme des reponses /v3/admin/telemetrie/* (miroir de backend/telemetrie/agregations.py).
export type Periode = "7j" | "30j" | "90j";

export interface Variation {
  projets_generes: number | null;
  utilisateurs_actifs: number | null;
  temps_median_generation_ms: number | null;
  temps_median_export_ms: number | null;
  taux_exports_sans_retouche: number | null;
}

export interface Kpi {
  projets_generes: number;
  utilisateurs_actifs: number;
  dau_moyen: number;
  mau: number;
  temps_median_generation_ms: number | null;
  temps_median_export_ms: number | null;
  exports: number;
  taux_exports_sans_retouche: number | null;
  retouches_total: number;
  retouches_moyennes_par_projet: number | null;
  feedback_positif: number;
  feedback_negatif: number;
  precision_correcteur: number | null;
  erreurs: number;
  variation: Variation;
}

export interface Retouche { valeur: string; retouches: number; par_projet: number | null }
export interface Trou { champ_id: string; combles: number; ignores: number; taux_ignore: number | null }
export interface AlerteStat { alerte_type: string; resolues: number; ignorees: number; taux_ignore: number | null }
export interface JourStat { jour: string; projets: number; utilisateurs: number; exports: number; erreurs: number }
export interface TopUser { user_id: string; compte: string; jours_actifs: number; projets: number }

export interface Synthese {
  periode_jours: number;
  debut: string;
  fin: string;
  kpi: Kpi;
  retouches: { par_type_element: Retouche[]; par_statut: Retouche[]; par_niveau: Retouche[] };
  trous: Trou[];
  alertes: AlerteStat[];
  corrections: { acceptees: number; rejetees: number; precision: number | null };
  feedback: { positif: number; negatif: number; motifs: { motif: string; n: number }[] };
  organes: { organe: string; n: number }[];
  service: { niveaux: { niveau: string; projets: number }[]; erreurs: { code: string; n: number }[] };
  series: JourStat[];
  top_utilisateurs: TopUser[];
}

export interface Recommandation {
  id: string;
  severite: "critique" | "attention" | "info";
  cible: string;
  titre: string;
  detail: string;
  valeur: number;
  seuil: number;
}
