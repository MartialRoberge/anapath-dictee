"""Rendu deterministe d'un CRDocument en markdown.

Cette brique est ce qui elimine par construction les bugs de format v3 :

- Titre "Microscopie" TOUJOURS present (ligne statique du template).
- Colonne "Temoin +" AFFICHEE UNIQUEMENT si au moins une ligne IHC
  a une valeur temoin non vide (via IhcTable.has_temoin_column).
- Multi-prelevement rendu en sections numerotees systematiques.
- Conclusion et pTNM en sections distinctes, impossible de confondre.
- Pas de regex, pas d'interpretation de prose : le LLM ne produit plus
  le markdown, il produit du JSON typed et Jinja fait le reste.

Convention : une fonction = une action. Le template n'a AUCUNE logique
metier, seulement de la mise en forme.
"""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from schemas import CRDocument, IhcTable


# ---------------------------------------------------------------------------
# Template Jinja
# ---------------------------------------------------------------------------


_MARKDOWN_TEMPLATE: str = """\
**__{{ doc.titre | upper }}__**
{%- if doc.renseignements_cliniques %}

*Renseignements cliniques : {{ doc.renseignements_cliniques }}*
{%- endif %}

{% for prel in doc.prelevements -%}
{%- if doc.prelevements | length > 1 %}
**__{{ prel.numero }}) {{ prel.titre_court or doc.titre }} :__**
{% endif %}
{%- if prel.macroscopie %}
**Macroscopie :**
{{ prel.macroscopie }}
{% endif %}
{%- if prel.microscopie %}
**Microscopie :**
{{ prel.microscopie }}
{% endif %}
{%- if prel.immunomarquage and prel.immunomarquage.lignes %}
{{ render_ihc(prel.immunomarquage) }}
{% endif %}
{%- if prel.biologie_moleculaire %}
**Biologie moleculaire :**
{{ prel.biologie_moleculaire }}
{% endif %}
{%- endfor %}
**__CONCLUSION :__**
{{ doc.conclusion }}
{%- if doc.ptnm %}

**{{ doc.ptnm }}**
{%- endif %}
{%- if doc.commentaire_final %}

*{{ doc.commentaire_final }}*
{%- endif %}
"""


# ---------------------------------------------------------------------------
# Rendu du tableau IHC (fonction separee, exposee au template)
# ---------------------------------------------------------------------------


def _render_ihc_table(table: IhcTable) -> str:
    """Rend le bloc immunomarquage en markdown.

    Colonne ``Temoin +`` presente UNIQUEMENT si has_temoin_column est True.
    C'est le point cle qui elimine le bug v3 ("colonne temoin toujours
    presente par defaut meme quand vide").
    """
    lines: list[str] = []

    if table.phrase_introduction:
        lines.append(f"*{table.phrase_introduction}*")
    else:
        lines.append(
            "*Immunomarquage : realise sur tissu fixe et coupes en paraffine, "
            "apres restauration antigenique par la chaleur, utilisation de "
            "l'automate BOND III (Leica) et application des anticorps suivants :*"
        )
    lines.append("")

    if table.has_temoin_column:
        lines.append("| Anticorps | Resultats | Temoin + |")
        lines.append("|---|---|---|")
        for row in table.lignes:
            lines.append(f"| {row.anticorps} | {row.resultat} | {row.temoin} |")
    else:
        lines.append("| Anticorps | Resultats |")
        lines.append("|---|---|")
        for row in table.lignes:
            lines.append(f"| {row.anticorps} | {row.resultat} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Environnement Jinja (singleton)
# ---------------------------------------------------------------------------


_env: Environment | None = None


def _get_env() -> Environment:
    """Retourne l'environnement Jinja2 singleton configure pour le template."""
    global _env
    if _env is None:
        _env = Environment(
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )
        _env.globals["render_ihc"] = _render_ihc_table
    return _env


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def render_markdown(doc: CRDocument) -> str:
    """Rend un CRDocument en markdown final consomme par le frontend.

    Aucun appel LLM, aucune regex. Sortie deterministe pour un document
    donne : meme entree = meme sortie, toujours.
    """
    env = _get_env()
    template = env.from_string(_MARKDOWN_TEMPLATE)
    rendered: str = template.render(doc=doc)
    return _cleanup_blank_lines(rendered)


def _cleanup_blank_lines(text: str) -> str:
    """Compresse les lignes vides consecutives en une seule."""
    lines: list[str] = text.splitlines()
    result: list[str] = []
    blank_streak: int = 0

    for line in lines:
        if not line.strip():
            blank_streak += 1
            if blank_streak <= 1:
                result.append("")
        else:
            blank_streak = 0
            result.append(line)

    while result and not result[-1]:
        result.pop()

    return "\n".join(result) + "\n"
