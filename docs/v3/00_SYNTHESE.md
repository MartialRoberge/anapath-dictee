# MARC v3 : synthèse (15/11/2026)

La dictée du pathologiste devient un **projet de compte rendu**. Chaque phrase est identifiée, sourcée et accompagnée d'un niveau de confiance. Les champs manquants restent visibles sous forme de trous, et chaque étape suivie par l'outil est consultable. Branche `projet-v3`.

## Pipeline (backend/projet/)

| Agent | Rôle | Moteur |
|---|---|---|
| Transcripteur | audio → texte | Voxtral |
| Correcteur phonétique | variantes STT (Phonex-FR + lexique KB), candidats proches, corrections non appliquées si confiance basse | déterministe, Mistral small si ambigu |
| Extracteur | organes, prélèvement, contexte, faits ancrés sur des passages exacts de la dictée | mistral-large-2512 |
| Rédacteur | sections et éléments, trous pour les champs obligatoires absents | mistral-large-2512 (en parallèle de l'extracteur) |
| Vérificateurs ×4 | unités mm/cm, cohérence C1-C17, complétude INCa sans faux positif, sécurité (chiffres, négations, injection) | déterministe |
| Codeur | ADICAP 2024-10 (certain/partiel), SNOMED CT (suggestion non validée) | déterministe |
| Relecteur | fidélité de chaque élément contre son passage de dictée, retrait des ajouts | mistral-medium (famille différente) |

Les mesures ci-dessous viennent de la campagne adversariale : 59 dictées réelles sur Mistral, 21 domaines, attentes écrites avant exécution.

- 0 violation de sécurité.
- 0 faux positif de champ manquant.
- 798 attentes sur 798 satisfaites.
- Latence : p50 7,0 s, p95 12,0 s.
- Environ 3 appels LLM par projet, pour un coût estimé à environ 0,004 USD (tarif à confirmer).

## Documents

| Fichier | Contenu |
|---|---|
| 01_audit_ressources.md | inventaire des ressources métier, lacunes, schéma KB |
| 02_audit_existant.md | code existant, ce qui est gardé et ce qui est refondu |
| 03_sources_web.md + sources_web/ | référentiels publics, licences |
| 05_base_connaissances.md | KB structurée (backend/kb/, scripts/build_kb.py) |
| 06_pipeline.md | agents, prompts, formule de confiance, repli N0-N3 |
| 07_telemetrie.md | événements d'usage, garanties de non-collecte médicale |
| 08_robustesse.md | campagnes, défauts corrigés, latences |
| 09_ergonomie.md + captures/ | audit UX, raccourcis, mesures de gestes |
| conformite/ | ISO 15189:2022 : matrice, analyse de risques, plan V&V, versions, statut réglementaire |

## Points ouverts (à trancher hors code)

1. **Licences** :
   - INCa : accord nécessaire pour la paraphrase.
   - SNOMED CT : statut d'affilié ANS de Gilbert.
   - ICCR : non embarqué, licence non commerciale.
2. **Validation métier par la pathologiste référente** : plages de mesures, règles de cohérence, variantes phonétiques et synonymes sont des semences à valider.
3. **Hébergement HDS** : Render n'est pas HDS. Une cible OVHcloud HDS est cohérente avec la souveraineté.
4. **Production actuelle** : l'alias `mistral-large-latest` casse l'ancien moteur. Il faut définir `MISTRAL_MODEL=mistral-large-2512` sur Render.
5. **Ancien mode étude** : il stocke encore les textes médicaux. Décision à prendre sur son avenir.

## Lancer

- Dev : backend `uvicorn main:app` (port 8000), frontend `npm run dev` (port 5173, proxy /v3).
- Démo sans backend : `?demo=1`. Ancienne interface : `?legacy=1`.
- Docker : `docker build --build-arg MARC_GIT_COMMIT=$(git rev-parse --short HEAD) -t marc-v3 .`, puis `docker compose up`.
