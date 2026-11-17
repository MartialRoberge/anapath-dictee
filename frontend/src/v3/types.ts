// Contrat MARC v3 — miroir exact de backend/projet/schemas.py. Modifier les deux ensemble.
export type Niveau = "haute" | "moyenne" | "basse";

export interface SourceRef {
  kind: "dictee" | "kb" | "regle" | "agent" | "web";
  ref: string;
  libelle: string;
  extrait?: string | null;
  debut?: number | null;
  fin?: number | null;
  fiabilite?: "A" | "B" | "C" | "D" | null;
  url?: string | null;
}

export interface Correction {
  id: string;
  original: string;
  corrige: string;
  debut: number;
  fin: number;
  confiance: number;
  raison: string;
  candidats: string[];
  sources: SourceRef[];
  appliquee: boolean;
}

export interface Preuve {
  categorie: "dictee" | "regle" | "referentiel" | "modele";
  verdict: "ok" | "attention" | "echec" | "info";
  titre: string;
  detail: string;
  calcul?: string | null;
  source?: SourceRef | null;
  effet?: number | null;
}

export interface Element {
  id: string;
  section_id: string;
  type: "phrase" | "trou" | "titre" | "liste";
  texte: string;
  statut: "dicte" | "reformule" | "normalise" | "a_completer";
  confiance: number;
  niveau: Niveau;
  sources: SourceRef[];
  explication: string;
  preuves?: Preuve[];
  a_verifier?: string | null;
  champ_id?: string | null;
  obligatoire: boolean;
  options: string[];
  unite?: string | null;
}

export interface Section { id: string; titre: string; ordre: number }

export interface Alerte {
  id: string;
  type: "incoherence" | "unite" | "manquant" | "phonetique" | "securite" | "codage";
  gravite: "bloquant" | "attention" | "info";
  message: string;
  element_ids: string[];
  suggestion?: string | null;
  confiance: number;
  sources: SourceRef[];
  agent: string;
  pourquoi?: string;
  calcul?: string | null;
  action?: string;
}

export interface Code {
  systeme: "ADICAP" | "SNOMED_CT" | "CIM_O3";
  code: string;
  libelle: string;
  statut: "certain" | "partiel" | "suggestion";
  confiance: number;
  sources: SourceRef[];
  explication: string;
}

export type Role = "orchestrateur" | "transcripteur" | "correcteur" | "extracteur" | "verificateur" | "codeur" | "redacteur" | "relecteur";

export interface TraceStep {
  id: string;
  agent: string;
  role: Role;
  titre: string;
  statut: "en_attente" | "en_cours" | "ok" | "avertissement" | "erreur" | "saute";
  debut_ms: number;
  duree_ms?: number | null;
  modele?: string | null;
  resume: string;
  details: string[];
}

export interface Contexte {
  organes: string[];
  organes_libelles: string[];
  prelevement?: string | null;
  contexte_lesionnel: "benin" | "precancereux" | "malin" | "indetermine";
  niveau_service: "N0" | "N1" | "N2" | "N3";
}

export interface Metriques {
  duree_totale_ms: number;
  appels_llm: number;
  tokens_entree: number;
  tokens_sortie: number;
  confiance_moyenne: number;
}

export interface Tracabilite {
  id?: string;
  horodatage_utc?: string;
  version_pipeline?: string;
  kb_version?: string;
  kb_empreinte_sha256?: string;
  kb_statut?: "en_service" | "non_en_service" | "non_enregistree";
  modeles?: Record<string, string>;
  empreinte_dictee_corrigee_sha256?: string;
  niveau_service?: "N0" | "N1" | "N2" | "N3";
  statut?: "brouillon" | "valide";
}

export interface Projet {
  id: string;
  version: "3";
  titre: string;
  dictee: { brute: string; corrigee: string };
  contexte: Contexte;
  corrections: Correction[];
  sections: Section[];
  elements: Element[];
  alertes: Alerte[];
  codes: Code[];
  trace: TraceStep[];
  metriques: Metriques;
  tracabilite?: Tracabilite | null;
}

// SSE : event "step" -> TraceStep ; "partial" -> {elements: Element[]} ; "projet" -> Projet ; "error" -> {message, recuperable}
export type ProjetEvent =
  | { event: "step"; data: TraceStep }
  | { event: "partial"; data: { elements: Element[] } }
  | { event: "projet"; data: Projet }
  | { event: "error"; data: { message: string; recuperable: boolean } };
