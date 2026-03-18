"""Transcription audio via Voxtral avec context_bias vocabulaire ACP."""

import httpx

from config import get_settings
from vocabulaire_acp import get_context_bias

VOXTRAL_API_URL: str = "https://api.mistral.ai/v1/audio/transcriptions"

MIME_TYPES: dict[str, str] = {
    ".webm": "audio/webm",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".m4a": "audio/mp4",
    ".mov": "video/quicktime",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}


def _detect_mime_type(filename: str) -> str:
    """Détecte le MIME type à partir de l'extension du fichier."""
    ext: str = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    return MIME_TYPES.get(ext, "audio/webm")


def _build_context_bias_csv() -> str:
    """Construit la chaîne context_bias au format CSV pour Voxtral.

    Voxtral exige des termes sans espaces ni virgules (pattern ^[^,\\s]+$).
    Les termes multi-mots sont transformés en un seul mot avec tiret,
    ou supprimés s'ils ne peuvent pas être adaptés.
    """
    terms: list[str] = get_context_bias()
    valid_terms: list[str] = []

    for term in terms:
        # Remplacer les espaces par des tirets pour les termes composés
        adapted: str = term.strip().replace(" ", "-")
        # Supprimer les virgules
        adapted = adapted.replace(",", "")
        # Vérifier qu'il reste quelque chose et pas d'espace
        if adapted and " " not in adapted:
            valid_terms.append(adapted)

    return ",".join(valid_terms)


async def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Transcrit un fichier audio via Voxtral avec biais de vocabulaire ACP.

    Supporte les formats : webm, mp3, mp4, m4a, mov, wav, ogg, flac, aac.
    Utilise le paramètre context_bias (CSV) pour orienter la reconnaissance
    vers les termes médicaux d'anatomopathologie.

    Args:
        audio_bytes: Contenu binaire du fichier audio.
        filename: Nom du fichier audio avec extension.

    Returns:
        Texte brut de la transcription.
    """
    settings = get_settings()
    mime_type: str = _detect_mime_type(filename)
    context_csv: str = _build_context_bias_csv()

    form_data: dict[str, str] = {
        "model": "voxtral-mini-latest",
        "language": "fr",
    }

    if context_csv:
        form_data["context_bias"] = context_csv

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            VOXTRAL_API_URL,
            headers={"Authorization": f"Bearer {settings.voxtral_api_key}"},
            files={"file": (filename, audio_bytes, mime_type)},
            data=form_data,
        )
        response.raise_for_status()
        data: dict[str, str] = response.json()

    return data.get("text", "")
