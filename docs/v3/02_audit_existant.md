# MARC v3 : audit de l'existant (PO-2)

Périmètre : dépôt `Demo_anapath`, branche `projet-v3`. Lecture du code, des specs et des docs ; exécution des tests existants. Aucun fichier modifié hors `docs/v3/`.

## 0. Résumé

**État de santé.** Backend : `pytest -q` donne **769 passed en 10 s**. Frontend : `tsc --noEmit -p tsconfig.app.json` ne remonte **aucune erreur**. Les campagnes live (`*_campaign.py`, qui appellent Voxtral et Mistral) n'ont pas été exécutées. Aucune mesure de latence réelle n'a donc été faite, et le backend n'en journalise pas.

**Verdict en cinq points.**

1. **Le socle de fidélité et d'explicabilité est solide et à garder.** Il comprend l'ancrage déterministe des citations dans la dictée, le collège de relecteurs avec vote et vérification de citation, le garde-chiffres, la négation, la complétude INCa, les règles de cohérence C1 à C16 et la codification ADICAP déterministe.
2. **Le contrat est le point faible.** Le compte rendu est une chaîne Markdown avec des marqueurs `[A COMPLETER: x]`. Le frontend la redécoupe par regex (`blocsTexte.ts`). Rien dans l'API ne porte un identifiant d'élément, une liste de sources ni une confiance. v3 a besoin d'un compte rendu **structuré en éléments**.
3. **Le pipeline est séquentiel et lent par construction.** Quatre étages se suivent : compréhension, rédaction, relecture, collège. Cela fait environ 10 appels LLM pour 20 assertions. La relecture et le collège pourraient tourner en parallèle, et la compréhension n'est qu'un « hint ». Il n'y a ni streaming ni trace d'étapes réelle. Les messages de progression du `Pipeline.tsx` sont des chaînes décoratives qui tournent sur un minuteur.
4. **Des données médicales sont stockées, contrairement à la cible v3.** Voir §3.2 : le texte de la dictée et le compte rendu sont conservés dans `reports` et dans `etude_dossiers`. Ils sont aussi exportables en CSV, avec les corrections avant/après en entier. L'audio, lui, n'est jamais écrit.
5. **Une grosse part du code est inutilisée.** Frontend : environ **4 600 lignes** inatteignables depuis `main.tsx`. Backend : `amont.py`, `interrogation.py` et `coherence_document.py` sont codés, et les deux premiers ne sont pas branchés. `coherence_document.py` est testé mais jamais appelé par le moteur.

## 1. Carte du pipeline actuel

### 1.1 Flux de bout en bout

```
audio (MediaRecorder / upload)
  └─ POST /transcribe ─▶ Voxtral (context_bias ~100 termes)  ──▶ texte brut (éditable à l'écran)
        └─ POST /format  {raw_text, rapport_precedent?}
              ├─ [det]  build_context_block : détection d'organes + pack INCa/IHC/classification
              ├─ [LLM 1] COMPRÉHENSION  → JSON {organes, type_prelevement, nature_lesion, entites, elements_dictes, resume}
              ├─ [LLM 2] RÉDACTION      → JSON {cr, organe, type_prelevement, alertes[]}   (une seule passe, un seul auteur)
              ├─ [det]  guardrails (build_validated_report) + comblement depuis la dictée
              ├─ [LLM 3] RELECTURE      → signalements[] (ne réécrit pas)
              ├─ [LLM 4..] COLLÈGE      → 2 lentilles × lots de 8 assertions + 1 « compléteur » (en parallèle entre eux)
              ├─ [det]  arbitrage par comptes de voix + vérification des citations
              └─ build_panel + coherence → FormatResponse
```

Moteurs sélectionnables par `REPORT_ENGINE` : `multipass` (défaut config et `render.yaml`), `local` (1 appel), `gilbert` (squelette). Le `docs/ARCHITECTURE.md` annonce encore `local` par défaut, ce qui est périmé.

### 1.2 Étapes, appels LLM et rôle

| # | Étage | Fichier | LLM ? | Ce qu'il fait | Explicable aujourd'hui ? |
|---|---|---|---|---|---|
| 0 | STT | `transcription.py`, `vocabulaire_acp.py` | Voxtral | Transcrit. `context_bias` limité à des mots simples, donc ~100 termes ACP. Aucune sortie n-best ni confiance. | Non. Le texte brut est rendu sans score. |
| 1 | Détection d'organes | `reports/knowledge.py` | Non | Mots-clés « spécifiques » (les termes génériques seuls ne comptent pas), max 4 organes, 23 templates. Injecte champs INCa, classification et panel IHC. | Oui, via `ContextResult.organes`, mais cette liste n'est pas exposée telle quelle. |
| 1b | Textes canoniques | `reports/canonical_texts.py` | Non | Cherche parmi 653 textes de référence du praticien (`data/textes_canoniques.json`) pour injecter le style maison. | Non exposé. |
| 2 | Compréhension | `prompts_multipass.py`, `multipass_engine._comprehend` | Oui | Extrait organes, nature de la lésion, entités et éléments dictés. Dégradation gracieuse : `{}` si échec. | **Oui** : renvoyé dans `trace.comprehension`. |
| 3 | Rédaction | `prompts_multipass.py`, `prompts.py` | Oui | Structure la dictée en CR. Corrections phonétiques **déléguées au prompt** (liste d'exemples en dur dans `prompts.py`). Sortie JSON `{cr, organe, type_prelevement, alertes}`. | Partielle : les `alertes` portent `declencheur`, `raison` et `options`. Le CR lui-même ne cite rien. |
| 4 | Guardrails | `reports/guardrails.py` (1 226 l.) | Non | Voir §1.3. | **Oui** (warnings texte). |
| 5 | Comblement | `reports/comblement.py` | Non | Si une étiquette (« PD-L1 ») apparaît une seule fois dans la dictée suivie d'une valeur, remplit le trou. Consigné dans `trace.comblements` avec la source. | **Oui**, c'est le meilleur exemple de trace du dépôt. |
| 6 | Relecture | `multipass_engine._review` | Oui | Signale fidélité, manque, incertitude, cohérence, sans réécrire. | `trace.signalements`. |
| 7 | Collège | `reports/college.py` | Oui (×2 lentilles × lots + 1) | « Littéraliste » (compare des mots, cite le passage exact), « sceptique » (cherche le pas de trop), « compléteur » (liste les manques). Température 0. | **Oui**, c'est le cœur de l'explicabilité. |
| 8 | Arbitrage | `etude/arbitrage.py` | Non | Compte les voix. **Vérifie chaque citation par recherche exacte dans la dictée** (sinon le vote bascule en non soutenu). Trois comportements : affirmer (silence), proposer, s'abstenir. | **Oui** : `voix_pour/voix_total`, `empan_*`, justifications recopiées telles quelles. |
| 9 | Panneau | `reports/panel.py`, `detection_manquantes.py`, `reporting_systems.py` | Non (fusion de sorties LLM) | Fusionne marqueurs `[A COMPLETER]`, champs INCa manquants, recommandations LLM et systèmes standardisés (Bethesda, Paris, Milan, Banff, MEST-C, SAF, ISHLT). Double filtre hors-contexte / déjà présent. | Partielle (`declencheur`, `raison`). |
| 10 | Cohérence | `reports/coherence.py` | Non | Structure (sections) et incohérences simples. **Appelée à chaque génération.** | Oui (`coherence.issues`). |
| 11 | Codification | `adicap.py`, `adicap_d1d2.py`, `adicap_ref.py`, `snomed.py` | Non | À la demande du client (`/adicap`, `/snomed`), pas dans `/format`. | ADICAP : `confidence` ∈ {haute, organe_seul, aucune} et `note`. SNOMED : rien. |

**Itération** (`/iterate`) : un LLM unique réécrit le CR entier. Un contrôle déterministe signale les termes et chiffres qui ont disparu (`contenu_perdu`). Cette itération **ne repasse pas par la compréhension, le collège ni la relecture**.

**Appels LLM par génération.** La formule est 3 + 2·⌈N/8⌉ + 1, où N est le nombre d'assertions jugeables. Pour 20 assertions, cela fait 10 appels. Le chemin critique compte 4 étages séquentiels :
- compréhension, puis rédaction (`max_tokens` à 16 384), puis relecture, puis collège ;
- la relecture et le collège sont indépendants (même CR en entrée) mais sont `await` l'un après l'autre.

### 1.3 Garde-fous déterministes (inventaire)

| Garde | Où | Ce qu'il détecte | Remarque |
|---|---|---|---|
| Parsing JSON robuste | `guardrails.parse_llm_json` | Fences, texte parasite, JSON tronqué (réparation) | Erreur : 502. |
| Garde-chiffres | `_check_numbers`, `numbers.py`, `chiffres_non_dictes` | Mesure du CR absente de la dictée (nombres parlés convertis en chiffres) | **Ne compare que la partie entière et ignore l'unité** : voir §5. |
| Mesures perdues | `_check_dropped_measurements` | Mesure dictée absente du CR | |
| Négations | `negation.py`, `_check_negation_flags` | Négation inversée ou perdue | Centralisé. |
| Sur-interprétation ganglionnaire | `_check_nodal_overinterpretation` | « N+ » non dicté | |
| Dérivation TNM | `_check_tnm_derivation` | pTNM non dicté | |
| Périmètre biopsie | `_check_biopsy_scope` | pTNM, marges et curage sur une biopsie | |
| Portée des classifications | `_check_classification_scope` | Classification hors organe | |
| Nettoyage de texte | `_clean_cr_text` | Marqueurs hors contexte, tableaux vides, méta-commentaires, sections vides | |
| Filtrage des alertes | `filter_alertes`, `filter_present_alertes` | Champ hors contexte, ou déjà présent | |
| Perte à l'itération | `contenu_perdu` | Termes cliniques ou chiffres disparus | |
| Cohérence structurelle | `coherence.py` | Sections manquantes, conclusion vide | |
| **Cohérence documentaire C1-C16** | `coherence_document.py` (1 152 l.) | Blocs, nombre de prélèvements, somme des ganglions, envahis > examinés, fragments, taille de conclusion vs macroscopie, **unités homogènes sur les axes d'une dimension (C7)**, trois axes, marges, lésion conclue décrite, marqueur conclu documenté, négations contredites, latéralité, organe, ganglions | **Testé (≈700 l. de tests), jamais appelé par le moteur** (voir §5). Zéro faux positif calibré sur les 653 textes canoniques. |
| Complétude INCa | `detection_manquantes.py`, `templates_organes.py` | Champs obligatoires manquants par organe, prélèvement et nature de lésion (`champ_applicable`) | Recall testé (`test_recall_obligatoires`). |

Il n'existe **aucun correcteur phonétique déterministe** : il se trouve uniquement dans le prompt (liste d'exemples) et dans le `context_bias` Voxtral.

## 2. Réutilisable tel quel pour un pipeline agentique explicable

### 2.1 À garder sans toucher

| Brique | Pourquoi |
|---|---|
| `etude/ancrage.py` | Empan calculé côté serveur par recouvrement de jetons, déterministe. Il ne demande jamais d'offsets au modèle. C'est la brique « source » de v3. |
| `etude/arbitrage.py`, `reports/college.py`, `reports/interrogation.py` | Vote, vérification de citation, trois comportements. Le modèle ne rédige pas, il vote. À adopter comme agent « vérificateur » (confiance = décompte de voix vérifiable). |
| `reports/numbers.py`, `negation.py`, `text_utils.py` | Briques pures, testées. |
| `reports/comblement.py` | Modèle de trace (champ, valeur, source). |
| `reports/coherence_document.py` | Cible v3 « vérificateurs d'incohérences ». Chaque règle rend un `AlerteDocument` avec `regle` et `Empan`, donc **code, message et source dans le CR**. À brancher. |
| `templates_organes.py` (23 organes), `specimen_type.py`, `detection_manquantes.py`, `reporting_systems.py` | Référentiel INCa. Cible v3 « champs obligatoires INCa manquants ». |
| `adicap*.py`, `snomed.py`, `organ_utils.py` | Codeur déterministe, qui s'abstient (`lesion "____"`) plutôt que de deviner. À étendre (voir §5). |
| `llm/` (base, mistral, anthropic, factory) | Abstraction propre : `LLMProvider`, `LLMRequest`, erreurs normalisées (`LLMTransientError`, `LLMTimeoutError`), `usage`. À étendre avec un horodatage par appel. |
| `reports/retry.py`, `config.py` | Retry, backoff, `college_actif` coupable : bon pour mesurer les régimes. |
| `ReportEngine` (Protocol) + `factory.py` | **Point d'extension naturel** : un `AgenticReportEngine` s'ajoute à côté de `multipass` sans toucher aux routes. Cela permet un parcours V1/V2 en parallèle. |
| `data/*.json` (ADICAP bible, `adicap_ref`, `codage_d1_d2`, textes canoniques) | Référentiels. |
| 769 tests | Filet de non-régression. Les tests des briques ci-dessus se réutilisent tels quels. |

### 2.2 Ce qui existe en germe et qu'il faut généraliser

| Ce que v3 demande | Ce qui existe | Écart |
|---|---|---|
| **Trace d'étapes** | `GeneratedReport.trace` = `{comprehension, signalements, college, passes[{role, model}], comblements}`. | `trace` est un `dict[str, object]` non typé. Il n'y a **ni durée, ni état, ni ordre, ni entrée/sortie par étape**. `passes` ne liste que le rôle et le modèle. Les étages déterministes (guardrails, panneau, cohérence) n'y figurent pas. |
| **Sources** | Chaque soumission du collège porte `empan_debut/fin/extrait` et `justifications` ; `DonneeManquante` porte `declencheur` (phrase dictée recopiée) ; `comblements` portent `source`. | La source existe seulement pour les assertions soumises au collège et pour les trous. Le CR affirmé (unanimité) n'a **pas** de source exposée au front. Les codes ADICAP/SNOMED n'ont pas de source (`extraire_codes` ancre côté étude uniquement). |
| **Degré de confiance** | `voix_pour/voix_total` (collège), `ADICAP.confidence` (3 niveaux), `PropositionAffichee.confiance` (float, alimenté par les codes, voir `extraction.py:552`). | Pas de **modèle de confiance unifié**. Les valeurs sont hétérogènes : décompte de voix, énumération, float. Le STT n'en fournit aucune. Le choix éditorial du projet est de préférer le décompte vérifiable à un nombre (« un 0,73 ne se contrôle pas »). À garder comme principe et à normaliser en niveaux (`haute / moyenne / basse` + décompte). |
| **Orchestrateur** | `MultiPassReportEngine.generate` : un script séquentiel. | Pas d'orchestrateur : pas de plan, pas de saut conditionnel, pas de parallélisme. |
| **Correcteur phonétique STT** | `context_bias` plus liste d'exemples dans le prompt. | À créer en agent explicite, **avec journal des corrections** (avant/après/source). |
| **Vérificateur d'unités mm/cm** | C7 (axes d'une même dimension), `_MEASURE_RE`. | Insuffisant : voir §5. |
| **Codeur ADICAP + SNOMED** | Existe, sur demande du client, sur le CR final. | SNOMED : **25 topographies et 19 morphologies seulement**, par mots-clés, sans confiance. À rendre sourçable. |
| **Texte à trous si manque** | `[A COMPLETER: champ]` + `TrouInline` + `options` fermées. | Fonctionne, mais fondé sur une syntaxe de texte (voir §4). |
| **Budget de questions** | `amont.py`, avec `BUDGET_QUESTIONS = 3` et la politique « seule l'incertitude qui change la sortie compte ». | **Non branché** (§5). |

## 3. Modèles de données et télémétrie

### 3.1 Tables

**Applicatif (`db_models.py`)** : `organizations`, `users`, `reports`, `report_exports`, `audit_log`, `business_rules`.

| Table | Colonnes notables |
|---|---|
| `users` | email, `password_hash` (bcrypt), name, `role` (`user` / `admin`), `organization_id`, `is_active`, `last_login`. |
| `reports` | `raw_transcription` (Text, NOT NULL), `structured_report` (Text, NOT NULL), `organe_detecte`, `status` (`draft`), **`completeness_warnings`** (Text, détourné pour stocker un JSON `{feedback, corrections[]}`). |
| `audit_log` | `user_id`, `action`, `details`, `ip_address` (jamais renseignée), `created_at`. Actions : `report_created`, `report_updated`, `feedback_added`, `report_deleted`. |
| `report_exports`, `business_rules` | Déclarées. Aucune route ne les alimente (`report_exports` jamais écrite, `business_rules` jamais lue). |

**Étude (`etude/models.py`, 9 tables)** : `etude_sessions`, `etude_dossiers`, `etude_prelevements`, `etude_propositions`, `etude_questions`, `etude_pauses`, `etude_ergonomie`, `etude_reponses_questionnaire`, `etude_revisions_decision`.

- **`etude_dossiers`** porte les horodatages t0 à t6 (dictée, affichage, décisions, clôture, export), `nb_prelevements_*`, abandon et exclusion (avec motif), `caracteres_modifies`, `organe`, `nb_blocs_non_vus`, et les textes décrits en §3.2.
- **`etude_propositions`** est l'unité d'analyse : `type` (restitution / code / completude), `valeur_proposee`, `empan_*`, `confiance`, `regles_evaluees`, `chiffres_non_dictes`, `affiche_a`, `vu_a`, `decide_a`, `latence_ms`, `hative`, `etat`, `decision`, `valeur_retenue`, `nature_correction`, `cause_erreur`.

**Base locale (`lexia.db`)** : vide, 0 rapport, 0 utilisateur, aucune table `etude_*`. Il n'y a donc **pas de données réelles à auditer**. La production visée est Render. Elle tombe sur un SQLite éphémère sans `DATABASE_URL` Postgres (`/health.base_persistante` le signale).

### 3.2 Données médicales stockées : constat précis (à lire)

L'audio **n'est jamais persisté** : `/transcribe` lit les octets en mémoire et les transmet à Voxtral. Je n'ai trouvé aucune écriture disque. En revanche **le texte médical est stocké, en clair, à quatre endroits**.

| # | Où | Quoi | Qui y accède |
|---|---|---|---|
| 1 | `reports.raw_transcription`, `reports.structured_report` (`POST /reports`) | Dictée et CR complets. Le docstring de la table dit « contenu anonyme », **mais aucune anonymisation n'est appliquée**. Si le praticien dicte un nom, une date de naissance ou un numéro de dossier, ils sont conservés tels quels. | Le praticien (`GET /reports`, `GET /reports/{id}`), l'admin (extraits). |
| 2 | `reports.completeness_warnings` → `corrections[]` | **À chaque `PUT /reports/{id}`, copie intégrale « avant » et « après » du CR**, accumulée sans limite. | `GET /reports/{id}`, `GET /admin/corrections` (extraits de 200 caractères), `GET /admin/reports`. |
| 3 | `etude_dossiers.transcription`, `cr_propose`, `cr_valide`, plus `etude_propositions.valeur_proposee` / `valeur_retenue` | Dictée et CR en entier, plus chaque phrase proposée et retenue. | **`GET /admin/etude/dossiers/{id}`** (texte complet) et **export CSV et XLSX** (`/admin/etude/export`, `/export.xlsx` : colonnes `transcription`, `cr_propose`, `cr_valide`, `valeur_*`). |
| 4 | Texte libre : `reports` (commentaire de feedback), `etude_dossiers.omission_texte` et `commentaire_validation`, `etude_reponses_questionnaire.valeur` | Texte libre, qui peut contenir du contenu clinique. | Admin. |

Côté navigateur, `lib/drafts.ts` conserve dans `localStorage` le CR, la dictée et l'explication pendant 24 h. Le jeton JWT y est aussi stocké.

**Ce qui est bien fait** : la suppression d'un CR supprime son dossier d'étude (RGPD, `DELETE /reports/{id}`) ; l'export pseudonymise le praticien ; l'ergonomie ne mesure aucun contenu saisi ; aucun traceur tiers.

**Conclusion pour la cible v3** (« aucune donnée médicale ni audio stocké ; seulement des retours d'usage »). Elle n'est atteinte ni par le modèle de données ni par les routes admin. Il faut :
- **supprimer** `reports.raw_transcription/structured_report`, le journal `corrections` et les colonnes de texte d'`etude_dossiers` / `etude_propositions`, ou en faire un mode explicitement distinct et désactivable (études cliniques) ;
- remplacer par des **compteurs** : feedback +/-, nombre de retouches (déjà calculable : `caracteres_modifies`, `nature_correction`), temps (t0 à t5 déjà là) ;
- ne pas écrire de texte libre sans mise en garde, ou le retirer.

### 3.3 Ce que la télémétrie admin collecte déjà (et ce qui est réutilisable)

**Déjà aligné sur la cible v3 (sans texte) :**
- feedback étoiles 1 à 5 (à ramener à +/-) ;
- nombre de corrections par CR (`correction_count`) ;
- temps : t0 à t6 et `latence_ms`, `latence_vue_ms`, pauses neutralisées, `hative` ;
- décisions par proposition (grilles fermées) et taux (conforme, corrigé, non dicté, hors sujet) avec numérateur et dénominateur ;
- ergonomie : visible_ms, clics, profondeur, ordre de visite, par zone ;
- F-SUS, questionnaires par cas ;
- exclusion plutôt que suppression, abandon motivé.

**Mais** : cette instrumentation est **celle d'une étude clinique** (protocole, F-SUS, verrou d'export, terciles d'apprentissage). Elle est lourde (≈ 6 700 lignes dans `etude/` et ≈ 1 500 dans les routes, sans compter les composants admin). La cible v3 n'en demande qu'une fraction. `docs/AUDIT_FAUX_SIGNAUX.md` (23/08, à 622 tests) listait des taux faux. Je ne l'ai pas rejoué ; la suite est passée de 622 à 769 tests et plusieurs commits récents (`etude:`, `admin:`) corrigent des points. **L'item 3.11 (« le collège n'est jamais transmis à l'extraction ») reste ouvert** : la route `POST /etude/dossiers` appelle `extraire(...)` sans `college=`.

**Admin** : `GET /admin/stats` (totaux, note moyenne, par organe), `/admin/reports` (200 derniers, avec email du praticien), `/admin/corrections`, `/admin/audit` (500 dernières lignes). La note moyenne et le comptage chargent **tous** les `completeness_warnings` en mémoire.

## 4. Carte de l'UI

### 4.1 Structure (Vite + React 19 + Tailwind 3 + lucide, shadcn minimal)

- **Navigation par état**, sans router : `Page = app | history | admin`, `AppView = record | report`.
- **`App.tsx` = 1 419 lignes** : concentre session, dictée, génération, brouillon, panneaux, étude, complétude, validation. C'est le principal nœud de dette frontend.
- Deux modes d'affichage coexistent : **mode travail** (`CompteRenduTravail` + `PanneauExplicabilite`, le plus récent) et **mode édition** (`ReportPanel` 1 123 l. + `ExplainPanel` + `CompletionPanel`, historique).
- Thème « charte Gilbert/Lexia » : tokens HSL en CSS vars, `iris` remappé sur #1E43E5, `vert` #0A7C5A pour les statuts, mode sombre, polices Inter / Bricolage Grotesque. `tailwind.config.js` déclare aussi `serif: Instrument Serif` et `hand: Caveat` (aucun usage trouvé dans les `.tsx`), `marc-aurora` (fond animé), keyframes `float` / `breathe` / `pulse-brain`.

### 4.2 Composants : reprendre, refondre, supprimer

| Zone | Composants | Verdict | Pourquoi |
|---|---|---|---|
| **Fondations** | `ui/button`, `badge`, `textarea`, `Confirmation`, `Toast`, `ErrorBoundary`, `toast-context` | **Reprendre** | Propres et petits. À étendre en design system (Harvey : très peu d'ornements, typographie, espaces). |
| **Services et hooks** | `services/api.ts`, `useAuth`, `useAudioRecorder`, `lib/config`, `lib/utils` | **Reprendre** | Types déjà miroir du backend. À faire évoluer vers le contrat v3. |
| **Surface de travail** | `travail/CompteRenduTravail`, `BlocTexte`, `TrouInline`, `MarkdownEnLigne` | **Reprendre l'idée, refondre l'implémentation** | Excellente UX : décider sur la phrase, combler le trou en place, jamais d'aller-retour. Mais construite sur `lib/blocsTexte.ts` (395 l.), qui **redécoupe du Markdown par regex** (`ENTETE`, `MARQUEUR_TROU`). v3 doit afficher des **éléments structurés** (id, texte, sources, confiance, statut) venus de l'API. |
| **Explicabilité** | `travail/PanneauExplicabilite` (405 l.) | **Reprendre le principe, refondre** | Principe à conserver : « le pourquoi, jamais la mécanique » ; citations jamais reformulées ; panneau purement consultatif. À réaligner sur la trace d'étapes v3 (timeline) plutôt que sur `trace.college.soumissions`. |
| **Dictée** | `RecorderPanel` (395), `analyse/QuaiDictee`, `BarreAjout`, `Glissiere`, `useDicteeAppoint` | **Refondre** | `RecorderPanel` mêle enregistrement, upload, transcription, génération, itération. `QuaiDictee` (micro fixe) est une bonne idée, mais n'est pas monté. |
| **Progression** | `Pipeline.tsx` (290) | **Remplacer** | Messages décoratifs sur minuteur (« Chargement du template INCa… »), sans lien avec l'exécution réelle. À remplacer par le **flux d'étapes réelles** (SSE). |
| **Complétude** | `CompletionPanel` (378), `lib/completion.ts`, `data/field-knowledge.ts` (722), `CodificationPanel` (238) | **Refondre** | Logique de complétude côté client dupliquant le serveur ; `field-knowledge.ts` est un second référentiel qui peut diverger de `templates_organes.py`. |
| **Mode édition historique** | `ReportPanel` (1 123), `ExplainPanel` (212) | **Supprimer à terme** | Coexiste avec le mode travail. |
| **Historique et connexion** | `HistoryPage`, `LoginPage` | **Refondre** | L'historique **suppose que le CR est stocké** (incompatible v3 sans stockage) ; à repenser. |
| **Admin et étude** | `AdminPage` (880), `admin/VueDossier` (1 288), `VuePraticiens` (1 045), `etude-admin/SyntheseEtude` (503), `ListeDossiersEtude`, hooks `useHorlogeEtude`, `useMesureErgonomie`, `useEtudeDossier` | **Réduire fortement** | Instrumentation d'étude clinique, très au-delà des retours d'usage de la cible v3. À remplacer par un tableau de bord minimal (+/-, retouches, temps). |
| **Mort (inatteignable depuis `main.tsx`)** | `analyse/PanneauAnalyse`, `PointCarte`, `QuaiDictee` ; `parcours/BarreEtat`, `BoutonValider`, `DialogueValidation` ; `revue/*` (`RevuePanel`, `PanneauLateralRevue`, `PropositionCarte`, `PileDecidees`, `VerbatimPanel`, `BoutonAbandon`) ; `etude-admin/DetailDossierEtude` ; `questionnaire/QuestionnaireParCas` | **Archiver** | **≈ 4 600 lignes**. Calcul par fermeture des imports depuis `main.tsx`. `BoutonValider` et `BarreEtat` documentent un parcours de validation non monté. |

### 4.3 Écarts avec un design épuré type Harvey

- **Densité visuelle** : sidebar, barre mobile, animations d'ambiance (`aurora`, `float`, `breathe`), badges de couleur nombreux, textes de 10 à 13 px en dur (`text-[..px]`). Harvey fait l'inverse : une colonne de lecture, une typographie dominante, des états rares et discrets.
- **Tokens** : l'échelle `iris` et `gilbert` double le primaire. Il faut un jeu de tokens unique, une échelle typographique et un jeu de composants (carte, ligne de source, pastille de confiance, timeline d'étapes).
- **Contenu** : le jargon du protocole d'étude (« proposition », « hâtive », « non vu ») ne doit pas fuiter dans l'UI praticien.
- **Accessibilité** : non auditée. Les marqueurs de trou sont des éléments cliquables dans du texte ; à vérifier au clavier.

## 5. Dette et risques

### 5.1 Risques produit et conformité

| # | Risque | Gravité | Détail |
|---|---|---|---|
| R1 | **Stockage de texte médical** | Élevée | Voir §3.2. Contredit la cible v3 et le discours « souverain ». Le commentaire « contenu anonyme » est trompeur. |
| R2 | **Aucune mesure de latence** | Élevée | La cible « 10× plus rapide » n'est pas vérifiable. Pas de chrono par étape, ni côté serveur ni côté client. |
| R3 | **Pipeline séquentiel, ≈ 10 appels** | Élevée | Voir §1.2. La relecture et le collège sont parallélisables (même CR en entrée). La compréhension pourrait précéder, ou être remplacée par l'extracteur. Pas de streaming : l'utilisateur attend l'ensemble. |
| R4 | **Vérification mm/cm absente du garde-chiffres** | Moyenne à élevée | `_check_numbers` compare la **partie entière** du chiffre à l'ensemble des chiffres dictés, **sans l'unité**. « 5 mm » dicté et « 5 cm » écrit passent. C7 ne vérifie que l'homogénéité des axes d'une dimension. Un vrai vérificateur d'unités reste à écrire. |
| R5 | **Pas de correcteur STT déterministe** | Moyenne | Les erreurs sont corrigées uniquement par le prompt, sans journal. Impossible de dire « j'ai corrigé X en Y parce que ». |
| R6 | **`coherence_document.py` non branché** | Moyenne | 16 règles zéro faux positif existent et ne servent à rien. À brancher en priorité (gain immédiat en vérificateurs). |
| R7 | **Codification limitée** | Moyenne | SNOMED : 25 topographies, 19 morphologies, mots-clés, sans confiance ni source. ADICAP s'abstient correctement mais ne cite aucune source. |
| R8 | **Confiance hétérogène** | Moyenne | Voir §2.2. |

### 5.2 Dette technique

| # | Dette | Détail |
|---|---|---|
| D1 | **Code mort backend** | `reports/amont.py` (320 l., collège amont : lectures, contestations, doutes, budget de 3 questions) et `reports/interrogation.py` : **jamais importés** par le moteur ni par les routes. `coherence_document.py` : testé, jamais appelé. `gilbert_engine.py` : squelette (`generate()` lève `GilbertCapabilityMissing`). `report_exports` et `business_rules` : tables sans route. |
| D2 | **Code mort frontend** | ≈ 4 600 lignes (§4.2). |
| D3 | **Contrat par chaîne Markdown** | `[A COMPLETER: x]`, `**__TITRE__**`, regex `ENTETE` dans `blocsTexte.ts`, `strip_*` dans `guardrails.py`. Toute évolution du style de sortie casse le front. |
| D4 | **`trace` non typé** | `dict[str, object]`, miroir manuel dans `api.ts`. Aucun schéma partagé. |
| D5 | **Colonne détournée** | `reports.completeness_warnings` stocke du JSON (feedback, corrections). Pas de requête SQL possible ; l'agrégat admin charge tout en mémoire. |
| D6 | **Migrations doubles** | `alembic/versions` ne contient que `001_initial_schema.py`, sans tables `etude_*`. Le schéma réel est maintenu au démarrage par `create_all` + `_reconcilier` (ajout de colonnes à chaud). Deux sources de vérité. |
| D7 | **Auth minimale** | Inscription ouverte (`/auth/register`, rôle `user`, sans vérification d'email ni organisation). JWT en `localStorage`. `get_current_user` exige la base : **toute génération dépend de la BDD**. `JWT_SECRET` par défaut accepté hors Postgres. |
| D8 | **Dépendance forte de `/format` à la BDD** | Le moteur n'en a pas besoin. À découpler pour un mode sans compte ou un mode démo. |
| D9 | **Doc périmée** | `ARCHITECTURE.md` : défaut `REPORT_ENGINE=local` (en réalité `multipass`), « ~128 tests » (en réalité 769), collège absent. |
| D10 | **Argument mort** | `DonneeManquante(..., obligatoire=False)` dans `_check_numbers` : le modèle n'a plus ce champ, pydantic l'ignore. |
| D11 | **Couplage prompt / parseur** | Les règles de style vivent dans de très longs prompts (`prompts.py` 348 l., `prompts_multipass.py` 264 l.) avec exemples en dur par organe. Pas de tests de prompts hors campagnes live. |
| D12 | **Harnais live à chemins en dur** | `tests/*_campaign.py` : certains contiennent des chemins hors dépôt. |
| D13 | **Taille des fichiers** | `templates_organes.py` 2 969 l., `etude/analyse.py` 1 694 l., `coherence_document.py` 1 152 l., `VueDossier.tsx` 1 288 l., `App.tsx` 1 419 l. |
| D14 | **Faux signaux d'étude** | `AUDIT_FAUX_SIGNAUX.md` (970 l.) : à rejouer avant toute réutilisation des taux. |
| D15 | **Fonts inutiles** | Instrument Serif et Caveat embarquées sans usage (poids du bundle) ; la charte Gilbert proscrit Instrument Serif. |

## 6. Contrat d'API actuel

Auth : `Authorization: Bearer <access_token>` (HTTPBearer). Erreurs : JSON `{detail}`. Codes usuels : 400, 401, 403, 404, 413, 422, 429 (rate limit), 502, 503, 504.
Limites : `/transcribe` 30/min, `/format` 20/min, `/iterate` 20/min, `/auth/register` 5/min.

### 6.1 Cœur (`main.py`)

| Méthode et chemin | Entrée | Sortie |
|---|---|---|
| `GET /health` | | `{status, base_configuree, base_persistante, moteur}` |
| `POST /transcribe` | `multipart file` (audio ou vidéo ; extensions webm, mp3, mp4, m4a, mov, wav, ogg, flac, aac ; max 200 Mo) | `{raw_transcription}` |
| `POST /format` | `{raw_text, rapport_precedent?}` | `FormatResponse` (ci-dessous) |
| `POST /iterate` | `{rapport_actuel, nouveau_transcript}` | `IterationResponse` (même contrat que `FormatResponse`) |
| `POST /sections` | `{formatted_report}` | `{sections: {nom: texte}}` |
| `POST /adicap` | `{formatted_report, organe_detecte}` | `{code, prelevement, prelevement_code, technique, technique_code, organe, organe_code, lesion, lesion_code, confidence, note}` |
| `POST /snomed` | idem | `{topography: {code, display, system}, morphology: {...}}` |
| `POST /export` | `{formatted_report, title?}` | `.docx` en flux |

**`FormatResponse`**

```
formatted_report: str                    # Markdown, avec marqueurs [A COMPLETER: champ]
organe_detecte: str
donnees_manquantes: [{champ, description, section,
                      declencheur?, raison?, options[]}]
warnings: [str]                          # texte libre (garde-fous + relecture)
organes_detectes: [str]
type_prelevement: str
coherence: {ok, structure_complete, sections_presentes[], issues[{code, message, severity}]}
trace: {                                 # dict libre, vide si moteur "local"
  comprehension?: {organes, type_prelevement, nature_lesion, entites, elements_dictes, resume},
  signalements?:  [{categorie, gravite?, message}],
  comblements?:   [{champ, valeur, source}],
  college?: null | {quorum, lentilles_muettes[], taux_de_soumission,
                    soumissions[{rang, section, assertion, comportement, motif,
                                 voix_pour, voix_total, empan_debut, empan_fin,
                                 empan_extrait, justifications[]}],
                    manques[{champ, justification}]},
  passes: [{role, model}]
}
```

Absent du contrat : identifiant d'élément, sources par phrase, confiance unifiée, durées, état des étapes, texte structuré par éléments.

### 6.2 Comptes-rendus (`/reports`, `routes_reports.py`)

| Méthode et chemin | Entrée | Sortie |
|---|---|---|
| `POST /reports` | `{raw_transcription, structured_report, organe_detecte, completeness_warnings}` | `{id, status}` |
| `GET /reports` | | `[{id, organe_detecte, status, created_at, updated_at, excerpt, has_feedback, rating}]` (100 max) |
| `GET /reports/{id}` | | détail complet avec `raw_transcription`, `structured_report`, `corrections[{timestamp, before, after}]` |
| `PUT /reports/{id}` | `{structured_report}` | `{status}` (stocke le diff avant/après) |
| `POST /reports/{id}/feedback` | `{rating 1..5, comment}` | `{status}` |
| `DELETE /reports/{id}` | | `{status}` (supprime aussi le dossier d'étude) |

### 6.3 Auth (`/auth`)

`POST /register` `{email, password, name}` ; `POST /login` `{email, password}` ; `POST /refresh` `{refresh_token}` : renvoient `{access_token, refresh_token, token_type}`. `GET /me` renvoie `{id, email, name, role}`. Access JWT 480 min, refresh 7 jours (HS256).

### 6.4 Administration (admin uniquement : `get_admin_user`)

`GET /admin/reports`, `/admin/stats`, `/admin/corrections`, `/admin/audit`.

### 6.5 Étude (praticien)

| Chemin | Rôle |
|---|---|
| `POST /etude/sessions` ; `POST /etude/sessions/{id}/cloture` | Session de travail |
| `POST /etude/dossiers` | Ouvre un dossier `{session_id, transcription, cr_propose, organe, t0, t1, codes[], alertes[], prelevements[]}`, **extrait et fige les propositions**, renvoie `{dossier_id, propositions[], sous_extraction}` |
| `POST /etude/propositions/{id}/vue` ; `POST /etude/dossiers/{id}/vues` | Premier affichage d'un bloc (idempotent) |
| `POST /etude/propositions/{id}/decision` | `{decision, valeur_retenue, nature_correction, cause_erreur, justif_ouverte, justif_duree_ms}` |
| `POST /etude/dossiers/{id}/pauses`, `/cloture`, `/export`, `/abandon`, `/exclusion` ; `DELETE /etude/dossiers/{id}` | Cycle de vie du dossier. `cloture` envoie `cr_valide`, `omission_*`, `commentaire_validation`, `rapport_id`. |
| `GET /etude/questionnaires/{nom}` ; `POST /etude/questionnaires` | Inclusion, par cas, fin d'étude (F-SUS : 409 tant que les libellés publiés ne sont pas en place) |
| `POST /etude/dossiers/{id}/ergonomie` | Lot d'instantanés par zone |

### 6.6 Étude (admin)

`GET /admin/etude/synthese`, `/dossiers`, `/dossiers/{id}` (texte complet), `POST .../exclusion`, `DELETE .../dossiers/{id}`, `GET /admin/etude/ergonomie`, `GET /admin/etude/export` (CSV), `GET /admin/etude/export.xlsx`.

## 7. Recommandations pour la décision (garder / refondre)

**Garder tel quel** : ancrage, collège et arbitrage, garde-chiffres, négation, comblement, templates INCa, ADICAP, `llm/`, `ReportEngine` et sa factory, 769 tests.

**Brancher ce qui est déjà écrit** : `coherence_document.py` (vérificateur d'incohérences) et la logique de questions de `amont.py`, avec son budget de 3.

**Refondre**
1. Le **contrat de sortie** : éléments structurés `{id, texte, section, sources[empan], confiance, statut}` et trace typée, avec durée et état par étape.
2. L'**orchestrateur** : étapes parallélisées, événements en flux (SSE) pour afficher les vraies étapes.
3. Le **modèle de données** : aucune donnée médicale persistée ; télémétrie réduite aux retours d'usage.
4. Le **frontend** : `App.tsx` à décomposer, `blocsTexte.ts` à supprimer, design system épuré, archivage des ~4 600 lignes mortes.

**À créer** : correcteur phonétique avec journal, vérificateur d'unités mm/cm (R4), enrichissement SNOMED, mesure de latence de bout en bout (préalable à toute promesse « 10× »).

**Décisions à prendre avec le propriétaire**
- Conserve-t-on un mode « étude clinique » séparé (stockage de texte sous consentement), ou le supprime-t-on ?
- Un historique de comptes rendus est-il nécessaire en v3 ? Sans stockage, il n'y en a pas côté serveur.
- Les comptes restent-ils ouverts à l'inscription ?
