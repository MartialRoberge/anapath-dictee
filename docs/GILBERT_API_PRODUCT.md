# Rendre l'API Gilbert « template-native » : du meeting-intelligence à la plateforme dictée → document structuré

**Objet.** Ce document explique, en mode produit, comment faire évoluer l'API Gilbert pour qu'une application verticale (MARC pour l'anapath, mais aussi juridique, industrie, etc.) puisse être construite **en ne changeant que le frontend**, tout le moteur restant côté Gilbert. Il répond à trois questions : *(1) qu'est-ce qui manque aujourd'hui ? (2) la génération par template est-elle bonne, et quel contexte faut-il en plus ? (3) quelle roadmap par sprints pour y arriver ?*

MARC (le POC anapath) sert de **implémentation de référence** : tout ce qu'il fait aujourd'hui côté serveur applicatif (connaissances métier par organe, guardrails, codification) est ce qu'il faut absorber dans l'API Gilbert pour le rendre réutilisable par toutes les verticales.

> **Ce document est la vue produit / roadmap.** Pour la **checklist technique
> d'intégration** (état réel de `backend/reports/gilbert_engine.py`, étapes de
> bascule, points d'injection), voir **[`INTEGRATION_GILBERT.md`](INTEGRATION_GILBERT.md)**.
> Pour la **trajectoire souveraineté/HDS**, voir
> **[`NOTE_TECHNO_SOUVERAINETE.md`](NOTE_TECHNO_SOUVERAINETE.md)**.

---

## 1. Le constat : Gilbert est une API de *consommation*, pas encore de *composition*

État de l'API v1.1.0 (audit OpenAPI) — ce que Gilbert fait très bien :

| Capacité | Endpoint | Verdict |
|---|---|---|
| Upload audio | `POST /meetings/upload` (file + title) | ✅ |
| Transcription (STT) | `GET /meetings/{id}/transcript` (polling) / webhook `meeting.transcribed` | ✅ solide, 98 %+ |
| Synthèse | `GET /meetings/{id}/summary` (markdown) | ✅ mais figée |
| Recherche, dossiers, partage | `/search`, `/folders`, `/shared` | ✅ |
| Webhooks, MCP | `/webhooks`, `gilbert-mcp` | ✅ |
| Dictionnaire (100 termes) | dans l'app | ⚠️ pas d'API |

Le problème pour un cas d'usage type MARC : **le pipeline est une boîte noire à sortie unique**. On téléverse de l'audio, on récupère un markdown de synthèse — dont on ne contrôle **ni la structure, ni le prompt, ni le vocabulaire, ni la validation, ni le format de sortie** par API. Or une app verticale a besoin exactement de ça : imposer sa structure métier, son vocabulaire, ses règles de fiabilité, et récupérer des **données structurées** (pas du texte libre) pour piloter son frontend.

**Conclusion produit :** Gilbert est aujourd'hui une **API de consommation** (je lis ce que le pipeline a produit). Pour supporter des verticales « frontend-only », il faut la faire passer à une **API de composition** (je déclare *comment* le document doit être produit, et je récupère du structuré).

---

## 2. La brique manquante : le **Template** comme objet de première classe

C'est le cœur de la réponse à ta question « est-ce qu'il faut du contexte en plus sur la génération des templates ? ». Aujourd'hui un « template » Gilbert = une mise en page de synthèse choisie dans l'app. C'est trop pauvre pour une verticale. Un template doit devenir un **objet API riche** qui porte *tout* le contexte de génération :

```jsonc
// POST /templates  — un template = tout ce qui cadre la génération
{
  "id": "acp-anapath-cr",
  "name": "Compte-rendu anatomopathologique",
  "vertical": "medical",
  "locale": "fr-FR",

  // (1) STRUCTURE de sortie : schéma des zones à remplir (slot-filling)
  "schema": {
    "sections": [
      { "key": "titre",       "type": "string", "required": true },
      { "key": "macroscopie", "type": "text" },
      { "key": "microscopie", "type": "text", "min_before_diagnosis": true },
      { "key": "ihc",         "type": "table", "columns": ["anticorps", "resultat"] },
      { "key": "conclusion",  "type": "text", "required": true }
    ]
  },

  // (2) INSTRUCTIONS de génération (le "prompt métier", versionné)
  "instructions": "Tu es anatomopathologiste... [règles de fidélité, structure]",

  // (3) VOCABULAIRE métier (biais STT + corrections), par API et non plus dans l'app
  "vocabulary": {
    "boost": ["TTF1", "Gleason", "Breslow", "FNCLCC", "Barrett"],
    "corrections": [{ "from": "brè slo", "to": "Breslow" }]
  },

  // (4) GARDE-FOUS de fiabilité (validation post-génération, refus/flag)
  "guardrails": {
    "no_invented_numbers": true,       // aucune mesure absente de la dictée
    "no_derived_staging": true,        // ne jamais déduire un stade non dicté
    "field_scope": "by_context",       // pas de champ hors organe/contexte
    "negation_safety": true
  },

  // (5) ENRICHISSEMENTS (plugins de post-traitement : codification, extraction)
  "enrichments": ["adicap", "snomed"],

  // (6) paramètres modèle
  "model": { "name": "lexia-large", "temperature": 0.0 }
}
```

Avec cet objet, **une verticale = un template + un frontend**. Le juridique déclare un template « conclusions d'audience » (sections : parties, faits, moyens, dispositif ; vocabulaire juridique ; garde-fou « ne jamais inventer d'article de loi »). L'industrie déclare « rapport d'intervention » (sections : équipement, symptôme, action, pièces ; vocabulaire technique). **Le moteur ne change pas, seul le template change** — et le frontend consomme le JSON structuré.

### La génération par template est-elle « bonne » ? Ce qu'on a appris avec MARC

Oui, **à condition de fournir les 6 blocs ci-dessus**. Un template réduit à une mise en page (ce que Gilbert offre aujourd'hui) produit des sorties instables. Les enseignements concrets du POC MARC, transposables tels quels :

- **Il faut la STRUCTURE + les INSTRUCTIONS, pas juste la mise en page.** Le LLM doit savoir *quoi* remplir et *avec quelles règles*. Sans ça, il invente.
- **Il faut les GARDE-FOUS.** Sur du médical, le LLM (même bon) dérivait des stades TNM faux et inventait des observations. Un template *sans* couche de validation n'est pas déployable sur un domaine à enjeu. Les guardrails doivent être **déclaratifs dans le template** et appliqués par le moteur.
- **Il faut le VOCABULAIRE par template** (et non un dictionnaire global de 100 termes) : chaque métier a son jargon et ses erreurs STT typiques.
- **Il faut une SORTIE STRUCTURÉE** (JSON par section), pas du markdown : c'est ce qui permet au frontend d'être « juste une vue » (édition par zone, champs manquants, ré-enrichissement).
- **La détection de contexte doit être automatique** (multi-sujets/multi-organes) : l'utilisateur ne choisit jamais son template à la main — le moteur sélectionne/assemble selon la dictée. (Sur MARC : détection automatique multi-organes, jamais de choix manuel.)

Autrement dit : la génération par template est excellente **si le template est un contrat complet (schéma + prompt + vocabulaire + garde-fous + enrichissements)**. C'est le contexte supplémentaire à ajouter.

---

## 3. Les endpoints à ajouter pour « ne changer que le frontend »

### 3.1 Gestion des templates (CRUD + versioning)
```
POST   /templates                 créer un template (objet §2)
GET    /templates            GET  /templates/{id}
PATCH  /templates/{id}            versionné (draft → publish)
POST   /templates/{id}/validate   lint du schéma + test à blanc
```

### 3.2 Génération pilotée par template (le point clé)
```
POST /meetings/upload
  ...+ "template_id": "acp-anapath-cr"     ← applique le template à ce meeting

POST /meetings/{id}/generate               ← (re)génère avec un template donné
  { "template_id": "...", "stream": true } ← streaming SSE de la génération
```

### 3.3 Sortie STRUCTURÉE (et non plus markdown figé)
```
GET /meetings/{id}/document?template_id=...
→ {
    "sections": { "titre": "...", "macroscopie": "...", "ihc": [...], "conclusion": "..." },
    "missing_fields": [ { "key": "grade", "reason": "attendu pour ce contexte" } ],
    "warnings": [ "mesure '42 mm' absente de la dictée" ],
    "enrichments": { "adicap": "BHRPA7A0", "snomed": {...} },
    "confidence": { "adicap": "haute" }
  }
```

### 3.4 Vocabulaire & enrichissements par API
```
PUT  /templates/{id}/vocabulary            biais STT + corrections (par métier)
GET  /enrichments                          plugins disponibles (codification, extraction, PII)
POST /enrichments/{name}/run               exécuter un enrichissement sur un document
```

### 3.5 Webhooks enrichis
```
events: meeting.document_ready, meeting.enrichment_ready, generation.chunk (si SSE indispo)
```

> **Effet net :** avec 3.1–3.5, une nouvelle verticale se lance **sans toucher au backend Gilbert** : on POST un template, on branche un frontend qui `upload(audio, template_id)` puis lit `/document`. C'est exactement l'objectif « seul le frontend change ».

---

## 4. Architecture cible (souple, multi-verticale)

```
                    ┌──────────────────────────────────────────┐
   Frontend MARC ──▶│  API Gilbert (composition)                │
   Frontend Juridique │  ┌────────┐  ┌─────────┐  ┌───────────┐ │
   Frontend Industrie │  │Template│─▶│  STT    │─▶│ Génération│ │
                    │  │ store  │  │(Lexia)  │  │ LLM+slots │ │
                    │  └────────┘  └─────────┘  └─────┬─────┘ │
                    │                    ┌────────────▼──────┐ │
                    │                    │ Guardrails (déclar.)│ │
                    │                    └────────────┬──────┘ │
                    │                    ┌────────────▼──────┐ │
                    │                    │ Enrichissements    │ │
                    │                    │ (plugins vertical) │ │
                    │                    └───────────────────┘ │
                    └──────────────────────────────────────────┘
```

Trois principes de souplesse :
1. **Template-driven** : le comportement est *déclaré*, pas codé. Nouvelle verticale = nouveau template.
2. **Guardrails déclaratifs** : la fiabilité (« ne pas inventer », « champs hors-contexte interdits ») est une propriété du template, appliquée par le moteur — indispensable pour les domaines à enjeu (médical, juridique).
3. **Enrichissements en plugins** : la codification (ADICAP/SNOMED pour le médical), l'extraction d'entités (montants, dates, articles pour le juridique), l'anonymisation PII… sont des modules activables par template.

---

## 5. Roadmap produit par sprints

Chaque sprint est livrable indépendamment et débloque des cas d'usage.

### Sprint 0 — Fondation « template = contrat » (2–3 sem.)
- Modèle de données Template (schéma + instructions + model params). CRUD `/templates`.
- `POST /meetings/upload` accepte `template_id`. `GET /meetings/{id}/document` renvoie un **JSON par sections**.
- *Débloque :* MARC passe en mode « frontend-only » pour la structure (sans encore guardrails/enrichissements).

### Sprint 1 — Sortie structurée + champs manquants (2 sem.)
- Schéma de sections typées (string/text/table). Détection des `missing_fields` selon le schéma + contexte.
- Édition par zone côté frontend (le front devient une simple vue).
- *Débloque :* complétude, ré-enrichissement par la voix, UX « champs à compléter ».

### Sprint 2 — Vocabulaire & corrections par template (1–2 sem.)
- `PUT /templates/{id}/vocabulary` (biais STT + corrections métier), injecté dans le STT et la génération.
- *Débloque :* qualité STT par métier (Gleason/Breslow médical, articles/juridictions en juridique, références pièces en industrie).

### Sprint 3 — Guardrails déclaratifs (2–3 sem.) — **le sprint « domaines à enjeu »**
- Règles activables : `no_invented_numbers`, `no_derived_staging`, `field_scope`, `negation_safety`, `citation_required` (juridique)…
- Sortie `warnings[]` + refus/flag. Validation post-génération dans le moteur.
- *Débloque :* déploiement en médical et juridique (là où une hallucination est inacceptable).

### Sprint 4 — Enrichissements en plugins (3 sem.)
- Registre `/enrichments`, exécution par template. Premiers plugins : codification (ADICAP/SNOMED), extraction d'entités, anonymisation PII.
- *Débloque :* la codification MARC devient un plugin Gilbert réutilisable ; le juridique branche « extraction de montants/dates/articles ».

### Sprint 5 — Streaming & temps réel (2 sem.)
- SSE de génération (`stream: true`) + `generation.chunk` webhook. Dictée temps réel via Lexia Pro (WebSocket) en amont.
- *Débloque :* latence perçue quasi nulle, dictée live.

### Sprint 6 — Studio de templates & marketplace (continu)
- UI de création de templates (schéma + prompt + garde-fous testés à blanc) + bibliothèque par secteur.
- *Débloque :* les verticales se créent **sans dev** (produit self-serve).

---

## 6. Décliner sur d'autres verticales (preuve de généricité)

| Vertical | Template (sections) | Vocabulaire | Guardrails clés | Enrichissements |
|---|---|---|---|---|
| **Médical / MARC** | titre, macro, micro, IHC, conclusion | Gleason, Breslow, TTF1… | pas de stade inventé, champs par organe | ADICAP, SNOMED |
| **Juridique** | parties, faits, moyens, dispositif | articles, juridictions, jurisprudence | citation obligatoire, pas d'article inventé | extraction articles/dates/montants |
| **Industrie / maintenance** | équipement, symptôme, diagnostic, action, pièces | références pièces, normes | pas de mesure inventée, pièce = référence connue | extraction réf. pièces, coûts |
| **RH / entretiens** | contexte, objectifs, évaluation, plan | compétences, échelles | anonymisation, pas de jugement inventé | PII, scoring |

Le même moteur sert les quatre : **seul le template (et le frontend) change**. C'est la démonstration concrète que la souplesse recherchée est atteignable en rendant le template « first-class ».

---

## 7. Ce qu'il faut vérifier / trancher côté Gilbert

1. **Le moteur de synthèse actuel peut-il accepter un schéma + des instructions par requête** (vs template global de compte) ? C'est le prérequis du Sprint 0.
2. **Sortie structurée** : le pipeline peut-il émettre du JSON par section plutôt que du markdown ? (Sinon : repli — le moteur MARC actuel encapsule le markdown et applique schéma+guardrails en aval ; utilisable comme pont pendant le Sprint 0–1.)
3. **Modèle** : la génération par template gagne à un LLM plus large que le 7B propriétaire pour les sections complexes ; prévoir un `model` paramétrable (Mistral large / Lexia large) par template.
4. **Guardrails** : sont-ils faisables dans le moteur, ou en post-traitement API ? (MARC les fait en post-traitement — réutilisable comme service.)
5. **Multi-tenant / secteur** : templates privés par organisation + bibliothèque publique par secteur.

---

## 8. Passerelle immédiate (sans attendre les sprints)

En attendant que l'API Gilbert soit « template-native », MARC fonctionne déjà avec l'abstraction `ReportEngine` (voir `INTEGRATION_GILBERT.md`) : le jour où `template_id` à l'upload + sortie structurée existent (Sprints 0–1), on bascule `REPORT_ENGINE=gilbert` sans toucher au frontend ni aux guardrails. MARC est donc **la première verticale de référence** de cette API composable — et son moteur (détection automatique multi-organes + injection de connaissances métier + guardrails + codification) est le patron de ce qu'il faut internaliser dans Gilbert.
