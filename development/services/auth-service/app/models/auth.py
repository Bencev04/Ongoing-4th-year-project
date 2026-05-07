"""
Authentication database models.

Defines SQLAlchemy ORM models for refresh tokens and blacklisted
tokens. Access tokens are stateless JWTs; refresh tokens are tracked
in the database so they can be revoked per-user or per-device.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from common.database import Base


class RefreshToken(Base):
    """
    Persisted refresh token.

    Each row represents an active refresh token that was issued to
    a specific user on a specific device.  Storing them in the DB
    allows per-session revocation and "logout everywhere" support.

    Attributes:
        id:          Primary key.
        user_id:     The user this token belongs to.
        owner_id:    Tenant (business owner) the user belongs to.
                     Stored redundantly for fast tenant-scoped queries.
        token_hash:  SHA-256 hash of the actual token value.
                     We never store the raw token.
        device_info: Optional user-agent / device identifier.
        ip_address:  IP the token was issued from.
        expires_at:  Absolute expiry timestamp.
        is_revoked:  Soft-revocation flag.
        created_at:  When the token was issued.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,  # supports IPv6
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<RefreshToken(id={self.id}, user_id={self.user_id}, "
            f"revoked={self.is_revoked})>"
        )

    @property
    def is_expired(self) -> bool:
        """Return True when the token has passed its expiry time."""
        now = datetime.now(UTC)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return now > exp


class TokenBlacklist(Base):
    """
    Blacklisted access-token JTI (JWT ID).

    When a user logs out we cannot truly invalidate a stateless JWT,
    but we *can* record its ``jti`` claim here and reject it on
    subsequent requests until natural expiry.

    Attributes:
        id:          Primary key.
        jti:         The unique JWT ID from the token's ``jti`` claim.
        user_id:     The user whose token was blacklisted.
        expires_at:  When the original JWT would have expired.
                     Used to prune old rows automatically.
        created_at:  When the blacklist entry was created.
    """

    __tablename__ = "token_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    jti: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TokenBlacklist(id={self.id}, jti='{self.jti}')>"
