"""Public operating parameters — the ``configs`` table funnel (ADR-055).

``CONFIG_REGISTRY`` is the sole source of truth for the key set, defaults,
types and descriptions; the ``configs`` table is only the override carrier
(docs/BILLING.md §4). Three anti-drift disciplines:

1. Reads funnel through :func:`get_config` — modules never query the table
   directly; unknown keys raise immediately (no silent ``None``).
2. :func:`set_config` is the only write path (admin-prep; no endpoint this
   batch) — registry-validated, upserts, invalidates the in-process cache.
3. Boundary rule: operating parameters (changing them must not require a
   deploy) live here; engineering parameters (a wrong value breaks the
   deployment — DSNs, secrets, DB fuses) stay in env ``app/config.py``.

Cache: process-local dict, invalidated on :func:`set_config`. Rows missing
from the table read as the registry default, so a cold database (or the
worker booting before the API's startup :func:`reconcile_configs`) still
reads correctly. The cache is per-process — a value changed via the API
lands in the worker process on its next restart (house rule: changes that
affect the pipeline restart the worker anyway).
"""

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Config

logger = structlog.get_logger()


@dataclass(frozen=True)
class ConfigDef:
    """Registry entry: default value, runtime type, human description."""

    default: Any
    type: type
    desc: str


CONFIG_REGISTRY: dict[str, ConfigDef] = {
    "wallet.signup_grant": ConfigDef(
        default=10000,
        type=int,
        desc="Credits granted when a wallet is opened on first login "
        "(kind=grant, ref.source=signup).",
    ),
    "credits.per_cost_usd": ConfigDef(
        default=1000,
        type=int,
        desc="Credits per $1 of provider cost — the single consumption ratio "
        "shared by the estimate fold and captures (BILLING §4), so one edit "
        "moves every price display without a deploy and without rewriting "
        "history. NOT the purchase ratio (money→credits is the W11 pricing "
        "decision, deliberately decoupled).",
    ),
}

_cache: dict[str, Any] = {}


def _coerce(key: str, raw: Any) -> Any:
    """Cast a stored/default value to the registry type; fail loud on drift
    (a corrupt row must surface, never silently fall back to the default)."""
    defn = CONFIG_REGISTRY[key]
    try:
        return defn.type(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Config {key!r}: cannot coerce {raw!r} to {defn.type.__name__}"
        ) from e


async def get_config(db: AsyncSession, key: str) -> Any:
    """Typed read of a config key — the single read funnel.

    Raises ``KeyError`` for keys absent from the registry. A key with no row
    yet reads as the registry default: the table only carries overrides.
    """
    if key not in CONFIG_REGISTRY:
        raise KeyError(f"Unknown config key: {key!r} (not in CONFIG_REGISTRY)")
    if key in _cache:
        return _cache[key]
    row = await db.get(Config, key)
    value = _coerce(key, row.value if row is not None else CONFIG_REGISTRY[key].default)
    _cache[key] = value
    return value


async def set_config(db: AsyncSession, key: str, value: Any) -> None:
    """Write path (admin-prep). Registry-validated upsert + cache
    invalidation. Callers commit (create_notification precedent — the write
    rides the caller's transaction)."""
    if key not in CONFIG_REGISTRY:
        raise KeyError(f"Unknown config key: {key!r} (not in CONFIG_REGISTRY)")
    coerced = _coerce(key, value)
    row = await db.get(Config, key)
    if row is None:
        db.add(Config(key=key, value=coerced, description=CONFIG_REGISTRY[key].desc))
    else:
        row.value = coerced
    await db.flush()
    # 写失效 = evict, not prime: if the caller's commit later rolls back, a
    # primed cache would serve a value the DB never stored until restart;
    # evicting makes the next read re-fetch the truth.
    _cache.pop(key, None)


async def reconcile_configs(db: AsyncSession) -> list[str]:
    """Startup reconcile (``seed_default_music`` same mechanism): insert
    registry keys missing from the table, with their defaults. Existing rows
    are untouched — their values may be operator overrides. Commits only when
    something was inserted."""
    existing = set((await db.execute(select(Config.key))).scalars().all())
    missing = [key for key in CONFIG_REGISTRY if key not in existing]
    for key in missing:
        defn = CONFIG_REGISTRY[key]
        db.add(Config(key=key, value=defn.default, description=defn.desc))
    if missing:
        await db.commit()
        logger.info("configs_reconciled", keys=missing)
    return missing
