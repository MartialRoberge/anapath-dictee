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
| Backend | Python 3 + FastAPI |
| Transcription | Voxtral Mini (API Mistral Audio) |
| Mise en forme | Mistral Large (Chat) |

## Structure

```
├── backend/
│   ├── main.py              # Serveur FastAPI (endpoints /transcribe, /format, /export)
│   ├── config.py            # Gestion cles API via .env
│   ├── transcription.py     # Appel Voxtral
│   ├── formatting.py        # Prompt metier + appel Mistral
│   ├── export_docx.py       # Generation Word
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx           # Layout principal
│       ├── components/       # RecorderPanel, ReportPanel, Pipeline
│       ├── hooks/            # useAudioRecorder, useSoundFeedback
│       └── services/api.ts   # Client HTTP
├── regles_metier_anapath.md  # Regles metier (reference)
├── start.sh                  # Script de lancement
├── .env.example              # Template variables d'environnement
└── .gitignore
```
