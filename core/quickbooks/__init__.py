"""QuickBooks Online integration package (Prompt 3).

Splits the integration into two focused modules:

* ``client`` — OAuth flow, token refresh, QuickBooks client construction, raw
  record pull, record normalization, and the top-level ``sync_transactions``.
* ``tokens`` — at-rest encryption helpers and persistence of access/refresh
  tokens to the ``QBToken`` model.
"""