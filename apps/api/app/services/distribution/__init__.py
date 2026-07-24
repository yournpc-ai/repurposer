"""Distribution service package (docs/DISTRIBUTION.md).

Public surface is re-exported here so ``app.services.distribution`` keeps the
single import path as the module grows (§1.1 naming convention).

- ``core``: state machine (sole ``state`` writer), credential encryption,
  publication creation / cancel / reads.
- ``channels``: OAuth connect / disconnect / token refresh lifecycle.
- ``publishing``: worker-side claim / execute / poll (fourth claim source).
- ``adapters``: per-platform OAuth + publish implementations behind
  ``PlatformAdapter``.
"""

from app.services.distribution.core import (
    DistributionError,
    cancel_publication,
    create_publication,
    decrypt_credentials,
    encrypt_credentials,
    get_publication,
    list_publications,
    retry_publication,
)
from app.services.distribution.channels import (
    connect_finish,
    connect_start,
    disconnect,
    list_channels,
    refresh_if_needed,
)
from app.services.distribution.publishing import (
    claim_due_publication,
    process_publication,
    reap_stale_publications,
)

__all__ = [
    "DistributionError",
    "cancel_publication",
    "claim_due_publication",
    "connect_finish",
    "connect_start",
    "create_publication",
    "decrypt_credentials",
    "disconnect",
    "encrypt_credentials",
    "get_publication",
    "list_channels",
    "list_publications",
    "process_publication",
    "reap_stale_publications",
    "refresh_if_needed",
    "retry_publication",
]
