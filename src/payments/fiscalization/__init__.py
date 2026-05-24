"""Fiscalization — reporting payment income to the Russian tax authority (ФНС).

Currently implements a single integration path: direct calls to «Мой налог»
(``lknpd.nalog.ru``) via the unofficial ``nalogo`` library. Architected as a
shared singleton ``MoyNalogClient`` that ``PaymentProvider``-s inject into their
``fiscalize_income`` flow.

The wrapper exists for two reasons beyond just calling the SDK:

1. **Single point of escape** — if ``nalogo`` ever needs swapping (e.g. it stops
   tracking ФНС API breakages), only this package changes.
2. **Domain DTO** — providers and business logic talk about ``FiscalReceipt``
   instead of provider-specific ``dict``. Keeps the SDK boundary clean.

Public surface:
- ``FiscalReceipt`` — what a successful registration returns.
- ``FiscalizationError`` — base exception; everything bubbling out of the
  underlying SDK is wrapped in this.
- ``MoyNalogClient`` — the wrapper itself (singleton, built in
  ``src.payments.runtime``).
"""

from .base import FiscalizationError, FiscalReceipt
from .moy_nalog import MoyNalogClient

__all__ = ["FiscalReceipt", "FiscalizationError", "MoyNalogClient"]
