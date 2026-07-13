# Règles Métier — Système de Dictée Anatomopathologique

> ## DOCUMENT MÉTIER HISTORIQUE
> Ce fichier documente les **règles métier et sources** du produit MARC. Pour
> l'**implémentation à jour** (modules, moteur, guardrails), la référence est
> **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — pas ce fichier. Les chiffres
> et chemins ci-dessous ont été **réalignés sur le code réel** (juillet 2026).
>
> Où vivent réellement les règles métier dans le code :
> - `backend/templates_organes.py` — **23** templates d'organes (`TOUS_LES_TEMPLATES`,
>   modèles Pydantic `TemplateOrgane` / `ChampObligatoire`) avec données minimales INCa.
> - `backend/reports/prompts.py` — **prompts système LLM** (mise en forme + itération).
>   *(Il n'existe pas de `backend/formatting.py`.)*
> - `backend/reports/knowledge.py` — détection multi-organes et injection des
>   connaissances métier dans le prompt (`detect_organs`, `build_context_block`).
> - `backend/detection_manquantes.py` — détection des données obligatoires manquantes.
> - `backend/vocabulaire_acp.py` — **uniquement** le `context_bias` Voxtral
>   (`CONTEXT_BIAS_TERMS`, ~100 termes ACP). **Il n'y a plus de table de corrections
>   phonétiques dans le code** : la correction phonétique et l'expansion d'acronymes
>   sont désormais **déléguées au prompt LLM** (`reports/prompts.py`).
> - Codification : `backend/adicap.py`, `backend/snomed.py`.

---

## Architecture de la correction STT

Le système corrige les erreurs de transcription en **2 couches** (la couche
« table de corrections phonétiques en dur » a été retirée) :

1. **Context bias Voxtral** — ~100 termes critiques injectés via `context_bias`
   (`vocabulaire_acp.py` → `transcription.py`), pour amorcer la reconnaissance
   vocale sur le vocabulaire ACP le plus mal reconnu.
2. **Correction contextuelle par le LLM** — le prompt système
   (`reports/prompts.py`) instruit le LLM (Mistral Large par défaut) de corriger
   les erreurs résiduelles **et** de développer les acronymes, en s'appuyant sur le
   contexte anatomique. C'est ici que vivent désormais les corrections phonétiques.

## Organes couverts (23)

Sein, Côlon-Rectum, Poumon, Prostate, Estomac, Thyroïde, Rein, Vessie,
Col utérin, Endomètre, Ovaire, Mélanome, Foie, Pancréas, Œsophage,
ORL/Tête et Cou, Testicule, Lymphome, Sarcome/Tissus mous, Système nerveux
central, Canal anal/Marge anale, **Vésicule biliaire**, **Appendice**.

*(Source : `TOUS_LES_TEMPLATES` dans `backend/templates_organes.py`. En cas de
divergence, le code fait foi.)*

## Sources des données minimales

- INCa (Institut National du Cancer) — Données minimales obligatoires par localisation tumorale
- SFP (Société Française de Pathologie) — 24 fiches CRFS
- Impulsion ACP (CNPath) — 180+ modèles de comptes rendus structurés
- Classification TNM 8e édition AJCC/UICC
- Codage ADICAP (8 dictionnaires)

*(Détails et recherche complète : [recherche_standards_anatomopathologie_france.md](recherche_standards_anatomopathologie_france.md).)*
