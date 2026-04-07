/**
 * Base de connaissances pour les champs obligatoires des CR anatomopathologiques.
 *
 * Chaque entree est CONTEXT-AWARE : elle ne s'affiche que pour les organes
 * auxquels elle s'applique (champ organs). Si organs est vide, l'entree
 * s'applique a tous les organes (champ universel).
 *
 * References : ISO 15189, OMS 2022, INCa (donnees minimales), AJCC/UICC TNM 8e ed.
 */

export interface FieldKnowledge {
  keywords: string[];
  title: string;
  why: string;
  norm: string;
  risk: string;
  severity: "error" | "warning";
  icon: string;
  /** Organes auxquels ce champ s'applique. Vide = tous les organes. */
  organs: string[];
}

export const FIELD_KNOWLEDGE: FieldKnowledge[] = [
  // ═══════════════════════════════════════
  // UNIVERSELS (tous organes)
  // ═══════════════════════════════════════
  {
    keywords: ["type histologique", "sous-type", "type de la lesion"],
    title: "Type histologique",
    why: "Le type histologique selon la classification OMS 2022 conditionne la prise en charge therapeutique. Base du diagnostic anatomopathologique.",
    norm: "OMS Classification of Tumours, 5e edition / INCa Donnees minimales",
    risk: "Dossier RCP incomplet. Traitement ne peut etre decide.",
    severity: "error",
    icon: "M",
    organs: [],
  },
  {
    keywords: ["macroscopie", "macro", "examen macroscopique"],
    title: "Description macroscopique",
    why: "La macroscopie documente l'echantillonnage et la taille du prelevement. Indispensable a la tracabilite (ISO 15189).",
    norm: "ISO 15189:2022 / ISO/TS 23824:2024",
    risk: "Defaut de tracabilite. Echantillonnage non verifiable.",
    severity: "warning",
    icon: "E",
    organs: [],
  },
  {
    keywords: ["microscopie", "histologie", "etude histologique", "etude cytologique"],
    title: "Etude histologique",
    why: "L'examen microscopique est le coeur du diagnostic. Sans lui, pas de diagnostic possible.",
    norm: "ISO 15189:2022 / Toutes les recommandations INCa",
    risk: "Compte-rendu invalide sans examen microscopique.",
    severity: "error",
    icon: "H",
    organs: [],
  },
  {
    keywords: ["conclusion"],
    title: "Conclusion diagnostique",
    why: "La conclusion synthetise le diagnostic en termes nosologiques complets. Element lu en premier par le clinicien, utilise pour la RCP.",
    norm: "ISO 15189:2022 / ISO/TS 23824:2024 / INCa",
    risk: "Risque de mauvaise interpretation du CR. Risque medico-legal.",
    severity: "error",
    icon: "C",
    organs: [],
  },
  {
    keywords: ["taille", "dimension", "mesurant", "grand axe", "taille tumorale"],
    title: "Taille tumorale",
    why: "Premier critere du staging pT (TNM). Conditionne directement le stade et le traitement adjuvant.",
    norm: "AJCC/UICC TNM 8e edition / ISO/TS 23824:2024",
    risk: "Impossible de calculer le pT. Stade TNM incomplet.",
    severity: "error",
    icon: "T",
    organs: [],
  },
  {
    keywords: ["embole", "vasculaire", "lymphatique", "invasion vasculaire"],
    title: "Emboles vasculaires/lymphatiques",
    why: "Facteur pronostique independant. Influence la decision de chimiotherapie adjuvante.",
    norm: "OMS 2022 / INCa / ESMO Clinical Practice Guidelines",
    risk: "Facteur pronostique manquant. Peut modifier l'indication de chimiotherapie.",
    severity: "warning",
    icon: "V",
    organs: [],
  },
  {
    keywords: ["engainement", "perinerveux", "perineural"],
    title: "Engainements perinerveux",
    why: "Facteur de risque de recidive locale, particulierement important dans les cancers du pancreas, colorectal et ORL.",
    norm: "OMS 2022 / CAP Synoptic Reporting / INCa",
    risk: "Facteur de recidive locale non documente.",
    severity: "warning",
    icon: "P",
    organs: [],
  },
  {
    keywords: ["marge", "limite", "exerese", "recoupe", "resection"],
    title: "Marges de resection",
    why: "Les marges determinent si l'exerese est complete (R0) ou non (R1/R2). Marge envahie = reprise chirurgicale ou radiotherapie.",
    norm: "ISO/TS 23824:2024 / CAP / INCa",
    risk: "Risque de recidive locale non detecte.",
    severity: "error",
    icon: "R",
    organs: [],
  },
  {
    keywords: ["ganglion", "curage", "ganglionnaire", "sentinelle"],
    title: "Statut ganglionnaire",
    why: "Nombre de ganglions examines et envahis determine le pN et le pronostic.",
    norm: "AJCC/UICC TNM 8e edition / INCa",
    risk: "pN indeterminable. Risque de sous-staging.",
    severity: "error",
    icon: "N",
    organs: [],
  },

  // ═══════════════════════════════════════
  // STAGING pTNM (pieces operatoires carcinologiques uniquement)
  // ═══════════════════════════════════════
  {
    keywords: ["ptnm", "tnm", "staging", "stade"],
    title: "Classification pTNM",
    why: "Standard international pour classifier l'extension tumorale. Obligatoire pour les pieces operatoires carcinologiques.",
    norm: "AJCC/UICC TNM Classification, 8e edition (2017) / INCa",
    risk: "Dossier RCP incomplet. Risque de sous-traitement ou sur-traitement.",
    severity: "error",
    icon: "S",
    organs: [],
  },

  // ═══════════════════════════════════════
  // SEIN UNIQUEMENT
  // ═══════════════════════════════════════
  {
    keywords: ["statut re", "recepteurs estrogenes", "recepteurs oestrogenes", "re positif", "re negatif"],
    title: "Recepteurs aux estrogenes (RE)",
    why: "Determine l'eligibilite a l'hormonotherapie dans le cancer du sein. Facteur predictif majeur.",
    norm: "ASCO/CAP Guidelines on ER Testing (2020) / INCa Donnees minimales sein",
    risk: "Hormonotherapie non decidable. Perte de chance therapeutique.",
    severity: "error",
    icon: "H",
    organs: ["sein"],
  },
  {
    keywords: ["statut rp", "recepteurs progesterone", "rp positif", "rp negatif"],
    title: "Recepteurs a la progesterone (RP)",
    why: "Complete le profil hormonal du cancer du sein. Contribue a la classification moleculaire.",
    norm: "ASCO/CAP Guidelines on PR Testing (2020) / INCa",
    risk: "Profil hormonal incomplet.",
    severity: "error",
    icon: "H",
    organs: ["sein"],
  },
  {
    keywords: ["her2", "her-2", "herceptest", "c-erbb-2"],
    title: "Statut HER2",
    why: "Determine l'eligibilite aux therapies ciblees anti-HER2 (trastuzumab). Score 2+ necessite FISH/CISH.",
    norm: "ASCO/CAP HER2 Testing Guidelines (2023) / INCa",
    risk: "Perte de chance si HER2+ non detecte.",
    severity: "error",
    icon: "2",
    organs: ["sein", "estomac"],
  },
  {
    keywords: ["ki67", "ki-67", "index de proliferation"],
    title: "Index Ki-67",
    why: "Mesure la proliferation tumorale. Participe a la classification moleculaire (Luminal A vs B) du cancer du sein.",
    norm: "St Gallen International Expert Consensus / INCa",
    risk: "Classification moleculaire impossible.",
    severity: "warning",
    icon: "K",
    organs: ["sein"],
  },
  {
    keywords: ["grade sbr", "grade nottingham", "sbr", "nottingham"],
    title: "Grade SBR/Nottingham",
    why: "Evalue l'agressivite du cancer du sein. 3 composantes : tubules, mitoses, atypies nucleaires.",
    norm: "OMS 2022 / INCa Donnees minimales sein",
    risk: "Evaluation pronostique incomplete.",
    severity: "error",
    icon: "G",
    organs: ["sein"],
  },
  {
    keywords: ["composante in situ", "dcis", "lcis", "in situ"],
    title: "Composante in situ",
    why: "Influence le risque de recidive locale et la decision de radiotherapie dans le cancer du sein.",
    norm: "OMS 2022 / INCa Donnees minimales sein",
    risk: "Risque de recidive locale non correctement evalue.",
    severity: "warning",
    icon: "L",
    organs: ["sein"],
  },
  {
    keywords: ["effraction capsulaire", "rupture capsulaire"],
    title: "Effraction capsulaire ganglionnaire",
    why: "Facteur pronostique pejoratif independant. Modifie le staging et l'indication de radiotherapie.",
    norm: "AJCC 8e edition / INCa",
    risk: "Facteur pronostique pejoratif non documente.",
    severity: "warning",
    icon: "F",
    organs: ["sein"],
  },

  // ═══════════════════════════════════════
  // COLON-RECTUM
  // ═══════════════════════════════════════
  {
    keywords: ["grade", "differenciation", "degre de differenciation"],
    title: "Grade de differenciation",
    why: "Evalue le degre de differenciation de l'adenocarcinome colorectal. Determine le pronostic.",
    norm: "OMS 2022 / INCa Donnees minimales colon-rectum",
    risk: "Evaluation pronostique incomplete.",
    severity: "error",
    icon: "G",
    organs: ["colon_rectum"],
  },
  {
    keywords: ["crm", "circonferentielle", "marge circonferentielle"],
    title: "Marge circonferentielle (CRM)",
    why: "Specifique au rectum. CRM < 1 mm = risque de recidive locale eleve. Conditionne la radiotherapie.",
    norm: "INCa Donnees minimales rectum / ESMO / NCCN",
    risk: "Risque de recidive locale non evalue pour le rectum.",
    severity: "error",
    icon: "R",
    organs: ["colon_rectum"],
  },
  {
    keywords: ["tumour budding", "budding"],
    title: "Tumour budding",
    why: "Facteur pronostique reconnu dans le cancer colorectal. Classifie en 3 grades (ITBCC).",
    norm: "ITBCC 2024 / OMS 2022 / INCa",
    risk: "Facteur pronostique emergent non documente.",
    severity: "warning",
    icon: "B",
    organs: ["colon_rectum"],
  },
  {
    keywords: ["mmr", "msi", "microsatellite", "statut mmr"],
    title: "Statut MMR/MSI",
    why: "Determine l'eligibilite a l'immunotherapie dans le cancer colorectal. Recherche systematique recommandee.",
    norm: "ESMO / INCa / NCCN Guidelines",
    risk: "Eligibilite a l'immunotherapie non evaluable.",
    severity: "warning",
    icon: "I",
    organs: ["colon_rectum"],
  },
  {
    keywords: ["kras", "nras", "braf", "statut kras", "statut ras"],
    title: "Statut KRAS/NRAS/BRAF",
    why: "Determine l'eligibilite aux anti-EGFR dans le cancer colorectal metastatique.",
    norm: "ESMO / INCa / NCCN Guidelines",
    risk: "Therapies ciblees anti-EGFR non envisageables.",
    severity: "warning",
    icon: "D",
    organs: ["colon_rectum"],
  },
  {
    keywords: ["mesorectum", "qualite du mesorectum"],
    title: "Qualite du mesorectum",
    why: "Evalue la qualite de l'exerese chirurgicale du rectum. 3 grades (complet, presque complet, incomplet).",
    norm: "INCa Donnees minimales rectum / Quirke classification",
    risk: "Qualite chirurgicale non evaluee.",
    severity: "warning",
    icon: "Q",
    organs: ["colon_rectum"],
  },
  {
    keywords: ["regression", "trg", "score de regression"],
    title: "Score de regression tumorale (TRG)",
    why: "Apres traitement neoadjuvant rectal, evalue la reponse histologique. Guide le traitement adjuvant.",
    norm: "OMS 2022 / AJCC 8e edition / INCa",
    risk: "Reponse au traitement neoadjuvant non evaluable.",
    severity: "warning",
    icon: "W",
    organs: ["colon_rectum"],
  },

  // ═══════════════════════════════════════
  // POUMON
  // ═══════════════════════════════════════
  {
    keywords: ["pattern predominant", "pattern", "architecture predominante"],
    title: "Pattern predominant",
    why: "Obligatoire pour les adenocarcinomes pulmonaires (OMS 2021). Determine le pronostic et la strategie therapeutique.",
    norm: "OMS 2021 Classification Poumon / INCa Donnees minimales poumon",
    risk: "Sous-typage incomplet de l'adenocarcinome.",
    severity: "error",
    icon: "A",
    organs: ["poumon"],
  },
  {
    keywords: ["pd-l1", "pdl1", "tps", "cps"],
    title: "PD-L1 (TPS/CPS)",
    why: "Determine l'eligibilite a l'immunotherapie anti-PD-1/PD-L1. Critique dans le poumon, la vessie et le melanome.",
    norm: "ESMO / NCCN / Avis HAS immunotherapie",
    risk: "Eligibilite a l'immunotherapie non evaluable.",
    severity: "warning",
    icon: "I",
    organs: ["poumon", "vessie", "melanome"],
  },
  {
    keywords: ["egfr", "alk", "ros1", "biologie moleculaire", "panel moleculaire"],
    title: "Panel moleculaire (EGFR, ALK, ROS1...)",
    why: "Les alterations moleculaires conditionnent l'acces aux therapies ciblees. Obligatoire pour les ADK pulmonaires.",
    norm: "ESMO / INCa Recommandations therapies ciblees poumon",
    risk: "Therapies ciblees non envisageables. Perte de chance majeure.",
    severity: "warning",
    icon: "D",
    organs: ["poumon"],
  },
  {
    keywords: ["invasion pleurale", "plevre"],
    title: "Invasion pleurale",
    why: "Modifie le pT dans les cancers pulmonaires (pT2a minimum). Facteur pronostique independant.",
    norm: "AJCC/UICC TNM 8e edition Poumon / INCa",
    risk: "Sous-staging potentiel.",
    severity: "warning",
    icon: "Q",
    organs: ["poumon"],
  },

  // ═══════════════════════════════════════
  // PROSTATE
  // ═══════════════════════════════════════
  {
    keywords: ["gleason", "isup", "grade group", "score de gleason"],
    title: "Score de Gleason / Grade ISUP",
    why: "Systeme de gradation specifique a la prostate. Determine le pronostic et la strategie therapeutique.",
    norm: "OMS 2022 / ISUP 2019 / INCa Donnees minimales prostate",
    risk: "Gradation tumorale absente. Decision therapeutique impossible.",
    severity: "error",
    icon: "G",
    organs: ["prostate"],
  },

  // ═══════════════════════════════════════
  // CANAL ANAL
  // ═══════════════════════════════════════
  {
    keywords: ["p16", "statut p16"],
    title: "Statut p16",
    why: "Surrogat de l'infection HPV a haut risque. Obligatoire pour les HSIL/AIN3 du canal anal. Confirme le diagnostic de lesion HPV-induite.",
    norm: "OMS 2019 Classification digestive / CAP / INCa",
    risk: "Diagnostic de lesion HPV-induite non confirme.",
    severity: "error",
    icon: "P",
    organs: ["canal_anal"],
  },

  // ═══════════════════════════════════════
  // MELANOME
  // ═══════════════════════════════════════
  {
    keywords: ["breslow", "indice de breslow", "epaisseur"],
    title: "Indice de Breslow",
    why: "Mesure en mm de l'epaisseur du melanome. Premier critere du pT. Conditionne toute la prise en charge.",
    norm: "AJCC 8e edition Melanome / OMS 2022 / INCa",
    risk: "Staging impossible sans Breslow.",
    severity: "error",
    icon: "B",
    organs: ["melanome"],
  },
  {
    keywords: ["clark", "niveau de clark"],
    title: "Niveau de Clark",
    why: "Niveau d'invasion anatomique du melanome dans la peau.",
    norm: "AJCC 8e edition (complementaire au Breslow)",
    risk: "Information complementaire manquante.",
    severity: "warning",
    icon: "C",
    organs: ["melanome"],
  },
  {
    keywords: ["ulceration"],
    title: "Ulceration",
    why: "L'ulceration modifie le staging du melanome (augmente le pT). Facteur pronostique independant.",
    norm: "AJCC 8e edition Melanome / OMS 2022",
    risk: "Sous-staging potentiel.",
    severity: "error",
    icon: "U",
    organs: ["melanome"],
  },
  {
    keywords: ["index mitotique", "mitoses"],
    title: "Index mitotique",
    why: "Nombre de mitoses par mm2. Facteur pronostique dans le melanome.",
    norm: "AJCC 8e edition / OMS 2022",
    risk: "Facteur pronostique manquant.",
    severity: "warning",
    icon: "X",
    organs: ["melanome"],
  },

  // ═══════════════════════════════════════
  // THYROIDE
  // ═══════════════════════════════════════
  {
    keywords: ["extension extrathyroidienne", "extension extra"],
    title: "Extension extrathyroidienne",
    why: "Distinguer extension minime (pT3) vs massive (pT4). Conditionne le traitement complementaire.",
    norm: "AJCC 8e edition Thyroide / OMS 2022 / INCa",
    risk: "Staging imprecis.",
    severity: "warning",
    icon: "E",
    organs: ["thyroide"],
  },
];

/**
 * Organe-specific guidance messages.
 */
export const ORGAN_GUIDANCE: Record<string, { title: string; tips: string[] }> = {
  sein: {
    title: "Sein",
    tips: [
      "Statut RE, RP, HER2 et Ki-67 obligatoires (ASCO/CAP)",
      "Si HER2 score 2+, la FISH/CISH est requise",
      "Grade SBR modifie Nottingham avec detail des 3 composantes",
      "pTNM obligatoire sur piece operatoire (AJCC 8e ed.)",
    ],
  },
  colon_rectum: {
    title: "Colon-Rectum",
    tips: [
      "Minimum 12 ganglions examines pour un staging adequat",
      "Marge circonferentielle (CRM) obligatoire pour le rectum",
      "Statut MMR/MSI a rechercher systematiquement",
      "Tumour budding a evaluer (ITBCC 2024)",
    ],
  },
  poumon: {
    title: "Poumon",
    tips: [
      "Pattern predominant obligatoire pour les ADK (OMS 2021)",
      "PD-L1 (TPS) a evaluer pour l'immunotherapie",
      "Panel moleculaire minimum : EGFR, ALK, ROS1, KRAS, BRAF",
      "Invasion pleurale a rechercher (modifie le pT)",
    ],
  },
  prostate: {
    title: "Prostate",
    tips: [
      "Score de Gleason et Grade Group ISUP obligatoires",
      "Mentionner le pourcentage de chaque pattern",
      "Nombre de biopsies positives / total par sextant",
      "Longueur tumorale par carotte biopsique",
    ],
  },
  thyroide: {
    title: "Thyroide",
    tips: [
      "Classification OMS 2022 mise a jour (ex-NIFTP)",
      "Extension extrathyroidienne : minime vs massive",
      "pTNM specifique thyroide (AJCC 8e ed.)",
    ],
  },
  melanome: {
    title: "Melanome",
    tips: [
      "Indice de Breslow en mm (obligatoire)",
      "Niveau de Clark",
      "Ulceration et index mitotique (modifient le pT)",
      "Statut BRAF a rechercher si stade III/IV",
    ],
  },
  canal_anal: {
    title: "Canal anal",
    tips: [
      "Classification AIN/LSIL/HSIL selon OMS 2019",
      "Statut p16 obligatoire pour les HSIL",
      "Mentionner la presence de koilocytes (HPV)",
      "Recherche de composante infiltrante obligatoire",
    ],
  },
  non_determine: {
    title: "Organe non detecte",
    tips: [
      "Les sections obligatoires universelles seront verifiees",
      "L'organe sera detecte automatiquement a la prochaine iteration",
    ],
  },
};

/**
 * Find the best matching knowledge entry for a field name,
 * filtered by the detected organ for context-awareness.
 */
export function findFieldKnowledge(
  fieldName: string,
  organe: string = ""
): FieldKnowledge | null {
  const normalized = fieldName.toLowerCase();
  for (const entry of FIELD_KNOWLEDGE) {
    // Skip entries that don't match this organ
    if (entry.organs.length > 0 && organe && !entry.organs.includes(organe)) {
      continue;
    }
    for (const kw of entry.keywords) {
      if (normalized.includes(kw)) {
        return entry;
      }
    }
  }
  return null;
}
