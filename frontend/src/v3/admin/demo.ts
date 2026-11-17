// Jeu de données de démonstration (?demo=1) : déterministe, sans backend, aucune donnée réelle ; formes conformes à docs/v3/11_contrat_admin.md.
import type {
  AdminApi, EtudeData, Origine, Periode, Recommandation, Retour, RetoursData, SanteData, SignalementMaj, Statut, Synthese, UtilisateurAdmin, VueEnsembleData,
} from "./types";

const U = {
  a: { id: "u-a", email: "alice@labo.example", nom: "Alice Pathologiste" },
  b: { id: "u-b", email: "bruno@labo.example", nom: "Bruno Interne" },
  c: { id: "u-c", email: "chloe@labo.example", nom: "Chloé Pathologiste" },
};

export const vueEnsembleDemo = (periode: Periode): VueEnsembleData => {
  const jours = periode === "7j" ? 7 : periode === "90j" ? 90 : periode === "tout" ? 180 : 30;
  const fin = Date.UTC(2026, 10, 17);
  const serie = Array.from({ length: jours }, (_, i) => {
    const d = new Date(fin - (jours - 1 - i) * 864e5);
    const semaine = d.getUTCDay() === 0 || d.getUTCDay() === 6;
    const base = semaine ? 0 : 3 + ((i * 7) % 6);
    return { jour: d.toISOString().slice(0, 10), projets_v3: base + (i > jours / 2 ? 2 : 0), comptes_rendus_anciens: semaine ? 0 : (i * 3) % 4, utilisateurs_actifs: semaine ? 1 : 2 + (i % 4) };
  });
  const somme = (k: "projets_v3" | "comptes_rendus_anciens") => serie.reduce((a, j) => a + j[k], 0);
  return {
    periode,
    kpi: {
      utilisateurs_actifs: 7, utilisateurs_total: 14, projets_v3: somme("projets_v3"), comptes_rendus_anciens: somme("comptes_rendus_anciens"), dossiers_etude: 12,
      notes_utile: 18, notes_a_ameliorer: 4, signalements_ouverts: 3, duree_mediane_generation_ms: 9200, modifications_moyennes_par_projet: 2.3,
    },
    serie,
    origines: { v3: true, ancienne_version: true, etude: true },
  };
};

const horo = (j: number, h = 9) => new Date(Date.UTC(2026, 10, 17 - j, h, 24, 23)).toISOString().replace(/\.\d+Z$/, "Z");

export const retoursDemo: Retour[] = [
  { id: "signalement:5efc5cd8-568d-4293-855a-8a7094183313", origine: "v3", nature: "signalement", categorie: "erreur_projet", sens: null, note_sur_5: null, message: "Le code ADICAP du côlon est faux", statut: "ouvert", utilisateur: U.a, cree_le: horo(0), ref: "5efc5cd8-568d-4293-855a-8a7094183313" },
  { id: "note:n-1", origine: "v3", nature: "note", categorie: null, sens: "negatif", note_sur_5: null, message: "Motifs : info_omise, trop_lent", statut: null, utilisateur: U.b, cree_le: horo(1, 14), ref: "n-1" },
  { id: "signalement:nc-1", origine: "v3", nature: "signalement", categorie: "non_conformite", sens: null, note_sur_5: null, message: "Non-conformité ISO : faux_positif, gravité majeure.", statut: "en_cours", utilisateur: U.a, cree_le: horo(5, 8), ref: "nc-1" },
  { id: "note:n-2", origine: "v3", nature: "note", categorie: null, sens: "positif", note_sur_5: null, message: "Motifs : gain_temps", statut: null, utilisateur: U.c, cree_le: horo(6, 16), ref: "n-2" },
  { id: "avis:r-1", origine: "ancienne_version", nature: "avis", categorie: null, sens: "negatif", note_sur_5: 2, message: "Trop lent sur les biopsies", statut: null, utilisateur: U.a, cree_le: horo(7), ref: "r-1" },
  { id: "etude_reponse:q-1", origine: "etude", nature: "avis", categorie: "questionnaire_fin_etude", sens: null, note_sur_5: null, message: "Le temps de réponse", statut: null, utilisateur: U.c, cree_le: horo(9), ref: "q-1" },
  { id: "signalement:s-2", origine: "v3", nature: "signalement", categorie: "amelioration", sens: null, note_sur_5: null, message: "Pouvoir réordonner les sections du compte rendu", statut: "traite", utilisateur: U.b, cree_le: horo(11), ref: "s-2" },
  { id: "etude:d-1", origine: "etude", nature: "avis", categorie: "commentaire_validation", sens: null, note_sur_5: null, message: "Compte rendu correct, une marge à reformuler", statut: null, utilisateur: U.b, cree_le: horo(12), ref: "d-1" },
];

export const utilisateursDemo: UtilisateurAdmin[] = [
  { id: "u-a", email: "alice@labo.example", nom: "Alice Pathologiste", role: "admin", cree_le: horo(120), derniere_activite: horo(0), projets_v3: 42, comptes_rendus_anciens: 11, dossiers_etude: 6, habilite_valideur: true },
  { id: "u-c", email: "chloe@labo.example", nom: "Chloé Pathologiste", role: "user", cree_le: horo(90), derniere_activite: horo(2), projets_v3: 27, comptes_rendus_anciens: 3, dossiers_etude: 4, habilite_valideur: true },
  { id: "u-b", email: "bruno@labo.example", nom: "Bruno Interne", role: "user", cree_le: horo(60), derniere_activite: horo(6), projets_v3: 9, comptes_rendus_anciens: 0, dossiers_etude: 2, habilite_valideur: false },
  { id: "u-d", email: "dora@labo.example", nom: "Dora Technicienne", role: "user", cree_le: horo(30), derniere_activite: null, projets_v3: 0, comptes_rendus_anciens: 0, dossiers_etude: 0, habilite_valideur: false },
];

const critere = (cle: string, libelle: string, valeur: number | null, seuil: number | null, sens: string, effectif: number, mini: number, unite = "taux", note = ""): EtudeData["couverture"][number] => ({
  cle, libelle, rang: "principal", unite, valeur, seuil, sens, effectif, effectif_minimal: mini,
  atteint: valeur == null || seuil == null ? null : sens === "au_plus" ? valeur <= seuil : valeur >= seuil, observable: true, donnees_suffisantes: effectif >= mini, note,
});

export const etudeDemo: EtudeData = {
  couverture: [
    critere("propositions_non_soutenues", "Propositions non soutenues par la dictée", 0.012, 0.02, "au_plus", 214, 200, "taux", "Référence externe : environ 1,5 % dans la littérature."),
    critere("acceptation_sans_modification", "Acceptation sans modification", 0.54, 0.6, "au_moins", 214, 200),
    critere("omissions_signalees", "Comptes rendus où une omission est signalée", null, 0.05, "au_plus", 9, 25),
    critere("score_fsus", "Score F-SUS moyen", 78.4, 70, "au_moins", 6, 10, "score"),
  ],
  corpus: { nb_praticiens: 5, nb_praticiens_sans_dossier: 1, nb_dossiers: 12, nb_exclus: 1, nb_dossiers_clos: 9, nb_commentes: 4, nb_abandons: 1 },
  praticiens_favorables: { libelle: "Praticiens souhaitant continuer", numerateur: 4, denominateur: 5, valeur: 0.8 },
};

export const santeDemo: SanteData = {
  version: "3.0.0+demo",
  base: { type: "postgresql", tables: [
    { nom: "audit_log", lignes: 0 }, { nom: "conformite_audit", lignes: 128 }, { nom: "etude_dossiers", lignes: 12 }, { nom: "reports", lignes: 31 },
    { nom: "signalements", lignes: 7 }, { nom: "telemetrie_evenements", lignes: 2410 }, { nom: "users", lignes: 14 } ] },
  controles: [
    { nom: "orphelins", ok: true, detail: "Aucun orphelin (reports, télémétrie, signalements, tables etude_*)." },
    { nom: "doublons_comptes", ok: true, detail: "Aucun e-mail en double (casse ignorée)." },
    { nom: "comptes_de_test", ok: false, detail: "3 compte(s) de test (@example.com) : à passer en revue." },
    { nom: "chaine_audit", ok: true, detail: "Chaîne intègre : 128 entrée(s) vérifiée(s)." },
    { nom: "signalements_en_double", ok: true, detail: "Aucun signalement en double." },
    { nom: "recopie_non_conformites", ok: true, detail: "2 non-conformité(s) recopiée(s) sur 2 dans l'ancienne table (conservée)." },
    { nom: "tables_jamais_ecrites", ok: false, detail: "1 table(s) vide(s) : audit_log (informatif : une table vide n'est pas une erreur)." },
  ],
};

const filtrer = (f: { origine: Origine | ""; categorie: string; statut: Statut | ""; page: number }): RetoursData => {
  const items = retoursDemo.filter((r) => (!f.origine || r.origine === f.origine) && (!f.categorie || r.categorie === f.categorie) && (!f.statut || r.statut === f.statut));
  return { total: items.length, page: f.page, items: items.slice((f.page - 1) * 25, f.page * 25) };
};

/** Implémentation de démonstration : aucune requête, les modifications vivent en mémoire pour la session. */
export const apiDemo: AdminApi = {
  vueEnsemble: async (p) => vueEnsembleDemo(p),
  recommandations: async () => recommandationsDemo,
  syntheseTelemetrie: async (p) => syntheseDemo(p),
  retours: async (f) => filtrer(f),
  majSignalement: async (id, corps) => {
    const r = retoursDemo.find((x) => x.ref === id);
    if (r && corps.statut) r.statut = corps.statut;
    return { id, user_id: r?.utilisateur.id ?? "u-a", categorie: r?.categorie ?? "amelioration", message: r?.message ?? "", projet_hash: null, ecran: "projet", version_app: "3.0.0",
      statut: (corps.statut ?? r?.statut ?? "ouvert") as Statut, note_admin: corps.note_admin ?? null, cree_le: r?.cree_le ?? horo(0), maj_le: horo(0), doublon_de: null, gravite: null, categorie_iso: null } satisfies SignalementMaj;
  },
  utilisateurs: async () => utilisateursDemo,
  habilitation: async (userId, habilite) => ({ user_id: userId, habilite }),
  etude: async () => etudeDemo,
  dossiersEtude: async () => [
    { id: "d-1", praticien_nom: "Bruno Interne", index_session: 1, organe: "sein", cree_a: horo(12), abandonne: false, statut: "clos", nb_propositions: 14, nb_decidees: 14, exclu: false, motif_exclusion: null },
    { id: "d-2", praticien_nom: "Chloé Pathologiste", index_session: 2, organe: "colon", cree_a: horo(14), abandonne: false, statut: "en_cours", nb_propositions: 10, nb_decidees: 6, exclu: false, motif_exclusion: null },
  ],
  exporter: async () => undefined,
  sante: async () => santeDemo,
};



function alea(graine: number): () => number {
  let s = graine;
  return () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; };
}

export function syntheseDemo(periode: Periode): Synthese {
  const jours = periode === "tout" ? 90 : parseInt(periode, 10);
  const r = alea(7 + jours);
  const fin = new Date(Date.UTC(2026, 10, 15));
  const series = Array.from({ length: jours }, (_, i) => {
    const d = new Date(fin); d.setUTCDate(d.getUTCDate() - (jours - 1 - i));
    const semaine = d.getUTCDay() === 0 || d.getUTCDay() === 6;
    const projets = semaine ? Math.round(r() * 4) : Math.round(14 + r() * 16 + i * 0.1);
    return { jour: d.toISOString().slice(0, 10), projets, utilisateurs: Math.min(12, Math.round(projets / 3) + 1), exports: Math.round(projets * 0.8), erreurs: r() < 0.2 ? 1 : 0 };
  });
  const total = series.reduce((a, s) => a + s.projets, 0);
  return {
    periode_jours: jours, debut: series[0].jour, fin: series[series.length - 1].jour,
    kpi: {
      projets_generes: total, utilisateurs_actifs: 11, dau_moyen: 5.4, mau: 14,
      temps_median_generation_ms: 9200, temps_median_export_ms: 148000, exports: Math.round(total * 0.8),
      taux_exports_sans_retouche: 0.46, retouches_total: Math.round(total * 2.3), retouches_moyennes_par_projet: 2.3,
      feedback_positif: 41, feedback_negatif: 9, precision_correcteur: 0.88, erreurs: 6,
      variation: { projets_generes: 0.18, utilisateurs_actifs: 0.1, temps_median_generation_ms: -0.12, temps_median_export_ms: -0.07, taux_exports_sans_retouche: 0.05 },
    },
    retouches: {
      par_type_element: [{ valeur: "phrase", retouches: 120, par_projet: 1.4 }, { valeur: "trou", retouches: 64, par_projet: 0.7 }, { valeur: "liste", retouches: 18, par_projet: 0.2 }, { valeur: "titre", retouches: 6, par_projet: 0.1 }],
      par_statut: [{ valeur: "reformule", retouches: 95, par_projet: 1.1 }, { valeur: "normalise", retouches: 52, par_projet: 0.6 }, { valeur: "a_completer", retouches: 40, par_projet: 0.5 }, { valeur: "dicte", retouches: 21, par_projet: 0.2 }],
      par_niveau: [{ valeur: "basse", retouches: 88, par_projet: 1 }, { valeur: "moyenne", retouches: 74, par_projet: 0.9 }, { valeur: "haute", retouches: 46, par_projet: 0.5 }],
    },
    trous: [
      { champ_id: "taille_tumorale", combles: 48, ignores: 6, taux_ignore: 0.11 },
      { champ_id: "grade_sbr", combles: 30, ignores: 12, taux_ignore: 0.29 },
      { champ_id: "emboles_vasculaires", combles: 9, ignores: 24, taux_ignore: 0.73 },
      { champ_id: "marges_distance", combles: 21, ignores: 10, taux_ignore: 0.32 },
      { champ_id: "ki67", combles: 6, ignores: 15, taux_ignore: 0.71 },
    ],
    alertes: [
      { alerte_type: "unite", resolues: 22, ignorees: 15, taux_ignore: 0.41 },
      { alerte_type: "manquant", resolues: 51, ignorees: 8, taux_ignore: 0.14 },
      { alerte_type: "incoherence", resolues: 17, ignorees: 3, taux_ignore: 0.15 },
      { alerte_type: "phonetique", resolues: 33, ignorees: 5, taux_ignore: 0.13 },
    ],
    corrections: { acceptees: 88, rejetees: 12, precision: 0.88 },
    feedback: { positif: 41, negatif: 9, motifs: [{ motif: "omission", n: 4 }, { motif: "mauvaise_unite", n: 3 }, { motif: "mise_en_forme", n: 2 }] },
    organes: [{ organe: "sein", n: 62 }, { organe: "colon", n: 41 }, { organe: "prostate", n: 33 }, { organe: "peau", n: 28 }, { organe: "poumon", n: 17 }],
    service: { niveaux: [{ niveau: "N0", projets: Math.round(total * 0.82) }, { niveau: "N1", projets: Math.round(total * 0.11) }, { niveau: "N2", projets: Math.round(total * 0.05) }, { niveau: "N3", projets: Math.round(total * 0.02) }], erreurs: [{ code: "timeout", n: 3 }, { code: "stt", n: 2 }, { code: "reseau", n: 1 }] },
    series,
    top_utilisateurs: [
      { user_id: "u1", compte: "pathologiste.a@labo.example", jours_actifs: Math.min(jours, 19), projets: 88 },
      { user_id: "u2", compte: "pathologiste.b@labo.example", jours_actifs: Math.min(jours, 15), projets: 61 },
      { user_id: "u3", compte: "pathologiste.c@labo.example", jours_actifs: Math.min(jours, 11), projets: 39 },
      { user_id: "u4", compte: "interne.d@labo.example", jours_actifs: Math.min(jours, 6), projets: 17 },
    ],
  };
}

export const recommandationsDemo: Recommandation[] = [
  { id: "champ_ignore_emboles_vasculaires", severite: "attention", cible: "emboles_vasculaires", titre: "Le champ emboles_vasculaires est ignoré dans 73 % des cas", detail: "24 ignorés sur 33 trous : vérifier sa pertinence (obligatoire ? libellé ? contexte ?).", valeur: 0.73, seuil: 0.6 },
  { id: "champ_ignore_ki67", severite: "attention", cible: "ki67", titre: "Le champ ki67 est ignoré dans 71 % des cas", detail: "15 ignorés sur 21 trous : vérifier sa pertinence (obligatoire ? libellé ? contexte ?).", valeur: 0.71, seuil: 0.6 },
  { id: "alerte_ignoree_unite", severite: "attention", cible: "unite", titre: "L'alerte unite est rejetée 41 %", detail: "15 rejets sur 37 : probables faux positifs, revoir le seuil ou la règle.", valeur: 0.41, seuil: 0.4 },
  { id: "retouches_elevees", severite: "attention", cible: "export", titre: "Seuls 46 % des exports sont sans retouche", detail: "Identifier les types d'éléments les plus retouchés et ajuster les gabarits.", valeur: 0.46, seuil: 0.5 },
];
