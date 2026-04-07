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
    """Detecte le MIME type a partir de l'extension du fichier."""
    ext: str = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    return MIME_TYPES.get(ext, "audio/webm")


def _adapt_term_for_context_bias(term: str) -> str:
    """Adapte un terme pour le format context_bias Voxtral.

    Voxtral exige des termes sans espaces ni virgules (pattern ^[^,\\s]+$).
    Les espaces sont remplaces par des tirets, les virgules supprimees.
    """
    adapted: str = term.strip().replace(" ", "-")
    adapted = adapted.replace(",", "")
    return adapted


def _build_context_bias_csv() -> str:
    """Construit la chaine context_bias au format CSV pour Voxtral."""
    terms: list[str] = get_context_bias()
    valid_terms: list[str] = []

    for term in terms:
        adapted: str = _adapt_term_for_context_bias(term)
        if adapted and " " not in adapted:
            valid_terms.append(adapted)

    return ",".join(valid_terms)


async def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    """Transcrit un fichier audio via Voxtral avec biais de vocabulaire ACP.

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
        response: httpx.Response = await client.post(
            VOXTRAL_API_URL,
            headers={"Authorization": f"Bearer {settings.voxtral_api_key}"},
            files={"file": (filename, audio_bytes, mime_type)},
            data=form_data,
        )
        response.raise_for_status()
        data: dict[str, str] = response.json()

    return data.get("text", "")
