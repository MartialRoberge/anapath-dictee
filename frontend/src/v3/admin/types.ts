// Forme des reponses de l'API d'administration (docs/v3/11_contrat_admin.md) et de /v3/admin/telemetrie/* (export CSV, recommandations).

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

/* ===== Contrat 11_contrat_admin.md ===== */
export type Periode = "7j" | "30j" | "90j" | "tout";
export type Origine = "v3" | "ancienne_version" | "etude";
export type Statut = "ouvert" | "en_cours" | "traite" | "rejete";
export type Nature = "signalement" | "note" | "avis";
export type Sens = "positif" | "negatif" | "neutre";

export interface KpiEnsemble {
  utilisateurs_actifs: number;
  utilisateurs_total: number;
  projets_v3: number;
  comptes_rendus_anciens: number;
  dossiers_etude: number;
  notes_utile: number;
  notes_a_ameliorer: number;
  signalements_ouverts: number;
  duree_mediane_generation_ms: number | null;
  modifications_moyennes_par_projet: number | null;
}
export interface JourSerie { jour: string; projets_v3: number; comptes_rendus_anciens: number; utilisateurs_actifs: number }
export interface VueEnsembleData {
  periode: Periode;
  kpi: KpiEnsemble;
  serie: JourSerie[];
  origines: Record<Origine, boolean>;
}

export interface UtilisateurRef { id: string; email: string | null; nom: string | null }
export interface Retour {
  id: string;
  origine: Origine;
  nature: Nature;
  categorie: string | null;
  sens: Sens | null;
  note_sur_5: number | null;
  message: string;
  statut: Statut | null;
  utilisateur: UtilisateurRef;
  cree_le: string;
  ref: string;
}
export interface RetoursData { total: number; page: number; items: Retour[] }
export interface FiltresRetours { origine: Origine | ""; categorie: string; statut: Statut | ""; page: number }

export interface SignalementMaj {
  id: string; user_id: string; categorie: string; message: string; projet_hash: string | null; ecran: string | null; version_app: string | null;
  statut: Statut; note_admin: string | null; cree_le: string; maj_le: string; doublon_de: string | null; gravite: string | null; categorie_iso: string | null;
}

export interface UtilisateurAdmin {
  id: string; email: string; nom: string; role: string; cree_le: string; derniere_activite: string | null;
  projets_v3: number; comptes_rendus_anciens: number; dossiers_etude: number; habilite_valideur: boolean;
}

export interface Critere {
  cle: string; libelle: string; rang: string; unite: "taux" | "effectif" | "score" | string; valeur: number | null; seuil: number | null;
  sens: "au_plus" | "au_moins" | string; effectif: number; effectif_minimal: number; atteint: boolean | null; observable: boolean;
  donnees_suffisantes: boolean; note: string;
}
export interface TauxEtude { libelle: string; numerateur: number; denominateur: number; valeur: number | null }
export interface EtudeData {
  couverture: Critere[];
  corpus: {
    nb_praticiens: number; nb_praticiens_sans_dossier: number; nb_dossiers: number; nb_exclus: number; nb_dossiers_clos: number;
    nb_commentes: number; nb_abandons: number;
  } & Record<string, unknown>;
  praticiens_favorables?: TauxEtude;
  [cle: string]: unknown;
}
export interface LigneDossierEtude {
  id: string; praticien_nom: string | null; index_session: number; organe: string | null; cree_a: string; abandonne: boolean;
  statut: string; nb_propositions: number; nb_decidees: number; exclu: boolean; motif_exclusion: string | null;
}

export interface TableSante { nom: string; lignes: number | null; erreur?: string }
export interface ControleSante { nom: string; ok: boolean; detail: string }
export interface SanteData { version: string; base: { type: string; tables: TableSante[] }; controles: ControleSante[] }

export interface HabilitationRep { user_id: string; habilite: boolean }

/** Accès aux données : l'implémentation réelle appelle l'API, la démonstration renvoie des fixtures conformes au contrat. */
export interface AdminApi {
  vueEnsemble(p: Periode): Promise<VueEnsembleData>;
  recommandations(p: Periode): Promise<Recommandation[]>;
  syntheseTelemetrie(p: Periode): Promise<Synthese>;
  retours(f: FiltresRetours): Promise<RetoursData>;
  majSignalement(id: string, corps: { statut?: Statut; note_admin?: string }): Promise<SignalementMaj>;
  utilisateurs(): Promise<UtilisateurAdmin[]>;
  habilitation(userId: string, habilite: boolean): Promise<HabilitationRep>;
  etude(): Promise<EtudeData>;
  dossiersEtude(): Promise<LigneDossierEtude[]>;
  exporter(chemin: string, nom: string): Promise<void>;
  sante(): Promise<SanteData>;
}
