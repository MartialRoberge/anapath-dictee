"""Chaine d'audit append-only : chaque entree contient le hash de la precedente (ISO 15189:2022 8.4)."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import ConformiteAudit

GENESE = "0" * 64

TYPES_EVENEMENT = (
    "generation", "validation", "revision", "derogation", "habilitation",
    "kb_approbation", "kb_mise_en_service", "kb_retrait", "non_conformite", "non_conformite_statut", "signalement_statut",
)

_verrou = asyncio.Lock()


def maintenant_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def calculer_hash(seq: int, ts: str, type_: str, acteur_id: str | None, projet_hash: str | None,
                  payload: dict[str, Any], hash_precedent: str) -> str:
    canon = json.dumps({"seq": seq, "ts": ts, "type": type_, "acteur": acteur_id, "projet": projet_hash,
                        "payload": payload, "prec": hash_precedent},
                       sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# Append-only applicatif : toute modification/suppression via l'ORM est refusee.
@event.listens_for(ConformiteAudit, "before_update")
def _refuser_maj(*_a: object) -> None:  # pragma: no cover - leve une exception
    raise RuntimeError("Journal d'audit en ajout seul : modification interdite.")


@event.listens_for(ConformiteAudit, "before_delete")
def _refuser_suppression(*_a: object) -> None:  # pragma: no cover
    raise RuntimeError("Journal d'audit en ajout seul : suppression interdite.")


async def ajouter(db: AsyncSession, type_: str, acteur_id: str | None, projet_hash: str | None,
                  payload: dict[str, Any]) -> ConformiteAudit:
    """Ajoute une entree (commit a la charge de l'appelant). Le payload doit deja etre valide."""
    if type_ not in TYPES_EVENEMENT:
        raise ValueError(f"type d'événement inconnu : {type_}")
    async with _verrou:
        dernier = (await db.execute(select(ConformiteAudit).order_by(ConformiteAudit.seq.desc()).limit(1))).scalar_one_or_none()
        seq = (dernier.seq + 1) if dernier else 1
        prec = dernier.hash if dernier else GENESE
        ts = maintenant_iso()
        h = calculer_hash(seq, ts, type_, acteur_id, projet_hash, payload, prec)
        e = ConformiteAudit(seq=seq, ts=ts, type=type_, acteur_id=acteur_id, projet_hash=projet_hash,
                            payload=payload, hash_precedent=prec, hash=h)
        db.add(e)
        await db.flush()
        await db.commit()
        return e


@dataclass
class Verification:
    ok: bool
    nb_entrees: int
    rupture_seq: int | None = None
    motif: str = ""
    dernier_hash: str = GENESE


def verifier_entrees(entrees: list[ConformiteAudit]) -> Verification:
    """Rejoue la chaine : hash recalcule, chainage, sequence sans trou."""
    prec = GENESE
    attendu = 1
    for e in entrees:
        if e.seq != attendu:
            return Verification(False, len(entrees), e.seq, "séquence interrompue (entrée supprimée ou insérée)", prec)
        if e.hash_precedent != prec:
            return Verification(False, len(entrees), e.seq, "chaînage rompu", prec)
        if calculer_hash(e.seq, e.ts, e.type, e.acteur_id, e.projet_hash, e.payload or {}, e.hash_precedent) != e.hash:
            return Verification(False, len(entrees), e.seq, "contenu altéré (hash différent)", prec)
        prec = e.hash
        attendu += 1
    return Verification(True, len(entrees), None, "", prec)


async def verifier(db: AsyncSession) -> Verification:
    res = await db.execute(select(ConformiteAudit).order_by(ConformiteAudit.seq))
    return verifier_entrees(list(res.scalars()))
