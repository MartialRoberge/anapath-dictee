"""Construction du bloc de tracabilite d'un projet (ISO 15189:2022 7.6, 8.4). Metadonnees et empreintes seulement."""
from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from projet.kb import get_kb, kb_dir
from projet.schemas import Tracabilite

VERSION_PIPELINE = "3.0.0"
_RACINE = Path(__file__).resolve().parent.parent

# Version de la base declaree « en service » (alimentee par le registre, voir routes) ; None = registre non consulte.
_en_service: str | None = None


def definir_kb_en_service(version: str | None) -> None:
    global _en_service
    _en_service = version


def kb_en_service() -> str | None:
    return _en_service


@lru_cache(maxsize=1)
def hash_git_court() -> str:
    # MARC_GIT_COMMIT (build Docker) ou RENDER_GIT_COMMIT (fourni par Render)
    env = (os.environ.get("MARC_GIT_COMMIT") or os.environ.get("RENDER_GIT_COMMIT") or "").strip()
    if env and env.isalnum():
        return env[:7]
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_RACINE, capture_output=True,
                             text=True, timeout=2, check=True).stdout.strip()
        return out if out.isalnum() else ""
    except Exception:  # noqa: BLE001 - git absent en production : pas de hash
        return ""


def version_pipeline() -> str:
    h = hash_git_court()
    return f"{VERSION_PIPELINE}+{h}" if h else VERSION_PIPELINE


def sha256_texte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


@lru_cache(maxsize=8)
def _empreinte_kb(dossier: str, signature: tuple) -> str:
    h = hashlib.sha256()
    for f in sorted(Path(dossier).glob("*.json")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def empreinte_kb() -> str:
    """SHA-256 de tous les fichiers JSON de la base (noms inclus). Vide si la base est absente."""
    d = kb_dir()
    if not d.is_dir():
        return ""
    sig = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in sorted(d.glob("*.json")))
    return _empreinte_kb(str(d), sig)


def version_kb() -> str:
    try:
        return str(get_kb().manifeste().get("version") or get_kb().manifeste().get("kb_version") or "")
    except Exception:  # noqa: BLE001
        return ""


def construire(*, projet_id: str, dictee_corrigee: str, niveau_service: str, modeles: dict[str, str]) -> Tracabilite:
    kb_v = version_kb()
    if _en_service is None:
        statut = "non_enregistree"
    else:
        statut = "en_service" if kb_v and kb_v == _en_service else "non_en_service"
    return Tracabilite(
        id=projet_id,
        horodatage_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        version_pipeline=version_pipeline(),
        kb_version=kb_v,
        kb_empreinte_sha256=empreinte_kb(),
        kb_statut=statut,  # type: ignore[arg-type]
        modeles=modeles,
        empreinte_dictee_corrigee_sha256=sha256_texte(dictee_corrigee),
        niveau_service=niveau_service,  # type: ignore[arg-type]
        statut="brouillon",
    )
