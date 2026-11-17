// Jeu de donnees de demonstration (?demo=1) : deterministe, sans backend, aucune donnee reelle.
import type { Periode, Recommandation, Synthese } from "./types";

function alea(graine: number): () => number {
  let s = graine;
  return () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; };
}

export function syntheseDemo(periode: Periode): Synthese {
  const jours = parseInt(periode, 10);
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
