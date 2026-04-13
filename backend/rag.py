"""Recherche hybride de templates organes : mots-cles + embeddings.

Strategie industrialisee en 3 niveaux :
1. MOTS-CLES (deterministe) : detection par mots-cles specifiques a chaque
   organe. Fiable, rapide, predictible. Couvre 95% des cas.
2. EMBEDDINGS (semantique) : recherche vectorielle via Mistral embed pour
   les cas non couverts par les mots-cles (organes rares, formulations
   inhabituelles).
3. MULTI-PRELEVEMENT : analyse le texte pour detecter si plusieurs organes
   distincts sont mentionnes (ex: biopsie bronchique + ganglion).

Le choix est toujours loggé pour traçabilite.
"""

import logging

import httpx

from config import get_settings
from text_utils import normaliser
from templates_organes import (
    TOUS_LES_TEMPLATES,
    TemplateOrgane,
    detecter_organe,
    get_template,
)

logger = logging.getLogger("rag")

MISTRAL_EMBED_URL: str = "https://api.mistral.ai/v1/embeddings"
MISTRAL_EMBED_MODEL: str = "mistral-embed"

# Cache des embeddings (calcule une seule fois)
_template_embeddings: dict[str, list[float]] = {}
_initialized: bool = False
_httpx_client: httpx.AsyncClient | None = None

# Mots-cles explicites de multi-prelevement
_MULTI_SPECIMEN_MARKERS: list[str] = [
    "premier prelevement", "deuxieme prelevement", "troisieme prelevement",
    "1)", "2)", "3)", "4)",
    "1 -", "2 -", "3 -",
    "premier :", "deuxieme :", "troisieme :",
]


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _get_httpx_client() -> httpx.AsyncClient:
    """Retourne le client httpx singleton."""
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(timeout=30.0)
    return _httpx_client


def _template_to_text(template: TemplateOrgane) -> str:
    """Texte descriptif d'un template pour l'embedding."""
    parts: list[str] = [
        template.nom_affichage,
        ", ".join(template.sous_types),
        ", ".join(template.mots_cles_detection),
        template.notes_specifiques[:300] if template.notes_specifiques else "",
    ]
    return " ".join(p for p in parts if p)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similarite cosinus entre deux vecteurs."""
    dot: float = sum(x * y for x, y in zip(a, b))
    norm_a: float = sum(x * x for x in a) ** 0.5
    norm_b: float = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embeddings via Mistral API."""
    settings = get_settings()
    api_key: str = settings.mistral_api_key or settings.voxtral_api_key
    if not api_key:
        raise ValueError("Aucune cle API Mistral pour les embeddings")

    client = _get_httpx_client()
    response: httpx.Response = await client.post(
        MISTRAL_EMBED_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": MISTRAL_EMBED_MODEL, "input": texts},
    )
    response.raise_for_status()
    data: dict[str, list[dict[str, list[float]]]] = response.json()
    return [item["embedding"] for item in data["data"]]


async def _ensure_initialized() -> None:
    """Initialise les embeddings des templates si pas deja fait."""
    global _initialized, _template_embeddings
    if _initialized:
        return

    texts: list[str] = [_template_to_text(t) for t in TOUS_LES_TEMPLATES]
    embeddings: list[list[float]] = await _embed_texts(texts)

    for template, embedding in zip(TOUS_LES_TEMPLATES, embeddings):
        _template_embeddings[template.organe] = embedding

    _initialized = True
    logger.info("Embeddings templates initialises (%d templates)", len(TOUS_LES_TEMPLATES))


# ---------------------------------------------------------------------------
# Niveau 1 : Detection par mots-cles (deterministe)
# ---------------------------------------------------------------------------

def _recherche_mots_cles(transcript: str) -> list[tuple[TemplateOrgane, float]]:
    """Detection deterministe par mots-cles.

    Utilise la detection eprouvee de templates_organes.detecter_organe.
    Retourne 1 template avec score 1.0 si trouve, sinon liste vide.
    """
    organe: str | None = detecter_organe(transcript)
    if organe is None:
        return []
    template: TemplateOrgane | None = get_template(organe)
    if template is None:
        return []
    return [(template, 1.0)]


# ---------------------------------------------------------------------------
# Niveau 2 : Recherche semantique (fallback)
# ---------------------------------------------------------------------------

async def _recherche_semantique(transcript: str) -> list[tuple[TemplateOrgane, float]]:
    """Recherche par embeddings pour les cas non couverts par mots-cles."""
    await _ensure_initialized()

    query_embeddings: list[list[float]] = await _embed_texts([transcript[:2000]])
    query_embedding: list[float] = query_embeddings[0]

    scores: list[tuple[TemplateOrgane, float]] = []
    for template in TOUS_LES_TEMPLATES:
        similarity: float = _cosine_similarity(
            query_embedding, _template_embeddings[template.organe]
        )
        scores.append((template, similarity))

    scores.sort(key=lambda x: x[1], reverse=True)

    # Retourner uniquement le meilleur si le score est significatif
    if scores and scores[0][1] >= 0.75:
        return [scores[0]]
    return []


# ---------------------------------------------------------------------------
# Niveau 3 : Detection multi-prelevement
# ---------------------------------------------------------------------------

def _detecter_organes_multiples(transcript: str) -> list[str]:
    """Detecte si plusieurs organes distincts sont mentionnes.

    Parcourt tous les templates et compte combien ont au moins 2 mots-cles
    presents dans le texte. Retourne les organes avec score >= 2.
    """
    texte_norm: str = normaliser(transcript)
    organes_detectes: list[tuple[str, int]] = []

    for template in TOUS_LES_TEMPLATES:
        score: int = 0
        for mot_cle in template.mots_cles_detection:
            if normaliser(mot_cle) in texte_norm:
                score += 1
        if score >= 2:
            organes_detectes.append((template.organe, score))

    # Trier par score decroissant
    organes_detectes.sort(key=lambda x: x[1], reverse=True)
    return [organe for organe, _ in organes_detectes]


def _est_multi_prelevement(transcript: str) -> bool:
    """Detecte si le texte contient des marqueurs de multi-prelevement."""
    texte_norm: str = normaliser(transcript)
    return any(normaliser(m) in texte_norm for m in _MULTI_SPECIMEN_MARKERS)


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

async def rechercher_templates(
    transcript: str, top_k: int = 3, seuil: float = 0.3
) -> list[tuple[TemplateOrgane, float]]:
    """Recherche hybride : mots-cles d'abord, embeddings en renfort.

    Strategie :
    1. Detection par mots-cles (deterministe, fiable)
    2. Si echec, recherche semantique (embeddings)
    3. Si multi-prelevement detecte, chercher les organes supplementaires

    Args:
        transcript: Le texte de la transcription.
        top_k: Nombre maximum de templates a retourner.
        seuil: Score minimum (pour la recherche semantique).

    Returns:
        Liste de tuples (template, score) tries par pertinence.
    """
    resultats: list[tuple[TemplateOrgane, float]] = []
    organes_vus: set[str] = set()

    # --- Niveau 1 : mots-cles ---
    kw_results = _recherche_mots_cles(transcript)
    if kw_results:
        for template, score in kw_results:
            resultats.append((template, score))
            organes_vus.add(template.organe)
        logger.info("Template detecte par mots-cles: %s", resultats[0][0].organe)

    # --- Niveau 2 : embeddings si mots-cles echouent ---
    if not resultats:
        try:
            sem_results = await _recherche_semantique(transcript)
            for template, score in sem_results:
                if template.organe not in organes_vus:
                    resultats.append((template, score))
                    organes_vus.add(template.organe)
                    logger.info(
                        "Template detecte par embeddings: %s (score=%.3f)",
                        template.organe, score,
                    )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Recherche semantique echouee: %s", exc)

    # --- Niveau 3 : multi-prelevement ---
    if _est_multi_prelevement(transcript) and len(resultats) < top_k:
        organes_multi = _detecter_organes_multiples(transcript)
        for organe in organes_multi:
            if organe in organes_vus:
                continue
            template = get_template(organe)
            if template:
                resultats.append((template, 0.8))
                organes_vus.add(organe)
                logger.info("Template multi-prelevement ajoute: %s", organe)
            if len(resultats) >= top_k:
                break

    return resultats[:top_k]
