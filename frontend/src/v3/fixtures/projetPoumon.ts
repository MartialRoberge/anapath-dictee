// Projet de démonstration réaliste (biopsies bronchiques, adénocarcinome). Données fictives.
// Les offsets de sources sont calculés depuis la dictée : ils restent exacts si le texte change.
import type { Alerte, Code, Correction, Element, Preuve, Projet, SourceRef, TraceStep } from "../types";

const BRUTE =
  "biopsie bronchique du lobe supérieur droit bronchoscopie pour masse hilaire quatre fragments mesurant de 2 à 4 cm " +
  "prolifération tumorale carcinomateuse infiltrante d'architecture acineuse et lépidique avec nécrose focale " +
  "les cellules expriment TTF un et la cytokératine sept P quarante négatif pas d'envahissement vasculaire identifié " +
  "conclusion adéno carcinome acineux infiltrant du poumon";

const CORRECTIONS_DEF: Array<[string, string, string, string[], string]> = [
  ["TTF un", "TTF1", "variante phonétique connue du marqueur TTF1 (acronyme)", ["TTF1", "TTF-1"], "c1"],
  ["cytokératine sept", "cytokératine 7", "chiffre dicté en lettres : CK7", ["cytokératine 7", "cytokératine 17"], "c2"],
  ["P quarante", "P40", "marqueur P40 dicté en lettres", ["P40", "P63"], "c3"],
  ["adéno carcinome", "adénocarcinome", "mot coupé par la reconnaissance vocale", ["adénocarcinome"], "c4"],
];

const CORRIGEE = CORRECTIONS_DEF.reduce((t, [o, c]) => t.replace(o, c), BRUTE);

const span = (needle: string, texte = CORRIGEE): SourceRef => {
  const debut = texte.indexOf(needle);
  return { kind: "dictee", ref: "dictee", libelle: "Dictée", extrait: needle, debut: debut < 0 ? null : debut, fin: debut < 0 ? null : debut + needle.length };
};

const corrections: Correction[] = CORRECTIONS_DEF.map(([original, corrige, raison, candidats, id], i) => {
  const debut = BRUTE.indexOf(original);
  return {
    id, original, corrige, debut, fin: debut + original.length, confiance: [0.93, 0.9, 0.88, 0.97][i], raison, candidats,
    sources: [{ kind: "agent", ref: "correcteur", libelle: "Correcteur phonétique" }, { kind: "kb", ref: "lexique_acp", libelle: "Lexique ACP · Acronymes", fiabilite: "B", extrait: "Lexique, rubrique Marqueurs d'immunohistochimie" }],
    appliquee: true,
  };
});

const KB_INCA: SourceRef = { kind: "kb", ref: "inca_poumon_2011", libelle: "INCa · Cancer bronchopulmonaire : données minimales", fiabilite: "A", url: "https://www.e-cancer.fr", extrait: "Le statut PD-L1 et la recherche de biomarqueurs figurent parmi les données attendues." };
const KB_OMS: SourceRef = { kind: "kb", ref: "oms_2021_thorax", libelle: "OMS 2021 · Tumeurs thoraciques", fiabilite: "A", url: "https://tumourclassification.iarc.who.int", extrait: "Chapitre Adénocarcinome, classification des sous-types" };
const REGLE_U1: SourceRef = { kind: "regle", ref: "U1", libelle: "Règle de plausibilité des unités", fiabilite: "B", extrait: "Règle U1, tailles maximales par prélèvement" };

const KB_MACRO: SourceRef = { kind: "kb", ref: "acp_macro_biopsies", libelle: "Bible de la pathologiste · Biopsies thoraciques", fiabilite: "C", extrait: "Les fragments biopsiques se décrivent en millimètres." };

const el = (id: string, section_id: string, texte: string, extra: Partial<Element> & { confiance: number }): Element => ({
  id, section_id, type: "phrase", texte, statut: "dicte",
  niveau: extra.confiance >= 0.85 ? "haute" : extra.confiance >= 0.6 ? "moyenne" : "basse",
  sources: [], explication: "", obligatoire: false, options: [], ...extra,
});

// Preuves : l'effet de chacune s'additionne pour donner la confiance affichée.
const dictee = (needle: string, detail: string, effet: number, titre = "Dicté tel quel"): Preuve => ({ categorie: "dictee", verdict: "ok", titre, detail, source: span(needle), effet });
const relecteur = (detail: string, effet: number): Preuve => ({ categorie: "modele", verdict: effet < 0 ? "attention" : "ok", titre: "Relecteur de fidélité", detail, effet });

const elements: Element[] = [
  el("e1", "s1", "Biopsies bronchiques du lobe supérieur droit, bronchoscopie pour masse hilaire.", { confiance: 0.96, sources: [span("biopsie bronchique du lobe supérieur droit bronchoscopie pour masse hilaire")], explication: "Reprise fidèle de la dictée ; organe et site identifiés.",
    preuves: [dictee("biopsie bronchique du lobe supérieur droit bronchoscopie pour masse hilaire", "Phrase reprise mot pour mot, avec la majuscule et la ponctuation en plus.", 0.9, "Ancrage dans la dictée"), relecteur("Aucun fait ajouté ni retiré.", 0.06)] }),
  el("e2", "s2", "Quatre fragments mesurant de 2 à 4 cm.", { confiance: 0.48, sources: [span("quatre fragments mesurant de 2 à 4 cm"), REGLE_U1], explication: "Mesure conservée telle que dictée ; l'unité est inhabituelle pour des fragments biopsiques (voir « À vérifier »).",
    a_verifier: "2 à 4 cm est très grand pour des fragments de biopsie bronchique : millimètres dictés par erreur ?",
    preuves: [
      dictee("quatre fragments mesurant de 2 à 4 cm", "« Quatre fragments mesurant de 2 à 4 cm » : nombre et unité repris sans modification.", 0.75, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "attention", titre: "Taille plausible pour une biopsie bronchique", detail: "Un fragment biopsique dépasse rarement 5 mm.", calcul: "20–40 mm > 5 mm (max biopsie bronchique)", source: REGLE_U1, effet: -0.15 },
      { categorie: "regle", verdict: "ok", titre: "Nombre de fragments", detail: "Dicté en toutes lettres, converti sans ambiguïté.", calcul: "« quatre » = 4" },
      { categorie: "referentiel", verdict: "info", titre: KB_MACRO.libelle, detail: "Les fragments biopsiques se décrivent en millimètres.", source: KB_MACRO },
      relecteur("Unité conservée comme dictée : le modèle n'a pas converti cm en mm de sa propre initiative.", -0.12),
    ] }),
  el("e3", "s3", "Prolifération tumorale carcinomateuse infiltrante, d'architecture acineuse et lépidique.", { confiance: 0.9, statut: "reformule", sources: [span("prolifération tumorale carcinomateuse infiltrante d'architecture acineuse et lépidique"), KB_OMS], explication: "Reformulation de ponctuation uniquement ; aucun terme ajouté.",
    preuves: [
      dictee("prolifération tumorale carcinomateuse infiltrante d'architecture acineuse et lépidique", "Tous les termes viennent de la dictée ; seule une virgule a été ajoutée.", 0.82, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "ok", titre: "Aucun terme ajouté", detail: "Chaque mot du texte figure dans la dictée.", calcul: "14 mots sur 14 retrouvés" },
      { categorie: "referentiel", verdict: "info", titre: KB_OMS.libelle, detail: "Architectures acineuse et lépidique : termes de la classification.", source: KB_OMS, effet: 0.04 },
      { categorie: "modele", verdict: "ok", titre: "Reformulation légère", detail: "Le modèle a ponctué la phrase sans modifier le sens.", effet: 0.04 },
    ] }),
  el("e4", "s3", "Nécrose focale.", { confiance: 0.72, sources: [span("nécrose focale")], explication: "Reprise à l'identique ; formulation très brève, à relire.",
    preuves: [dictee("nécrose focale", "Deux mots dictés, repris à l'identique. Phrase très courte : peu de contexte pour la confirmer.", 0.72, "Ancrage dans la dictée")] }),
  el("e5", "s3", "Pas d'envahissement vasculaire identifié.", { confiance: 0.93, sources: [span("pas d'envahissement vasculaire identifié")], explication: "Négation dictée, conservée à l'identique.",
    preuves: [
      dictee("pas d'envahissement vasculaire identifié", "La négation est dictée explicitement.", 0.88, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "ok", titre: "Négation conservée", detail: "Le sens négatif de la dictée est préservé.", calcul: "1 négation dictée, 1 négation rédigée" },
      relecteur("Aucune négation inversée ou perdue.", 0.05),
    ] }),
  el("e6", "s4", "Phénotype", { type: "titre", confiance: 1, statut: "normalise", explication: "Titre de sous-partie." }),
  el("e7", "s4", "TTF1 exprimé.", { type: "liste", confiance: 0.88, statut: "normalise", sources: [span("les cellules expriment TTF1"), { kind: "agent", ref: "correcteur", libelle: "Correcteur phonétique" }], explication: "« TTF un » corrigé en TTF1 ; les cellules expriment le marqueur.",
    preuves: [
      dictee("les cellules expriment TTF1", "« Les cellules expriment TTF un » : le marqueur est exprimé.", 0.8, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "ok", titre: "Marqueur connu", detail: "TTF1 figure dans le lexique des anticorps.", calcul: "« TTF un » → TTF1 (0,93)", effet: 0.08 },
      { categorie: "modele", verdict: "ok", titre: "Correction à l'écoute", detail: "« TTF un » remplacé par TTF1 (acronyme).", source: { kind: "agent", ref: "correcteur", libelle: "Correcteur phonétique" } },
    ] }),
  el("e7b", "s4", "Cytokératine 7 (CK7) exprimée.", { type: "liste", confiance: 0.86, statut: "normalise", sources: [span("la cytokératine 7")], explication: "« cytokératine sept » corrigé en cytokératine 7 (CK7).",
    preuves: [
      dictee("la cytokératine 7", "« La cytokératine sept » : marqueur exprimé, nombre dicté en lettres.", 0.78, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "ok", titre: "Marqueur connu", detail: "CK7 figure dans le lexique des anticorps.", calcul: "« cytokératine sept » → CK7 (0,90)", effet: 0.08 },
      { categorie: "modele", verdict: "ok", titre: "Correction à l'écoute", detail: "Chiffre dicté en lettres converti : CK7.", source: { kind: "agent", ref: "correcteur", libelle: "Correcteur phonétique" } },
    ] }),
  el("e8", "s4", "P40 négatif.", { type: "liste", confiance: 0.84, sources: [span("P40 négatif")], explication: "Correction phonétique « P quarante » -> P40, à confirmer.",
    preuves: [
      dictee("P40 négatif", "« P quarante négatif » : marqueur dicté négatif.", 0.78, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "attention", titre: "Marqueur ambigu à l'oral", detail: "« P quarante » peut aussi être P63 ; P40 retenu.", calcul: "P40 0,88 contre P63 0,09", effet: 0.06 },
      { categorie: "modele", verdict: "ok", titre: "Correction à l'écoute", detail: "« P quarante » remplacé par P40.", source: { kind: "agent", ref: "correcteur", libelle: "Correcteur phonétique" } },
    ] }),
  el("e9", "s4", "PD-L1 (% de cellules tumorales)", { type: "trou", statut: "a_completer", confiance: 0, niveau: "basse", obligatoire: true, champ_id: "pdl1_tps", unite: "%", options: ["< 1 %", "1 à 49 %", "≥ 50 %", "Non réalisé"], sources: [KB_INCA], explication: "Donnée attendue pour un carcinome bronchopulmonaire ; non dictée, donc laissée à compléter.",
    a_verifier: "Non dicté : à compléter avant validation.",
    preuves: [
      { categorie: "dictee", verdict: "attention", titre: "PD-L1 n'est pas mentionné dans la dictée", detail: "", calcul: "pd-l1, pdl1, ttf, tps" },
      { categorie: "regle", verdict: "info", titre: "Champ exigé", detail: "Exigé pour : poumon · biopsie · carcinome" },
      { categorie: "referentiel", verdict: "info", titre: KB_INCA.libelle, detail: "", source: KB_INCA },
    ] }),
  el("e10", "s5", "Biologie moléculaire (EGFR, ALK, ROS1)", { type: "trou", statut: "a_completer", confiance: 0, niveau: "basse", obligatoire: true, champ_id: "bm_poumon", options: ["Demandée", "Non demandée", "Résultat en attente"], sources: [KB_INCA], explication: "Information non dictée ; aucune valeur supposée.",
    a_verifier: "Non dicté : à compléter avant validation.",
    preuves: [
      { categorie: "dictee", verdict: "attention", titre: "La biologie moléculaire n'est pas mentionnée dans la dictée", detail: "", calcul: "egfr, alk, ros1, biologie moléculaire" },
      { categorie: "regle", verdict: "info", titre: "Champ exigé", detail: "Exigé pour : poumon · biopsie · adénocarcinome" },
      { categorie: "referentiel", verdict: "info", titre: KB_INCA.libelle, detail: "", source: KB_INCA },
    ] }),
  el("e11", "s6", "Adénocarcinome acineux infiltrant du poumon.", { confiance: 0.9, statut: "normalise", sources: [span("adénocarcinome acineux infiltrant du poumon"), KB_OMS], explication: "Diagnostic repris tel que dicté ; seule la correction phonétique « adénocarcinome » est appliquée.",
    preuves: [
      dictee("adénocarcinome acineux infiltrant du poumon", "« Adéno carcinome » recollé en un mot ; le reste est repris tel que dicté.", 0.82, "Ancrage dans la dictée"),
      { categorie: "regle", verdict: "ok", titre: "Cohérent avec la microscopie", detail: "Architecture acineuse décrite plus haut.", calcul: "acineux (conclusion) = acineuse (microscopie)", effet: 0.05 },
      { categorie: "referentiel", verdict: "info", titre: KB_OMS.libelle, detail: "Terme de la classification.", source: KB_OMS, effet: 0.03 },
    ] }),
];

const alertes: Alerte[] = [
  { id: "a1", type: "manquant", gravite: "bloquant", message: "PD-L1 non dicté.", element_ids: ["e9"], suggestion: "Compléter le pourcentage ou indiquer « Non réalisé ».", confiance: 0.95, sources: [KB_INCA], agent: "Vérificateur de complétude",
    pourquoi: "Ce champ est attendu pour un carcinome bronchopulmonaire et n'apparaît pas dans la dictée.", calcul: "1 champ obligatoire attendu, 0 dicté", action: "Compléter le pourcentage, ou indiquer « Non réalisé »." },
  { id: "a2", type: "unite", gravite: "attention", message: "« 2 à 4 cm » pour des fragments biopsiques.", element_ids: ["e2"], suggestion: "2 à 4 mm", confiance: 0.82, sources: [REGLE_U1], agent: "Vérificateur d'unités",
    pourquoi: "Des fragments de biopsie bronchique mesurent en général quelques millimètres : les millimètres ont peut-être été dictés par erreur.", calcul: "20–40 mm > 5 mm (max biopsie bronchique)", action: "Confirmer 2 à 4 cm, ou corriger en 2 à 4 mm." },
  { id: "a3", type: "manquant", gravite: "attention", message: "Biologie moléculaire non mentionnée.", element_ids: ["e10"], suggestion: null, confiance: 0.8, sources: [KB_INCA], agent: "Vérificateur de complétude",
    pourquoi: "EGFR, ALK et ROS1 sont attendus pour un adénocarcinome du poumon.", calcul: "1 champ attendu, 0 dicté", action: "Indiquer si la recherche est demandée, non demandée ou en attente." },
  { id: "a4", type: "phonetique", gravite: "info", message: "« P quarante » compris comme P40.", element_ids: ["e8"], suggestion: "Confirmer P40", confiance: 0.88, sources: [], agent: "Correcteur phonétique",
    pourquoi: "À l'oral, « P quarante » ressemble à « P soixante-trois » ; P40 est le plus probable.", calcul: "P40 0,88 contre P63 0,09", action: "Confirmer P40, ou choisir P63 dans l'onglet Dictée." },
  { id: "a5", type: "codage", gravite: "info", message: "Code ADICAP proposé à titre de suggestion.", element_ids: ["e11"], suggestion: null, confiance: 0.6, sources: [], agent: "Codeur",
    pourquoi: "La lésion est codée, mais la topographie fine n'est pas vérifiée dans la table ADICAP.", calcul: "confiance du code 0,55", action: "Contrôler le code dans l'onglet Codes avant de le reporter." },
];

const codes: Code[] = [
  { systeme: "SNOMED_CT", code: "35917007", libelle: "Adénocarcinome", statut: "certain", confiance: 0.93, sources: [span("adénocarcinome")], explication: "Terme dicté en conclusion, correspondance exacte." },
  { systeme: "CIM_O3", code: "8551/3", libelle: "Adénocarcinome acineux", statut: "partiel", confiance: 0.78, sources: [KB_OMS], explication: "Sous-type acineux dicté ; comportement /3 (malin) déduit du libellé." },
  { systeme: "ADICAP", code: "B.H.PO.A7", libelle: "Biopsie, histologie, poumon, adénocarcinome (code à confirmer)", statut: "suggestion", confiance: 0.55, sources: [], explication: "Structure plausible mais morphologie fine non vérifiée dans la table ; à confirmer par le praticien." },
];

const T = (id: string, agent: string, role: TraceStep["role"], titre: string, debut_ms: number, duree_ms: number, modele: string | null, resume: string, details: string[] = []): TraceStep =>
  ({ id, agent, role, titre, statut: "ok", debut_ms, duree_ms, modele, resume, details });

export const traceDemo: TraceStep[] = [
  T("t1", "Transcripteur", "transcripteur", "Transcrire la dictée", 0, 1420, "voxtral-mini-latest", "Dictée de 24 s transcrite (196 mots)."),
  T("t2", "Correcteur phonétique", "correcteur", "Corriger les erreurs de reconnaissance vocale", 1450, 880, "mistral-small-latest", "4 corrections proposées, toutes avec leur raison.", ["« TTF un » -> TTF1", "« cytokératine sept » -> cytokératine 7", "« P quarante » -> P40", "« adéno carcinome » -> adénocarcinome"]),
  T("t3", "Extracteur", "extracteur", "Identifier organe, prélèvement et éléments", 2350, 1210, "mistral-large-latest", "Organe : poumon · biopsie · contexte malin."),
  T("t4", "Vérificateur d'unités", "verificateur", "Vérifier les unités de mesure", 3600, 310, null, "1 mesure inhabituelle signalée (cm pour biopsie)."),
  T("t5", "Vérificateur de complétude", "verificateur", "Vérifier les champs obligatoires", 3600, 420, null, "2 champs attendus non dictés : PD-L1, biologie moléculaire."),
  T("t6", "Codeur", "codeur", "Rechercher les codes ADICAP et SNOMED CT", 4050, 960, "mistral-small-latest", "3 codes : 1 certain, 1 partiel, 1 suggestion."),
  T("t7", "Rédacteur", "redacteur", "Rédiger le projet de compte rendu", 5050, 1830, "mistral-large-latest", "12 éléments, 2 trous à compléter."),
  T("t8", "Relecteur de fidélité", "relecteur", "Relire en vérifiant la fidélité à la dictée", 6900, 1100, "mistral-large-latest", "Aucun fait, mesure ni négation ajouté."),
];

export const projetPoumon: Projet = {
  id: "demo-poumon-001",
  version: "3",
  titre: "EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES BRONCHIQUES",
  dictee: { brute: BRUTE, corrigee: CORRIGEE },
  contexte: { organes: ["poumon"], organes_libelles: ["Poumon"], prelevement: "biopsie", contexte_lesionnel: "malin", niveau_service: "N0" },
  corrections,
  sections: [
    { id: "s1", titre: "Renseignements cliniques", ordre: 1 },
    { id: "s2", titre: "Macroscopie", ordre: 2 },
    { id: "s3", titre: "Microscopie", ordre: 3 },
    { id: "s4", titre: "Immunohistochimie", ordre: 4 },
    { id: "s5", titre: "Biologie moléculaire", ordre: 5 },
    { id: "s6", titre: "Conclusion", ordre: 6 },
  ],
  elements, alertes, codes, trace: traceDemo,
  metriques: { duree_totale_ms: 8000, appels_llm: 5, tokens_entree: 6840, tokens_sortie: 1210, confiance_moyenne: 0.84 },
};

// Trou non obligatoire ajouté pour la démonstration (les tests de référence restent sur `projetPoumon`).
const KB_BIBLE: SourceRef = { kind: "kb", ref: "bible_ihc_poumon", libelle: "Bible de la pathologiste · Biopsies thoraciques", fiabilite: "C", extrait: "Fiche Immunohistochimie, proliférations tumorales" };
const ki67: Element = el("e12", "s4", "Ki67 (% de cellules tumorales)", {
  type: "trou", statut: "a_completer", confiance: 0, niveau: "basse", obligatoire: false, champ_id: "ki67", unite: "%", options: ["< 10 %", "10 à 30 %", "> 30 %", "Non réalisé"],
  sources: [KB_BIBLE], explication: "",
  a_verifier: "Ki67 n'est pas dicté : à compléter, ou à ignorer s'il n'est pas utile ici.",
  preuves: [
    { categorie: "dictee", verdict: "attention", titre: "Ki67 n'est pas mentionné dans la dictée", detail: "", calcul: "ki67, ki-67, mib1, mib-1, index de prolifération" },
    { categorie: "regle", verdict: "info", titre: "Champ exigé", detail: "Exigé pour : poumon · biopsie · carcinome infiltrant" },
    { categorie: "referentiel", verdict: "info", titre: KB_BIBLE.libelle, detail: "", source: KB_BIBLE },
  ],
});
export const projetDemo: Projet = { ...projetPoumon, elements: projetPoumon.elements.flatMap((e) => (e.id === "e9" ? [e, ki67] : [e])) };

export const dicteesExemples = [
  { organe: "Poumon", titre: "Biopsies bronchiques", texte: BRUTE.charAt(0).toUpperCase() + BRUTE.slice(1) + "." },
  { organe: "Côlon", titre: "Colectomie droite", texte: "Colectomie droite pour adénocarcinome du caecum. Tumeur ulcérée de 4 centimètres. Infiltration de la sous-séreuse. Douze ganglions examinés, deux métastatiques. Marges de résection saines." },
  { organe: "Sein", titre: "Microbiopsie", texte: "Microbiopsie mammaire du quadrant supéro-externe gauche. Carcinome canalaire infiltrant de grade 2 de Elston et Ellis. Récepteurs aux oestrogènes positifs à 90 pour cent. HER2 score 1 plus." },
];
