"""Moteur MULTI-PASSES : comprendre -> rediger -> relire -> reunir le college.

Meme socle que ``LocalReportEngine`` (STT, provider, guardrails de securite), mais
la generation est decomposee en passes LLM a role explicite, ce qui apporte
l'EXPLICABILITE (on montre ce que le moteur a compris, ce que la relecture
signale et ce que le college a arbitre) sans changer le contrat : renvoie un
``GeneratedReport`` (avec `trace`).

LE COLLEGE N'EST PAS UNE QUATRIEME RELECTURE. La passe de relecture signale au
praticien ; le college, lui, DECIDE de ce qui sera soumis a validation, assertion
par assertion, sur des comptes de voix (voir reports/college.py et
etude/arbitrage.py). Ce qu'il affirme a l'unanimite, citations verifiees dans la
dictee, ne devient pas une proposition : le silence est le bon comportement.

Ce que le college a decide entre dans `trace`, avec les motifs TELS QUE les
relecteurs les ont ecrits. Rien n'y est reformule : une justification reecrite
pour le praticien ne serait plus de l'explicabilite, ce serait de la generation.

Plus lent (6 appels LLM au lieu d'1) — choix assume : qualite + transparence.
La configuration permet de couper le college pour mesurer sans lui.
"""

from __future__ import annotations

import logging

from etude.arbitrage import Arbitrage, Soumission, arbitrer, taux_de_soumission
from etude.extraction import AssertionNumerotee, assertions_a_juger, rattacher_les_rangs
from reports.college import LENTILLES, RapportCollege, reunir_le_college
from reports.engine import EngineCapabilities, GeneratedReport, ReportEngine
from reports.guardrails import GenerationParseError, build_validated_report, parse_llm_json
from reports.comblement import combler_depuis_la_dictee
from reports.knowledge import ContextResult, build_context_block
from reports.local_engine import LocalReportEngine
from reports.prompts import build_format_user_prompt
from reports.prompts_multipass import (
    build_comprehension_hint,
    build_comprehension_system_prompt,
    build_comprehension_user_prompt,
    build_redaction_system_prompt,
    build_relecture_system_prompt,
    build_relecture_user_prompt,
)

logger = logging.getLogger("anapath.engine.multipass")

_CATEGORIE_LABEL: dict[str, str] = {
    "fidelite": "Fidélité",
    "manque": "Donnée manquante",
    "incertitude": "À vérifier",
    "coherence": "Cohérence",
}

_PASSES_DE_BASE: tuple[str, ...] = ("comprehension", "redaction", "relecture")


class MultiPassReportEngine(LocalReportEngine):
    """Génération en passes explicites, sur le socle local.

    Trois passes redigent le compte rendu, une quatrieme le fait relire par le
    college — qui arbitre ce qui sera soumis au praticien, et qui peut etre
    coupe par configuration.
    """

    capabilities = EngineCapabilities(
        name="multipass",
        separate_transcription=True,
        is_async=False,
        supports_templates=True,
        supports_iteration=True,
    )

    async def generate(
        self, transcript: str, *, rapport_precedent: str = ""
    ) -> GeneratedReport:
        # --- Passe 1 : COMPREHENSION (adaptable, explicable) --------------
        comprehension = await self._comprehend(transcript)

        # Ressources metier deterministes (INCa, formulations maison) : inchangees.
        context: ContextResult = build_context_block(transcript)
        logger.info(
            "multipass: organes(det)=%s | organes(compris)=%s",
            context.organes, comprehension.get("organes"),
        )

        # --- Passe 2 : REDACTION (prompt allege) -------------------------
        system_prompt: str = build_redaction_system_prompt(context.block)
        user_prompt: str = (
            build_comprehension_hint(comprehension)
            + build_format_user_prompt(transcript, rapport_precedent)
        )
        raw: str = await self._complete(system_prompt, user_prompt, label="redaction")
        report: GeneratedReport = build_validated_report(
            raw,
            source_text=transcript,
            organes=context.organes,
            provider=self._provider.name,
            model=self._provider.model,
        )

        # --- GARDE-FOU : ne pas redemander ce qui a ete dicte ------------
        #
        # La regle est dans le prompt, en toutes lettres et avec son exemple.
        # Elle n'a pas suffi : sur une dictee telegraphique — « PD-L1, 5% » —
        # le modele ne rattache pas la valeur a son etiquette et pose un trou.
        # Le praticien a parle pour ne pas avoir a taper ; on lui rendait un
        # formulaire. Ce comblement-ci est DETERMINISTE et ne comble que si
        # l'etiquette figure une seule fois dans la dictee, suivie d'une valeur.
        cr_comble, combles = combler_depuis_la_dictee(report.cr, transcript)
        if combles:
            report.cr = cr_comble
            # Trace, pour que l'explicabilite dise d'ou vient chaque valeur :
            # un comblement qu'on ne peut pas justifier serait indistinguable
            # d'une invention.
            report.trace["comblements"] = [
                {"champ": c.champ, "valeur": c.valeur, "source": c.source}
                for c in combles
            ]

        # --- Passe 3 : RELECTURE (signale, ne reecrit pas) ---------------
        signalements = await self._review(report.cr, transcript)

        # --- Passe 4 : COLLEGE (arbitre ce qui sera soumis) --------------
        college = await self._reunir_le_college(report.cr, transcript)

        # Les signalements de relecture rejoignent les warnings (canal deja
        # remonte au front) et la trace d'explicabilite.
        report.warnings = report.warnings + [
            f"Relecture — {_CATEGORIE_LABEL.get(str(s.get('categorie')), 'Note')} : "
            f"{s.get('message', '')}"
            for s in signalements
        ]
        report.trace = {
            "comprehension": comprehension,
            "signalements": signalements,
            # None quand le college n'a pas siege : l'etude retombe alors sur le
            # decoupage mecanique (voir etude/extraction.py).
            "college": college,
            "passes": _passes(self._provider.model, college is not None),
        }
        return report

    # -- Passes annexes (degradation gracieuse : jamais bloquantes) --------

    async def _comprehend(self, transcript: str) -> dict[str, object]:
        """Passe 1. Retourne {} si la comprehension echoue (on continue sans)."""
        try:
            raw = await self._complete(
                build_comprehension_system_prompt(),
                build_comprehension_user_prompt(transcript),
                label="comprehension",
            )
            data = parse_llm_json(raw)
            return data if isinstance(data, dict) else {}
        except (GenerationParseError, ValueError, Exception) as exc:  # noqa: BLE001
            logger.warning("comprehension ignoree : %s", exc)
            return {}

    async def _review(self, cr: str, transcript: str) -> list[dict[str, object]]:
        """Passe 3. Retourne [] si la relecture echoue (on continue sans)."""
        try:
            raw = await self._complete(
                build_relecture_system_prompt(),
                build_relecture_user_prompt(cr, transcript),
                label="relecture",
            )
            data = parse_llm_json(raw)
            items = data.get("signalements") if isinstance(data, dict) else None
            if not isinstance(items, list):
                return []
            return [s for s in items if isinstance(s, dict) and s.get("message")]
        except (GenerationParseError, ValueError, Exception) as exc:  # noqa: BLE001
            logger.warning("relecture ignoree : %s", exc)
            return []

    async def _reunir_le_college(
        self, cr: str, transcript: str
    ) -> dict[str, object] | None:
        """Passe 4. Retourne None quand le college n'a pas siege.

        Trois cas de non-tenue, et tous les trois retombent sur le decoupage :
        l'option est coupee, le compte rendu ne contient rien a juger, ou aucun
        relecteur n'a repondu.
        """
        if not self._settings.college_actif:
            return None

        assertions = assertions_a_juger(cr, transcript)
        if not assertions:
            return None

        rapport = await reunir_le_college(
            self._provider,
            transcript,
            cr,
            [(une.rang, une.texte) for une in assertions],
        )
        if rapport.quorum == 0:
            # Aucune lentille n'a repondu : c'est une PANNE, pas un desaccord.
            # Arbitrer la-dessus soumettrait toutes les assertions en les
            # declarant non ancrees, alors que le decoupage sait encore les
            # ancrer dans la dictee. On rend la main au repli.
            logger.warning("college muet : repli sur le decoupage")
            return None

        arbitrage = arbitrer(
            rattacher_les_rangs(rapport, assertions),
            [une.texte for une in assertions],
            transcript,
        )
        logger.info(
            "college: quorum=%s | soumises=%s/%s",
            rapport.quorum, len(arbitrage.a_valider), len(arbitrage.soumissions),
        )
        return _trace_du_college(rapport, arbitrage, assertions)


def _passes(model: str, avec_college: bool) -> list[dict[str, str]]:
    """Les passes reellement executees, pour que la latence soit imputable."""
    passes = [{"role": role, "model": model} for role in _PASSES_DE_BASE]
    if avec_college:
        passes.extend(
            {"role": f"college:{lentille.cle}", "model": model}
            for lentille in LENTILLES
        )
    return passes


def _trace_du_college(
    rapport: RapportCollege,
    arbitrage: Arbitrage,
    assertions: list[AssertionNumerotee],
) -> dict[str, object]:
    """Ce que le college a decide, sous une forme que le front peut afficher.

    Le taux de soumission est consigne a chaque generation : c'est l'indicateur
    a suivre, et il doit BAISSER quand la redaction s'ameliore.
    """
    sections = {une.rang: une.section for une in assertions}
    return {
        "quorum": rapport.quorum,
        "lentilles_muettes": list(rapport.lentilles_muettes),
        "taux_de_soumission": taux_de_soumission(arbitrage),
        "soumissions": [
            _trace_soumission(soumission, sections.get(soumission.rang, ""))
            for soumission in arbitrage.soumissions
        ],
        "manques": [
            {"champ": manque.champ, "justification": manque.justification}
            for manque in arbitrage.manques
        ],
    }


def _trace_soumission(soumission: Soumission, section: str) -> dict[str, object]:
    """Le sort d'une assertion, avec de quoi le verifier sans nous croire.

    Les justifications sont RECOPIEES telles que les relecteurs les ont ecrites
    en jugeant. Les reformuler pour le praticien reviendrait a generer
    l'explication d'une decision au lieu de la constater — ce ne serait plus de
    l'explicabilite. Le decompte des voix joue le meme role qu'un score de
    confiance, en verifiable : "deux relecteurs sur trois ont retrouve ce
    passage dans votre dictee" se controle, un 0,73 ne se controle pas.
    """
    empan = soumission.empan
    return {
        "rang": soumission.rang,
        "section": section,
        "assertion": soumission.assertion,
        "comportement": soumission.comportement,
        "motif": soumission.motif,
        "voix_pour": soumission.voix_pour,
        "voix_total": soumission.voix_total,
        "empan_debut": empan.debut if empan is not None else None,
        "empan_fin": empan.fin if empan is not None else None,
        "empan_extrait": empan.extrait if empan is not None else "",
        "justifications": list(soumission.justifications),
    }


_: type[ReportEngine] = MultiPassReportEngine
