"""Layer 1B infra contracts: user profile, session revocation, passwordless auth, publish mail."""

from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import settings
from app.dependencies.auth import _get_user_from_token
from app.models.tables import LoginSession, User, now_utc
from app.platform import notifications
from app.platform.auth import create_access_token, create_verification_code, session_claims
from app.platform.routes import (
    ProfileUpdate,
    UserSettingsUpdate,
    VerifyCodeRequest,
    get_settings,
    list_sessions,
    logout,
    put_settings,
    revoke_session,
    save_profile,
    verify_code_endpoint,
)

pytestmark = pytest.mark.asyncio


async def test_profile_and_partial_settings_preserve_other_values(database):
    async with database() as db:
        user = User(
            email="prefs@example.test", settings={"unrelated": "keep", "confirm_execution": "ask"}
        )
        db.add(user)
        await db.commit()
        initial = await get_settings(db, user)
        assert initial.locale is None and not initial.publish_alerts
        await put_settings(UserSettingsUpdate(theme="dark"), db, user)
        updated = await put_settings(UserSettingsUpdate(locale="zh"), db, user)
        assert (updated.theme, updated.locale, updated.confirm_execution) == ("dark", "zh", "ask")
        assert user.settings["unrelated"] == "keep"
        assert (await save_profile(ProfileUpdate(name="  Studio  "), db, user)).name == "Studio"


async def test_revoked_session_stays_revoked_and_legacy_token_adopts_once(database):
    async with database() as db:
        owner, other = User(email="owner@example.test"), User(email="other@example.test")
        db.add_all([owner, other])
        await db.commit()
        legacy = create_access_token(owner.id)
        legacy_id = session_claims(legacy)[1]
        assert await _get_user_from_token(db, legacy, "Mobile Safari") == owner
        fresh_id = uuid4()
        fresh = create_access_token(owner.id, fresh_id)
        assert await _get_user_from_token(db, fresh, "") is None
        db.add(
            LoginSession(
                id=fresh_id,
                user_id=owner.id,
                user_agent="Firefox",
                expires_at=session_claims(fresh)[2],
            )
        )
        await db.commit()
        req = Request(
            {"type": "http", "headers": [(b"authorization", ("Bearer " + fresh).encode())]}
        )
        devices = await list_sessions(req, db, owner)
        assert {d.id for d in devices} == {fresh_id, legacy_id}
        assert [d.id for d in devices if d.current] == [fresh_id]
        with pytest.raises(HTTPException) as exc:
            await revoke_session(legacy_id, db, other)
        assert exc.value.status_code == 404
        await revoke_session(legacy_id, db, owner)
        assert await _get_user_from_token(db, legacy, "") is None
        assert await _get_user_from_token(db, fresh, "") == owner


async def test_passwordless_login_creates_device_and_logout_revokes_it(database):
    email = "signed-in@example.test"
    async with database() as db:
        code = await create_verification_code(db, email)
        req = Request({"type": "http", "headers": [(b"user-agent", b"Test Browser")]})
        response = await verify_code_endpoint(
            VerifyCodeRequest(email=email, code=code.code), req, db
        )
        claims = session_claims(response.token)
        assert claims and not claims[3]
        authenticated = await _get_user_from_token(db, response.token, "Test Browser")
        assert str(authenticated.id) == response.user.id
        signed_in = Request(
            {
                "type": "http",
                "headers": [
                    (b"authorization", f"Bearer {response.token}".encode()),
                ],
            }
        )
        await logout(signed_in, db, authenticated)
        assert await _get_user_from_token(db, response.token, "Test Browser") is None


async def test_publish_mail_only_after_opt_in_retries_same_event_and_honors_opt_out(
    database, monkeypatch
):
    requests = []

    def provider(req):
        requests.append(req)
        return httpx.Response(503 if len(requests) == 1 else 200)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        notifications.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(provider), **kw),
    )
    monkeypatch.setattr(settings, "resend_api_key", "test")
    async with database() as db:
        user = User(email="owner@example.test")
        db.add(user)
        await db.commit()

        async def event(kind):
            row = await notifications.create_notification(
                db, user_id=user.id, type=kind, payload={}
            )
            await db.commit()
            return row

        assert (await event("publish_failed")).email_due_at is None
        user.settings = {"publish_alerts": True, "locale": "zh"}
        await db.commit()
        assert (await event("publish_succeeded")).email_due_at is None
        row = await event("channel_expired")
        assert await notifications.deliver_due_alert(db)
        assert row.email_attempts == 1 and row.email_due_at > now_utc()
        row.email_due_at = now_utc() - timedelta(seconds=1)
        await db.commit()
        assert await notifications.deliver_due_alert(db)
        assert row.email_due_at is None
        assert requests[0].headers["Idempotency-Key"] == requests[1].headers["Idempotency-Key"]
        assert requests[0].content == requests[1].content
        await event("publish_unknown")
        user.settings = {"publish_alerts": False}
        await db.commit()
        assert await notifications.deliver_due_alert(db)
        assert not await notifications.deliver_due_alert(db)
        assert len(requests) == 2
