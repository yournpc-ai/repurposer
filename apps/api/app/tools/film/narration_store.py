"""Film narration reuse store (ADR-138 R4-A — 总设计 §10.1).

ONE row per (project_id, content_hash) holding the ORIGINAL speed-1.0
synthesis of one narration line; versions/runs of the same project reuse
it. Reuse keys on the ACTUAL synthesis configuration — ``content_hash`` =
sha256 over the canonical identity (normalized text | RESOLVED voice_id |
language | synthesis config) — never a display name, never an unresolved
Auto. Speed adaptation is a runtime RE-SYNTHESIS: an unfit hit re-calls the
provider at the computed speed — a real, metered vendor call — seeded from
the stored original's KNOWN 1.0 duration (the ladder resumes at pass 2
instead of starting cold). The adapted product is a run-level staging file
(never stored, never in the hash); a missing staging file is never a loss —
the stored row plus the target window fully determine what to re-synthesize.
Never a local speed transform of the original's bytes, never free: no
zero-TTS and no deterministic-recovery claim.

The concurrency laws (闸 16 — the unique index alone does NOT prevent
duplicate TTS calls; every write is ownership-conditioned):

1. **原子占位** — ``INSERT … ON CONFLICT DO NOTHING`` mints the
   placeholder (``status='synthesizing'``, owner_token + lease); the
   winner synthesizes, everyone else reads the committed row.
2. **有界等待/接管** — a placeholder past its lease is taken over by a
   conditional UPDATE (still ``synthesizing`` + lease expired): exactly
   one row affected = the takeover landed; zero = re-read (someone else
   finished or took over).
3. **完成经 owner 校验** — the audio first lands at a token-suffixed
   staging object; the finalize UPDATE carries ``owner_token=me AND
   status='synthesizing'``. Zero rows = ownership lost → the loser deletes
   ONLY its own staging object and re-reads the row for the winner's
   result — never an unconditional overwrite.
4. **过期不得覆盖/删除** — every write keeps the double condition; staging
   objects are token-isolated, cleanup only ever touches one's own.
5. **失败不留毒** — a failed synthesis deletes its placeholder under the
   same owner condition; rows already ``done`` survive a failed run (the
   resource is lawful — later runs reuse it).

File loss self-heals: a ``done`` row whose storage object is gone reads as
a miss (the row deletes, the line re-synthesizes, the loss is logged). The
self-heal's delete is bound to the EXACT record that was read and proven
lost — primary-key identity plus the ``done`` status that was seen: a
concurrent request's fresh placeholder or committed result is a DIFFERENT
row and can never match, so a late self-heal lands zero rows and re-reads
instead of deleting the living world (the publish window's minimal
protection rides the same conditional single statements as laws 1–5 — no
wider machinery).

Zero LLM here. All seats commit through independent short sessions — the
run's own transaction never carries the store (a run rollback must not
un-commit a completed synthesis).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = structlog.get_logger()

# One synthesis occupancy's lease: comfortably over the bounded ladder's
# wall-clock (a few provider calls at ≤180s timeouts), far under any
# human-scale wait. A crashed owner never blocks a hash beyond this.
LEASE_S = 600.0
# Bounded wait for another owner's result: poll cadence and total budget
# (a fresh synthesis completes well inside the lease; the waiter outlives
# ONE lease so a crashed owner's hash gets taken over, not abandoned).
_WAIT_POLL_S = 2.0
_WAIT_BUDGET_S = LEASE_S + 120.0


def narration_synth_config() -> dict:
    """The current synthesis configuration fact (the hash's config half):
    the provider/model/format the original synthesis runs under. Speed is
    NOT part of it — the store holds only speed-1.0 originals; adaptation
    re-synthesizes at run time (metered — see the module docstring)."""
    from app.providers import voice  # deferred: provider leaf

    return {
        "provider": "minimax",
        "model": voice.tts_model(),
        "sample_rate": 32000,
        "format": "mp3",
        "speed_base": 1.0,
    }


def narration_content_hash(
    *, text: str, voice_id: str, language: str, config: dict
) -> tuple[str, str]:
    """The reuse identity: sha256 over the canonical synthesis identity —
    normalized text (whitespace-collapsed) | resolved voice_id | language |
    config. Returns (content_hash, config_hash)."""
    normalized = " ".join(text.split())
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payload = json.dumps(
        {
            "text": normalized,
            "voice_id": voice_id,
            "language": language,
            "config": config_hash,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), config_hash


def adaptation_speed(*, duration_s: float, window_s: float, speed_max: float) -> float | None:
    """The deterministic adaptation decision (the reuse contract's second
    gate — a hash hit is not automatically usable): the original's REAL
    duration against the target window. None = the original fits as-is;
    otherwise the provider speed that fits (≤ ``speed_max``), or
    ``speed_max`` itself when even the cap cannot fit (the caller's flex /
    honest-failure law takes over — the same terminal shape as the
    pre-store ladder)."""
    if duration_s <= window_s:
        return None
    needed = duration_s / max(window_s, 0.2)
    return min(needed, speed_max)


@dataclass
class NarrationReuse:
    """A resolved store state for one line: either the reuse answer (a done
    row's original — key + real duration) or the synthesis occupancy this
    run now owns (``owner_token`` — finalize/fail must carry it)."""

    storage_key: str | None
    duration_s: float | None
    owner_token: str | None

    @property
    def reusable(self) -> bool:
        return self.storage_key is not None


def _store_session():
    from app.models.database import AsyncSessionLocal  # deferred: worker seat

    return AsyncSessionLocal()


async def _read_row(project_id: UUID, content_hash: str):
    from app.models.tables import FilmNarration  # deferred: table seat

    async with _store_session() as session:
        row = (
            await session.execute(
                select(
                    FilmNarration.id,
                    FilmNarration.status,
                    FilmNarration.storage_key,
                    FilmNarration.duration_s,
                    FilmNarration.lease_expires_at,
                ).where(
                    FilmNarration.project_id == project_id,
                    FilmNarration.content_hash == content_hash,
                )
            )
        ).first()
    return row


async def _storage_exists(key: str | None) -> bool:
    from app.providers import storage  # deferred: provider leaf

    try:
        return await storage.exists(key)
    except Exception as e:  # noqa: BLE001 — an unreadable store never blocks
        logger.warning("film_narration_exists_check_failed", error=str(e))
        return True  # fail OPEN on errors (only a proven 404 self-heals)


async def resolve_narration(
    project_id: UUID,
    *,
    text: str,
    voice_id: str,
    language: str,
    config: dict | None = None,
) -> NarrationReuse:
    """The synthesis path's ONE store seat: resolve the line's reuse state.

    - a ``done`` row whose object exists → its (key, duration) rides back
      (zero synthesis);
    - a ``done`` row whose object is GONE → the row deletes (self-heal,
      logged) and the line re-enters as a miss;
    - no row → the atomic placeholder INSERT (law 1): winner = owner
      (``owner_token`` set); loser = a committed row appeared mid-flight
      (re-read once);
    - a live placeholder owned elsewhere → the bounded wait (law 2): poll
      the committed row in short sessions; the lease lapsing without a
      finalize → the conditional takeover UPDATE (still synthesizing +
      lease expired — one row affected = ours, zero = re-read); a vanished
      placeholder (the owner's failure deleted it) = re-enter the claim;
    - the wait budget exhausting → the honest tail: take over ourselves
      once more, else keep waiting never happens — the budget bounds it.
    """
    cfg = config if config is not None else narration_synth_config()
    content_hash, config_hash = narration_content_hash(
        text=text, voice_id=voice_id, language=language, config=cfg
    )
    from app.models.tables import FilmNarration  # deferred: table seat

    deadline = time.monotonic() + _WAIT_BUDGET_S
    while True:
        row = await _read_row(project_id, content_hash)
        if row is not None and row.status == "done":
            if await _storage_exists(row.storage_key):
                return NarrationReuse(row.storage_key, row.duration_s, None)
            # 文件丢失自愈: a done row whose object vanished reads as a miss.
            # The delete is bound to the EXACT record we read and proved
            # lost (primary key + the status we saw) — between our read and
            # this delete another reader may have healed the hash already;
            # their fresh placeholder/result is a different row and must
            # survive our late delete (zero rows → the claim path re-reads).
            logger.warning(
                "film_narration_object_lost",
                project_id=str(project_id),
                content_hash=content_hash,
            )
            await _delete_lost_row(project_id, content_hash, row_id=row.id)
            row = None
        if row is None:
            token = uuid4().hex
            async with _store_session() as session:
                inserted = (
                    await session.execute(
                        pg_insert(FilmNarration)
                        .values(
                            project_id=project_id,
                            content_hash=content_hash,
                            voice_id=voice_id,
                            language=language,
                            config_hash=config_hash,
                            text=" ".join(text.split()),
                            status="synthesizing",
                            owner_token=token,
                            lease_expires_at=datetime.now(UTC)
                            + timedelta(seconds=LEASE_S),
                        )
                        .on_conflict_do_nothing(
                            index_elements=["project_id", "content_hash"]
                        )
                        .returning(FilmNarration.id)
                    )
                ).first()
                await session.commit()
            if inserted is not None:
                return NarrationReuse(None, None, token)
            continue  # a committed row appeared mid-flight — re-read it
        # A placeholder owned elsewhere: wait out its lease, then try the
        # conditional takeover ONCE per pass (law 2); the budget bounds the
        # whole wait.
        if time.monotonic() > deadline:
            raise TimeoutError(
                "narration store wait budget exhausted — the owning "
                "synthesis never finalized in time"
            )
        lease = row.lease_expires_at
        lease_expired = not isinstance(lease, datetime) or lease <= datetime.now(UTC)
        if lease_expired:
            takeover = await _try_takeover(project_id, content_hash)
            if takeover is not None:
                return NarrationReuse(None, None, takeover)
            continue  # someone else finished or took over — re-read
        await asyncio.sleep(_WAIT_POLL_S)


async def _try_takeover(project_id: UUID, content_hash: str) -> str | None:
    """Law 2's conditional takeover: lands only while the row is still
    ``synthesizing`` past its lease. Returns OUR new owner token, else
    None (re-read — someone else finished or took over)."""
    from app.models.tables import FilmNarration  # deferred: table seat

    token = uuid4().hex
    async with _store_session() as session:
        result = await session.execute(
            update(FilmNarration)
            .where(
                FilmNarration.project_id == project_id,
                FilmNarration.content_hash == content_hash,
                FilmNarration.status == "synthesizing",
                FilmNarration.lease_expires_at < datetime.now(UTC),
            )
            .values(
                owner_token=token,
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=LEASE_S),
            )
        )
        await session.commit()
    return token if (result.rowcount or 0) == 1 else None


async def finalize_narration(
    project_id: UUID,
    *,
    text: str,
    voice_id: str,
    language: str,
    owner_token: str,
    staging_key: str,
    duration_s: float,
    config: dict | None = None,
) -> tuple[str, float]:
    """Law 3: publish the synthesized original under owner校验. The audio
    MUST already sit at ``staging_key`` (the token-suffixed object — the
    row adopts that key verbatim). Returns the AUTHORITATIVE
    ``(storage_key, duration_s)`` pair: ours when the conditional UPDATE
    landed; the winner's when it did not (zero rows = ownership lost — we
    delete ONLY our own staging object and re-read the committed row, never
    an unconditional overwrite). The pair matters: a straddled finalize
    must never couple our decoded seconds to someone else's audio."""
    from app.models.tables import FilmNarration  # deferred: table seat

    cfg = config if config is not None else narration_synth_config()
    content_hash, _ = narration_content_hash(
        text=text, voice_id=voice_id, language=language, config=cfg
    )
    async with _store_session() as session:
        result = await session.execute(
            update(FilmNarration)
            .where(
                FilmNarration.project_id == project_id,
                FilmNarration.content_hash == content_hash,
                FilmNarration.owner_token == owner_token,
                FilmNarration.status == "synthesizing",
            )
            .values(
                status="done",
                storage_key=staging_key,
                duration_s=duration_s,
            )
        )
        await session.commit()
    if (result.rowcount or 0) == 1:
        return staging_key, duration_s
    # Ownership lost (a takeover finalized first): drop ONLY our staging
    # object, then read the winner's committed result. The cleanup is
    # best-effort — a storage hiccup never masks the real outcome (the
    # orphan is token-suffixed and reaped by the bucket's own hygiene).
    from app.providers import storage  # deferred: provider leaf

    try:
        await storage.delete(staging_key)
    except Exception as e:  # noqa: BLE001 — cleanup must never mask the outcome
        logger.warning("film_narration_staging_cleanup_failed", error=str(e))
    row = await _read_row(project_id, content_hash)
    if (
        row is not None
        and row.status == "done"
        and row.storage_key
        and row.duration_s is not None
    ):
        return row.storage_key, row.duration_s
    raise TimeoutError(
        "narration store finalize lost ownership and no committed result "
        "stands — the line re-synthesizes on the next attempt"
    )


async def fail_narration(
    project_id: UUID,
    *,
    text: str,
    voice_id: str,
    language: str,
    owner_token: str,
    config: dict | None = None,
) -> None:
    """Law 5: a failed synthesis deletes its OWN placeholder only — the
    double condition (owner + still synthesizing) means an expired owner's
    late failure never deletes a takeover's row."""
    cfg = config if config is not None else narration_synth_config()
    content_hash, _ = narration_content_hash(
        text=text, voice_id=voice_id, language=language, config=cfg
    )
    await _delete_row(project_id, content_hash, owner_token=owner_token)


async def _delete_lost_row(project_id: UUID, content_hash: str, *, row_id) -> None:
    """The self-heal's conditional delete — bound to the EXACT record whose
    object was proven lost: the primary key AND the ``done`` status that was
    read. Zero rows affected = the world already moved on (another reader
    healed the hash first; a fresh placeholder or a committed result now
    stands under it) — the caller falls through to the claim path, whose
    ON CONFLICT re-read absorbs every shape. Never an unconditional delete
    by hash: that would reap a concurrent request's living row."""
    from app.models.tables import FilmNarration  # deferred: table seat

    async with _store_session() as session:
        await session.execute(
            delete(FilmNarration).where(
                FilmNarration.project_id == project_id,
                FilmNarration.content_hash == content_hash,
                FilmNarration.id == row_id,
                FilmNarration.status == "done",
            )
        )
        await session.commit()


async def _delete_row(
    project_id: UUID, content_hash: str, *, owner_token: str | None = None
) -> None:
    from app.models.tables import FilmNarration  # deferred: table seat

    conditions = [
        FilmNarration.project_id == project_id,
        FilmNarration.content_hash == content_hash,
    ]
    if owner_token is not None:
        # The failure path's double condition: only OUR still-synthesizing
        # placeholder is deletable — never someone's done row, never a
        # takeover's fresh placeholder.
        conditions += [
            FilmNarration.owner_token == owner_token,
            FilmNarration.status == "synthesizing",
        ]
    async with _store_session() as session:
        await session.execute(delete(FilmNarration).where(*conditions))
        await session.commit()
