# Journal d'audit & notes de reprise — MARC

_Audit technique complet réalisé le 2026-07-13 avant reprise par un développeur senior._

Ce document récapitule le nettoyage effectué, les **invariants à préserver**, les
**décisions délibérées** (ce qui a été gardé et pourquoi) et les **améliorations
restantes** (non bloquantes). Pour l'architecture et le lancement, voir
[ARCHITECTURE.md](ARCHITECTURE.md) et le README.

---

## 1. Nettoyage effectué (backend)

| Chantier | Détail | Effet |
|---|---|---|
| Code mort supprimé | `detection_manquantes` (~430 l : cluster `_est_*`/`_MOTS_CLES_*` doublonnant `specimen_type.champ_applicable`), `vocabulaire_acp` (1067→61 l : wordboost/corrections phonétiques/acronymes non branchés), fonctions mortes de `templates_organes`, 3 scripts cassés (`ingest_*`, `build_golden_fixtures` référençant un sous-système `retrieval`/`schemas` disparu), 1 binaire orphelin | ~2700 lignes retirées |
| Normalisation de texte | 8 ré-implémentations → **`text_utils`** unique (`strip_accents`/`normaliser`/`cle_alphanum`, base NFD + ligatures œ/æ) | Source unique, sémantique cohérente |
| Négation | 3 masquages + 3 listes de marqueurs → module **`negation`** (`mask_negations` + `NEGATION_MARKERS`) | Source unique |
| Bug contrat (M3) | `IterationResponse` jetait silencieusement `organes_detectes`/`coherence` (Pydantic) → hérite de `FormatResponse` ; `coherence` typée `CoherenceVerdict` (plus de `dict` nu) | Perte de données corrigée |
| Déploiement (B1) | migration Alembic en `UUID` natif ≠ ORM en `String(36)` → alignée + `env.py` lit `DATABASE_URL`. **Validé** : `alembic upgrade head` produit un schéma == `Base.metadata` | Chemin migré réparé |
| Config STT | `transcription.py` lit désormais `voxtral_model`/`stt_timeout_seconds`/`llm_max_retries` (au lieu de valeurs en dur) | Config effective |
| Abstraction (M5) | logique de panneau extraite de `main.py` → `reports/panel.py` ; endpoint mort `/completude` retiré | `main.py` 595→436 l |
| Lisibilité | `build_validated_report` (103 l) découpé en phases nommées ; scories (sets à doublons, regex `[A COMPLETER]` dupliquée, branche morte de cohérence) | — |

Tests backend : **128 passent** au moment de la remise (`cd backend && python -m pytest -q`
pour le compte exact — la suite évolue avec les ajouts de tests).

Validation métier (non-régression) : campagne held-out de 16 cas neufs (cytologie,
médical/greffon, tumoral, pièges) via le **vrai chemin de production** (`build_panel`) :
16/16 organe, **0 violation de sécurité** (aucun champ tumoral réclamé hors contexte).

---

## 2. Invariants à PRÉSERVER (sécurité — ne pas casser)

Ces propriétés sont testées et garantissent la fiabilité clinique. Toute évolution
doit les conserver :

1. **Codification jamais plus affirmative que la dictée.** `adicap.py`/`snomed.py`
   défèrent (`____`/`XX`, `confidence` basse) dès qu'il y a doute. Ne jamais
   « deviner » un grade/stade non dicté (voir `_lesion_grade_non_dicte`,
   `_check_tnm_derivation`). C'est de la codification déterministe, **pas** de
   l'interprétation médicale.
2. **Aucun champ tumoral sur lésion non tumorale.** `reports/guardrails.filter_alertes`
   + `specimen_type.detecter_diagnostic_context` retirent grade/pTNM/marges/MMR… sur
   contexte bénin/médical/pré-cancéreux. Les marqueurs moléculaires (MMR/MSI/KRAS…)
   sont réservés au **carcinome infiltrant**.
3. **Anti-hallucination + fidélité des chiffres.** Une mesure du CR absente de la
   dictée est signalée (`_check_numbers`) ; une taille dictée disparue du CR remonte
   au panneau (`_check_dropped_measurements`). Ne pas contourner ces gardes.
4. **Anti-faux-positif du panneau.** `filter_present_alertes` retire les champs déjà
   présents. Les systèmes de reporting (`reporting_systems`) ont leur propre contrôle
   de présence et sont ajoutés **après** ce filtre (sinon supprimés à tort).
5. **Détection 100 % automatique.** Aucun choix de template par l'utilisateur : les
   organes sont détectés (`reports/knowledge.detect_organs`), multi-organes géré.
6. **Abstraction moteur.** Tout passe par `reports.ReportEngine` : `LocalReportEngine`
   (Mistral aujourd'hui) est interchangeable avec `GilbertReportEngine` sans toucher
   au frontend. Ne pas court-circuiter cette couche.

---

## 3. Décisions délibérées (gardé sciemment)

- **Moteur `reports/gilbert_engine.py` (stub) et sa méthode `_map_summary_to_report`**
  sont conservés : c'est le **point d'extension** voulu (bascule Mistral→Gilbert),
  pas du code mort superseded. `generate`/`iterate` lèvent `GilbertCapabilityMissing`
  tant que l'API Gilbert n'expose pas le nécessaire (voir INTEGRATION_GILBERT.md).
- **Modèles ORM `Organization`, `ReportExport`, `BusinessRule`** (et colonnes
  multi-tenant `org_id`, `subscription_plan`…) sont conservés bien que non instanciés :
  ils matérialisent le schéma multi-tenant prévu. La migration 001 les crée. À
  **implémenter ou retirer** selon la feuille de route produit.
- **`calculer_score_completude`** est conservée (testée) bien que l'endpoint
  `/completude` ait été retiré : capacité prête à ré-exposer si besoin.
- **Harnais `tests/*_campaign.py`** conservés (valeur de test live Mistral) mais ce
  **ne sont pas** des tests pytest (pas de préfixe `test_`, appels réseau). À lancer
  manuellement. `functional_campaign.py` contient un chemin audio codé en dur à
  corriger avant usage.

---

## 4. Améliorations restantes recommandées (non bloquantes)

Priorisées, sans risque pour les invariants ci-dessus :

1. **Deux sources de vérité pour les vocabulaires de champs** :
   `specimen_type.CHAMPS_PIECE_ONLY`/`CHAMPS_INFILTRANT_ONLY` et
   `guardrails._PIECE_ONLY_FIELD_TERMS`/`_TUMORAL_FIELD_TERMS`/`_INVASIVE_FIELD_TERMS`
   se recouvrent. Non fusionnés ici car ils alimentent **deux mécanismes distincts**
   (gating de template par clé exacte vs filtrage du panneau par sous-chaîne) et les
   tests de sécurité sont critiques. À centraliser dans un référentiel unique consommé
   par les deux, **avec la batterie de sécurité en garde-fou**.
2. **Typage des retours de codification** : `suggerer_adicap` renvoie `dict[str, str]`
   (via `AdicapResult.as_dict()`) et `suggerer_snomed` `dict[str, str | dict]`. Le
   dataclass `AdicapResult` existe déjà : renvoyer les dataclasses et adapter les ~15
   sites d'appel (dont tests) donnerait un typage fort de bout en bout.
3. **Fonctions encore longues** : `suggerer_adicap` (~80 l) et `filter_alertes`
   (~80 l) gagneraient à extraire `_resolve_organe` et des prédicats de filtrage
   (une règle = une fonction).
4. **Couverture de tests** : `routes_auth`/`routes_admin`/`routes_reports` et
   `auth.py` (hash/JWT) n'ont pas de test — surface sécurité à couvrir en priorité.
5. **Qualité de `data/adicap_bible.json`** : 23 doublons exacts et ~55 paires
   `(organ_code, lesion_code)` ambiguës à dédupliquer (le test `test_adicap_bible_
   zero_wrong` couvre la justesse, pas l'unicité).
6. **Persistance / M4** : `PUT`/`DELETE /reports/{id}` (édition + effacement RGPD) et
   `/admin/corrections` ne sont pas appelés par le frontend actuel. À brancher côté UI
   ou documenter comme API admin/RGPD.
7. **Données volumineuses en `.py`** : `templates_organes.py` (~3000 l) pourrait
   externaliser ses données en `data/*.json` (comme `adicap_bible.json`), en gardant
   les dataclasses en Python.

---

## 5. Où regarder pour comprendre le cœur

- **Génération** : `reports/local_engine.py` → prompt `reports/prompts.py` → parsing +
  gardes `reports/guardrails.build_validated_report` → `GeneratedReport`.
- **Panneau « à compléter »** : `reports/panel.build_panel`.
- **Codification** : `adicap.suggerer_adicap`, `snomed.suggerer_snomed` (déterministes,
  sur `data/adicap_bible.json`).
- **Contexte diagnostique** : `specimen_type.py` (bénin/pré-cancéreux/infiltrant).
- **Normalisation / négation** : `text_utils.py`, `negation.py` (sources uniques).
