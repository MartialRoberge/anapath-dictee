# Règles Métier — Système de Dictée Anatomopathologique

> **Ce fichier est conservé à titre de documentation.**
> Les règles métier sont désormais codées dans les modules Python :
> - `backend/vocabulaire_acp.py` — 240 corrections phonétiques, 68 acronymes, 91 marqueurs IHC, 52 négations
> - `backend/templates_organes.py` — 21 templates organes avec données minimales INCa
> - `backend/formatting.py` — Prompts système LLM (mise en forme + itération)
> - `backend/detection_manquantes.py` — Détection des données obligatoires manquantes

---

## Architecture de la correction STT

Le système corrige les erreurs de transcription en **3 couches** :

1. **Context bias Voxtral** — ~100 termes critiques injectés via `context_bias` (expérimental pour le français)
2. **Correction phonétique** — 240 règles de remplacement appliquées sur le transcript brut avant envoi au LLM
3. **Correction contextuelle LLM** — Le prompt système instruit Mistral Large de corriger les erreurs restantes en utilisant le contexte anatomique

## Organes couverts (21)

Sein, Côlon-Rectum, Poumon, Prostate, Estomac, Thyroïde, Rein, Vessie,
Col utérin, Endomètre, Ovaire, Mélanome, Foie, Pancréas, Œsophage,
ORL/Tête et cou, Testicule, Lymphome, Sarcome, SNC, Canal anal

## Sources des données minimales

- INCa (Institut National du Cancer) — Données minimales obligatoires par localisation tumorale
- SFP (Société Française de Pathologie) — 24 fiches CRFS
- Impulsion ACP (CNPath) — 180+ modèles de comptes rendus structurés
- Classification TNM 8e édition AJCC/UICC
- Codage ADICAP (8 dictionnaires)
