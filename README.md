# Anapath - Dictee anatomopathologique

Application de dictee medicale pour anatomopathologistes. Dictez au micro, obtenez un compte-rendu structure et formate automatiquement grace a Voxtral (transcription) et Mistral (mise en forme intelligente).

## Prerequis (macOS)

- **Python 3.9+** (inclus avec macOS / Xcode CLI tools)
- **Node.js 18+** et **npm** : `brew install node`

## Installation rapide

```bash
# 1. Cloner le repo
git clone https://github.com/HugoF1234/Demo_anapath.git
cd Demo_anapath

# 2. Configurer les cles API
cp .env.example .env
# Editer .env avec vos cles Voxtral et Mistral

# 3. Installer les dependances backend
cd backend
pip3 install -r requirements.txt
cd ..

# 4. Installer les dependances frontend
cd frontend
npm install
cd ..
```

## Lancement

```bash
# Commande unique (lance backend + frontend, tue les anciens processus)
./start.sh
```

Ou manuellement dans deux terminaux :

```bash
# Terminal 1 - Backend (http://localhost:8000)
cd backend && python3 -m uvicorn main:app --reload

# Terminal 2 - Frontend (http://localhost:5173)
cd frontend && npm run dev
```

Ouvrir **http://localhost:5173** dans le navigateur.

## Utilisation

1. **Maintenir la barre espace** (ou cliquer dans la zone micro) pour dicter
2. **Relacher** pour arreter - le traitement se lance automatiquement
3. Le workflow defile : Envoi > Transcription > Lexia Intelligence > Termine
4. Le **compte-rendu formate** apparait a droite
5. Modifier la transcription brute ou le compte-rendu si besoin
6. **Exporter en .docx** ou **Copier** le resultat

## Architecture

| Couche | Technologie |
|--------|-------------|
| Frontend | React 19 + TypeScript (Vite) |
| Backend | Python 3.11+ + FastAPI |
| Transcription (STT) | Voxtral Mini (API Mistral Audio) |
| Génération (LLM) | Mistral Large par défaut, via une abstraction de fournisseur (`LLM_PROVIDER`) |
| Moteur de CR | `REPORT_ENGINE=local` (Voxtral + LLM + templates) ou `gilbert` (moteur distant Lexia) |

Le moteur de génération est **agnostique du fournisseur** : Mistral aujourd'hui,
un moteur type Gilbert demain, sans réécrire le code métier. Voir
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) et
[docs/INTEGRATION_GILBERT.md](docs/INTEGRATION_GILBERT.md).

## Structure

```
├── backend/
│   ├── main.py              # API FastAPI (transcribe/format/iterate/templates/export/...)
│   ├── config.py            # Configuration via .env
│   ├── transcription.py     # Appel Voxtral (STT)
│   ├── llm/                 # Abstraction fournisseur LLM (Mistral, Anthropic) + factory
│   ├── templates_cr/        # Catalogue de templates métier (structure + slots + formulations)
│   ├── reports/             # Moteur de CR : engine (local/gilbert), prompts, guardrails, retry
│   ├── adicap.py / snomed.py / detection_manquantes.py  # Codification & complétude
│   ├── export_docx.py       # Génération Word
│   ├── tests/               # Suite pytest (déterministe) + campagne fonctionnelle live
│   └── requirements.txt
├── frontend/                # React 19 + TS (RecorderPanel, ReportPanel, ...)
├── docs/                    # ARCHITECTURE.md, INTEGRATION_GILBERT.md
├── start.sh, .env.example
```

## Tests

```bash
cd backend
python -m pytest                       # suite déterministe (aucun appel réseau)
python tests/functional_campaign.py    # campagne live Voxtral+Mistral (consomme des crédits API)
```
