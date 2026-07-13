# Brancher un moteur Gilbert (Lexia) sur MARC — checklist technique

Ce document est la **checklist technique d'intégration** : ce qu'il faut mettre en
place, côté application et côté API Gilbert, pour remplacer (ou compléter) le moteur
local Mistral par le moteur de synthèse Gilbert, **sans réécrire le code métier**.

> Vision produit et roadmap de l'API « template-native » : voir le document
> **[`GILBERT_API_PRODUCT.md`](GILBERT_API_PRODUCT.md)**. Trajectoire souveraineté
> et séquencement des phases : **[`NOTE_TECHNO_SOUVERAINETE.md`](NOTE_TECHNO_SOUVERAINETE.md)** §4-5.

L'architecture a été conçue pour cette bascule : le code applicatif ne dépend que
de l'interface `ReportEngine` (`backend/reports/engine.py`). Passer à Gilbert =
implémenter cette interface + configurer `REPORT_ENGINE=gilbert`.

---

## 1. Ce qui est déjà prêt côté application

| Élément | Emplacement | État |
|---|---|---|
| Interface moteur `ReportEngine` | `backend/reports/engine.py` | ✅ Fait |
| Sélecteur de moteur (`local`/`gilbert`) | `backend/reports/factory.py` + `REPORT_ENGINE` | ✅ Fait |
| Squelette `GilbertReportEngine` (upload + polling transcript) | `backend/reports/gilbert_engine.py` | ✅ Fait, testable |
| Catalogue métier des organes (détection + champs INCa) | `backend/templates_organes.py` (`TOUS_LES_TEMPLATES`, 23 organes) | ✅ Fait |
| Guardrails réutilisables sur toute sortie (locale ou distante) | `backend/reports/guardrails.py` | ✅ Fait |

Le point d'injection du `template_id` à l'upload est déjà marqué dans le code
(`GilbertReportEngine._upload`, commentaire « ajouter ici `data["template_id"]` »),
tout comme le mapping synthèse→CR structuré (`_map_summary_to_report`). Le
constructeur `GilbertReportEngine(..., gilbert_template_id=...)` accepte déjà un
identifiant de template ; en revanche **la correspondance organe → `template_id`
Gilbert n'existe pas encore** (voir §2.1, à créer).

---

## 2. Ce qu'il faut faire côté API Gilbert (tu es le contact Lexia)

L'API Gilbert v1.1.0 est aujourd'hui une API de **consommation** (upload → transcript
→ summary markdown en lecture seule). Pour l'utiliser comme moteur de génération de
CR par template, il manque trois capacités. Par ordre de priorité :

### 2.1 (BLOQUANT) Sélection de template à l'upload

**Besoin :** pouvoir dire à Gilbert quel template appliquer pour CE prélèvement.

- **Aujourd'hui :** `POST /meetings/upload` n'accepte que `file` + `title`. Le template
  appliqué est celui configuré globalement sur le compte Lexia.
- **À exposer :** un paramètre `template_id` (ou `summary_template`) dans le multipart
  de `POST /meetings/upload`, OU un endpoint `POST /meetings/{id}/summary` acceptant
  `{template_id}` pour (re)générer la synthèse avec un template choisi.
- **Côté app :** dé-commenter la ligne prête dans `GilbertReportEngine._upload`
  (`data["template_id"] = self._gilbert_template_id`) et **créer la correspondance
  organe → `template_id` Gilbert**, qui n'existe pas encore. Deux options :
  ajouter un champ optionnel (ex. `gilbert_template_id`) au modèle `TemplateOrgane`
  de `backend/templates_organes.py`, **ou** maintenir une petite table de lookup
  dédiée. Puis faire en sorte que `GilbertReportEngine.build()` sélectionne le
  `template_id` à partir de l'organe détecté.

### 2.2 (BLOQUANT) Sortie structurée exploitable

**Besoin :** récupérer non pas un markdown libre, mais les champs
`{cr, organe, type_prelevement, alertes}` — le contrat que l'app manipule partout.

- **Aujourd'hui :** `GET /meetings/{id}/summary` renvoie `summary_text` (markdown).
- **Deux options :**
  1. **Idéal —** Gilbert expose une synthèse structurée (JSON) quand le template le
     définit : champs nommés (titre, macroscopie, microscopie, conclusion) + métadonnées
     (organe, type de prélèvement). L'app mappe directement.
  2. **Repli —** l'app garde le markdown Gilbert et le passe dans les mêmes guardrails
     que le moteur local (`build_validated_report`), l'organe/type étant redéduits
     localement (via `reports/knowledge.py`). Fonctionnel mais on perd la garantie de
     structure côté serveur.
- **Côté app :** implémenter `GilbertReportEngine.generate()` (aujourd'hui lève
  `GilbertCapabilityMissing`) et `_map_summary_to_report()` (déjà esquissé).

### 2.3 (SOUHAITABLE) Création/gestion des templates via API

**Besoin :** créer et versionner les templates de CR ACP par programme (un template
par couple organe × type de prélèvement), plutôt qu'à la main dans le dashboard.

- **À exposer :** `POST /templates` (créer), `GET /templates`, `PATCH /templates/{id}`.
  Chaque template décrit la structure de synthèse + le vocabulaire métier (cf.
  l'objet Template détaillé dans `GILBERT_API_PRODUCT.md` §2).
- **Côté app :** un script de synchronisation pousserait le catalogue métier vers
  Gilbert et récupérerait les `template_id` générés, pour alimenter la
  correspondance organe → `template_id` de §2.1.

### 2.4 (SOUHAITABLE) Dictionnaire médical par API

- Gilbert supporte un dictionnaire de 100 termes **dans l'app** (acronymes, jargon).
  L'exposer par API (`GET/PUT /dictionary`) permettrait de pousser le vocabulaire ACP
  automatiquement — le `context_bias` STT de MARC est déjà centralisé dans
  `backend/vocabulaire_acp.py` (`CONTEXT_BIAS_TERMS`, ~100 termes).

---

## 3. Points d'attention fonctionnels

- **Asynchrone vs synchrone.** Gilbert est asynchrone (upload → polling/webhook). Le
  moteur déclare `capabilities.is_async = True`. Pour une bonne UX, l'app devra
  soit afficher un état « synthèse en cours » avec polling, soit s'abonner au webhook
  `meeting.summarized` (HMAC-SHA256). Le pipeline local restera préférable pour la
  dictée temps réel courte ; Gilbert est adapté aux dictées longues / batch.
- **Itération.** Gilbert n'expose pas d'endpoint d'itération sur une synthèse existante
  (`capabilities.supports_iteration = False` ; `iterate()` lève
  `GilbertCapabilityMissing`). Tant que ce n'est pas le cas, garder l'itération
  (`/iterate`) sur le moteur local, même si la génération initiale passe par Gilbert
  (**architecture hybride possible** : Gilbert pour la 1re passe, local pour les
  retouches).
- **Guardrails toujours actifs.** Quelle que soit la source (Mistral ou Gilbert), passer
  la sortie par `build_validated_report` : garde-chiffres (mesures absentes de la dictée),
  garde-négations, périmètre biopsie. C'est la garantie « faible taux d'hallucination »
  indépendante du moteur.
- **Souveraineté.** Gilbert (Lexia, OVHcloud SecNumCloud/HDS) et Mistral sont tous deux
  réputés souverains : la bascule ne change pas le positionnement RGPD/souveraineté
  (statut HDS exact à confirmer, cf. `NOTE_TECHNO_SOUVERAINETE.md` §3).

---

## 4. Checklist de bascule (le jour J)

1. [ ] Gilbert expose `template_id` à l'upload **ou** régénération par template (§2.1).
2. [ ] Gilbert renvoie une synthèse structurée **ou** on active le repli markdown+guardrails (§2.2).
3. [ ] Créer les templates ACP côté Lexia, récupérer leurs `template_id`.
4. [ ] Créer la correspondance organe → `gilbert_template_id` (champ sur `TemplateOrgane`
       ou table de lookup) et la câbler dans `GilbertReportEngine.build()`.
5. [ ] Implémenter `GilbertReportEngine.generate()` + `_map_summary_to_report()`.
6. [ ] Dé-commenter l'injection `template_id` dans `_upload`.
7. [ ] Configurer `GILBERT_API_KEY` et `REPORT_ENGINE=gilbert`.
8. [ ] Ajouter la gestion async côté frontend (polling ou webhook) si dictées longues.
9. [ ] Rejouer un harnais fonctionnel (`backend/tests/*_campaign.py`, live) contre le moteur Gilbert.

Une fois §2.1 et §2.2 disponibles côté API, la bascule applicative est de l'ordre de
**une à deux journées** (implémentation `generate` + mapping + tests), sans toucher aux
routes, au frontend, ni aux guardrails.
