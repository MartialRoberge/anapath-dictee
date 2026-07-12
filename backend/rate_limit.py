"""Limiteur de debit partage (slowapi).

Isole dans son module pour etre importe a la fois par ``main`` (enregistrement
du handler 429) et par les routers (decorateurs ``@limiter.limit(...)``), sans
import circulaire.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
