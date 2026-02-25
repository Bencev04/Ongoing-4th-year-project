"""
Token management operations for Auth Service.

Encapsulates all JWT creation / validation logic and **async** database
operations for refresh-token tracking and access-token blacklisting.

The token blacklist is backed by Redis for sub-millisecond lookups on
every authenticated request, with Postgres as a durable fallback.

Security notes
--------------
* Access tokens are **stateless** JWTs with a short TTL (default 30 min).
* Refresh tokens are **opaque** random strings whose SHA-256 hash is
  stored in the ``refresh_tokens`` table.  The raw value is only ever
  held in memory or sent to the client.
* On logout the refresh token row is soft-revoked and, optionally,
  the access token's ``jti`` is written to both Redis and ``token_blacklist``.
* ``cleanup_expired_tokens`` should be called periodically (e.g. via
  a cron job or startup task) to prune stale rows.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.auth import RefreshToken, TokenBlacklist
from ..schemas.auth import TokenPayload

import sys
sys.path.append("../../shared")
from common.config import settings
from common.redis import get_redis

logger = logging.getLogger(__name__)


# ==============================================================================
# Constants
# ==============================================================================

ACCESS_TOKEN_EXPIRE_MINUTES: int = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
ALGORITHM: str = settings.algorithm
SECRET_KEY: str = settings.secret_key

_BLACKLIST_PREFIX: str = "bl:"


# ==============================================================================
# Token Creation  (CPU-only — no I/O, stays synchronous)
# ==============================================================================

def create_access_token(
    user_id: int,
    email: str,
    role: str,
    owner_id: Optional[int] = None,
    company_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    acting_as: Optional[int] = None,
    impersonator_id: Optional[int] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, str, datetime]:
    """
    Create a signed JWT access token.

    The token embeds tenant context so downstream services can
    enforce multi-tenancy without a database lookup.  Optional
    impersonation claims (``acting_as``, ``impersonator_id``) are
    included only when a superadmin creates a shadow token.

    Args:
        user_id:         Authenticated user’s primary key.
        email:           User email embedded in the token.
        role:            User role string (superadmin / owner / admin /
                         manager / employee / viewer).
        owner_id:        Tenant identifier (business-owner user ID).
                         ``None`` for superadmins.
        company_id:      Company identifier for tenant metadata.
        organization_id: Platform-level organization ID.
        acting_as:       When impersonating, the effective owner_id.
                         Omitted from JWT when ``None``.
        impersonator_id: The superadmin’s real user ID during
                         impersonation.  Omitted when ``None``.
        expires_delta:   Custom lifetime; falls back to config default.

    Returns:
        Tuple of ``(encoded_jwt, jti, expiry_datetime)``.
    """
    jti: str = uuid.uuid4().hex
    now: datetime = datetime.now(timezone.utc)
    expire: datetime = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: dict = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "owner_id": owner_id,
        "company_id": company_id,
        "organization_id": organization_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "token_type": "access",
    }

    # --- Impersonation claims (only when actively impersonating) ---
    if acting_as is not None:
        payload["acting_as"] = acting_as
    if impersonator_id is not None:
        payload["impersonator_id"] = impersonator_id

    encoded_jwt: str = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, jti, expire


def create_refresh_token() -> str:
    """
    Generate a cryptographically random refresh token string.

    The raw value is returned to the caller (and ultimately to the
    client).  Only a SHA-256 hash of this value is persisted.

    Returns:
        A URL-safe random string of 64 characters.
    """
    return secrets.token_urlsafe(48)


# ---- Impersonation shadow token -----------------------------------------

IMPERSONATION_TOKEN_EXPIRE_MINUTES: int = 15
"""Shadow tokens have a deliberately short lifetime (15 min)."""


def create_impersonation_token(
    target_user_id: int,
    target_email: str,
    target_role: str,
    target_owner_id: Optional[int],
    target_company_id: Optional[int],
    target_organization_id: Optional[int],
    impersonator_id: int,
) -> tuple[str, str, datetime]:
    """
    Create a *shadow* access token for superadmin impersonation.

    The resulting JWT looks like a normal access token for the
    **target** user but carries two extra claims:

    - ``acting_as``       — the target user’s ``owner_id`` so
      downstream services apply the correct tenant scope.
    - ``impersonator_id`` — the superadmin’s real user ID so
      the audit trail can attribute the action.

    The token lifetime is intentionally short
    (``IMPERSONATION_TOKEN_EXPIRE_MINUTES``).

    Args:
        target_user_id:         ID of the user being impersonated.
        target_email:           Email of the target user.
        target_role:            Role of the target user.
        target_owner_id:        Tenant owner_id of the target user.
        target_company_id:      Company of the target user.
        target_organization_id: Organization of the target user.
        impersonator_id:        The superadmin’s own user ID.

    Returns:
        Tuple of ``(encoded_jwt, jti, expiry_datetime)``.

    Security:
        This function does **not** verify that the caller is a
        superadmin — that check must happen in the route handler.
    """
    return create_access_token(
        user_id=target_user_id,
        email=target_email,
        role=target_role,
        owner_id=target_owner_id,
        company_id=target_company_id,
        organization_id=target_organization_id,
        acting_as=target_owner_id,
        impersonator_id=impersonator_id,
        expires_delta=timedelta(minutes=IMPERSONATION_TOKEN_EXPIRE_MINUTES),
    )


# ==============================================================================
# Token Hashing / Decoding  (CPU-only)
# ==============================================================================

def hash_token(token: str) -> str:
    """
    Compute the SHA-256 hex digest of a token value.

    Args:
        token: Raw token string.

    Returns:
        64-character lowercase hex digest.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> Optional[TokenPayload]:
    """
    Decode and validate a JWT access token.

    Args:
        token: The encoded JWT string.

    Returns:
        A ``TokenPayload`` if the token is valid and not expired,
        or ``None`` if validation fails for any reason.
    """
    try:
        payload: dict = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(**payload)
    except (JWTError, KeyError, ValueError):
        return None


# ==============================================================================
# Refresh Token Persistence  (async)
# ==============================================================================

async def store_refresh_token(
    db: AsyncSession,
    user_id: int,
    owner_id: int,
    raw_token: str,
    device_info: Optional[str] = None,
    ip_address: Optional[str] = None,
    expires_days: int = REFRESH_TOKEN_EXPIRE_DAYS,
) -> RefreshToken:
    """
    Persist a new refresh token (hashed) in the database.

    Args:
        db:           Async database session.
        user_id:      User the token belongs to.
        owner_id:     Tenant / owner ID for multi-tenant filtering.
        raw_token:    The plain-text token (will be hashed before storage).
        device_info:  Optional user-agent or device name.
        ip_address:   Optional client IP address.
        expires_days: Number of days until the token expires.

    Returns:
        The newly created ``RefreshToken`` row.
    """
    token_hash: str = hash_token(raw_token)
    expires_at: datetime = datetime.now(timezone.utc) + timedelta(days=expires_days)

    db_token = RefreshToken(
        user_id=user_id,
        owner_id=owner_id,
        token_hash=token_hash,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )

    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)

    return db_token


async def verify_refresh_token(
    db: AsyncSession,
    raw_token: str,
) -> Optional[RefreshToken]:
    """
    Look up a refresh token by its hash and validate it.

    Args:
        db:        Async database session.
        raw_token: The plain-text refresh token from the client.

    Returns:
        The ``RefreshToken`` row if valid, or ``None`` if the token
        is unknown, revoked, or expired.
    """
    token_hash: str = hash_token(raw_token)

    result = await db.execute(
        select(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    db_token: Optional[RefreshToken] = result.scalar_one_or_none()

    if db_token is None:
        return None

    # Check expiry
    if db_token.is_expired:
        db_token.is_revoked = True
        await db.commit()
        return None

    return db_token


# ==============================================================================
# Revocation  (async)
# ==============================================================================

async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> bool:
    """
    Revoke a single refresh token (logout one session).

    Args:
        db:        Async database session.
        raw_token: The plain-text refresh token.

    Returns:
        ``True`` if a matching active token was found and revoked.
    """
    token_hash: str = hash_token(raw_token)

    result = await db.execute(
        select(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    db_token: Optional[RefreshToken] = result.scalar_one_or_none()

    if db_token is None:
        return False

    db_token.is_revoked = True
    await db.commit()
    return True


async def revoke_all_user_tokens(db: AsyncSession, user_id: int) -> int:
    """
    Revoke every active refresh token for a user (logout everywhere).

    Args:
        db:      Async database session.
        user_id: The user whose tokens should be revoked.

    Returns:
        The number of tokens that were revoked.
    """
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
        .values(is_revoked=True)
    )
    await db.commit()
    return result.rowcount  # type: ignore[return-value]


# ==============================================================================
# Access Token Blacklist  (Redis-first, Postgres fallback)
# ==============================================================================

async def blacklist_access_token(
    db: AsyncSession,
    jti: str,
    user_id: int,
    expires_at: datetime,
) -> None:
    """
    Add an access token's JTI to both Redis (fast lookups) and
    Postgres (durable persistence).

    Args:
        db:         Async database session.
        jti:        The JWT ID claim.
        user_id:    The user who owned the token.
        expires_at: When the JWT would have naturally expired.
    """
    # ---- Redis (sub-millisecond lookups) ----
    now = datetime.now(timezone.utc)
    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    ttl_seconds: int = int((exp - now).total_seconds())
    if ttl_seconds > 0:
        try:
            r = await get_redis()
            await r.setex(f"{_BLACKLIST_PREFIX}{jti}", ttl_seconds, "1")
        except Exception:
            logger.warning("Failed to write JTI %s to Redis blacklist", jti)

    # ---- Postgres (durable source of truth) ----
    entry = TokenBlacklist(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at,
    )
    db.add(entry)
    await db.commit()


async def is_token_blacklisted(
    jti: str,
    db: Optional[AsyncSession] = None,
) -> bool:
    """
    Check whether an access token's JTI has been blacklisted.

    Checks Redis first for speed (~0.1 ms); falls back to Postgres
    if Redis is unavailable.

    Args:
        jti: The JWT ID claim to look up.
        db:  Optional async database session for the Postgres fallback.

    Returns:
        ``True`` if the JTI exists in the blacklist.
    """
    # ---- Redis fast path ----
    try:
        r = await get_redis()
        if await r.exists(f"{_BLACKLIST_PREFIX}{jti}"):
            return True
    except Exception:
        logger.debug("Redis unavailable for blacklist check, falling back to DB")

    # ---- Postgres fallback ----
    if db is not None:
        result = await db.execute(
            select(TokenBlacklist).filter(TokenBlacklist.jti == jti)
        )
        return result.scalar_one_or_none() is not None

    return False


# ==============================================================================
# Maintenance  (async)
# ==============================================================================

async def cleanup_expired_tokens(db: AsyncSession) -> dict[str, int]:
    """
    Delete expired refresh tokens and blacklist entries.

    Should be called periodically to keep the tables compact.
    Redis entries auto-expire via TTL so no cleanup is needed there.

    Args:
        db: Async database session.

    Returns:
        Dictionary with counts of deleted rows per table.
    """
    now: datetime = datetime.now(timezone.utc)

    refresh_result = await db.execute(
        delete(RefreshToken)
        .where(RefreshToken.expires_at < now)
        .execution_options(synchronize_session=False)
    )
    blacklist_result = await db.execute(
        delete(TokenBlacklist)
        .where(TokenBlacklist.expires_at < now)
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    return {
        "refresh_tokens_deleted": refresh_result.rowcount,  # type: ignore[dict-item]
        "blacklist_entries_deleted": blacklist_result.rowcount,  # type: ignore[dict-item]
    }
