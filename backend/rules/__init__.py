"""Registry des regles metier par organe.

Expose l'API publique ``get_rules(organe)`` qui retourne l'OrganRules
associe ou le ruleset generique si l'organe n'est pas couvert.
"""

from rules.loader import get_rules, list_supported_organes, reload_rules

__all__ = ["get_rules", "list_supported_organes", "reload_rules"]
