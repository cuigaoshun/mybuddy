from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, MetaData, Table, Text, Uuid, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from app.memory.models import ExternalUserIdentity
from app.memory.repositories import UserIdentityRepository
from app.util import generate_uuid7

USER_IDENTITY_SCHEMA = "public"


class PostgresUserIdentityRepository(UserIdentityRepository):
    """基于 PostgreSQL 的第三方身份映射仓储。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._metadata = MetaData(schema=USER_IDENTITY_SCHEMA)
        # users 保存系统内部统一 user_id，本仓储只依赖最小字段集合。
        self._users_table = Table(
            "users",
            self._metadata,
            Column("id", BigInteger, Identity(always=True), primary_key=True),
            Column("user_id", Uuid(as_uuid=False), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Index("uidx_users_user_id", "user_id", unique=True),
        )
        # 身份映射表按 (im_type, third_party_user_id) 唯一定位系统 user_id。
        self._identities_table = Table(
            "user_external_identities",
            self._metadata,
            Column("id", BigInteger, Identity(always=True), primary_key=True),
            Column("user_id", Uuid(as_uuid=False), nullable=False),
            Column("im_type", Text, nullable=False),
            Column("third_party_user_id", Text, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Index(
                "uidx_user_external_identities_im_type_third_party_user_id",
                "im_type",
                "third_party_user_id",
                unique=True,
            ),
            Index("idx_user_external_identities_user_id", "user_id"),
        )

    def get_by_external_identity(self, im_type: str, third_party_user_id: str) -> ExternalUserIdentity | None:
        # 读取已有映射，供只读查询场景复用。
        statement = (
            select(
                self._identities_table.c.user_id,
                self._identities_table.c.im_type,
                self._identities_table.c.third_party_user_id,
                self._identities_table.c.created_at,
            )
            .where(
                self._identities_table.c.im_type == im_type,
                self._identities_table.c.third_party_user_id == third_party_user_id,
            )
            .limit(1)
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return ExternalUserIdentity(
            user_id=row["user_id"],
            im_type=row["im_type"],
            third_party_user_id=row["third_party_user_id"],
            created_at=row["created_at"],
        )

    def get_or_create_user_id(self, im_type: str, third_party_user_id: str) -> str:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            # 同一个第三方身份在单事务内串行化，避免并发首登时生成多个 user_id。
            connection.execute(
                select(func.pg_advisory_xact_lock(func.hashtext(_build_lock_key(im_type, third_party_user_id))))
            )
            existing_identity = connection.execute(
                select(self._identities_table.c.user_id)
                .where(
                    self._identities_table.c.im_type == im_type,
                    self._identities_table.c.third_party_user_id == third_party_user_id,
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing_identity is not None:
                return existing_identity

            # 只有映射不存在时才创建新的系统 user_id，并立即写入映射表。
            user_id = str(generate_uuid7())
            connection.execute(
                insert(self._users_table).values(
                    user_id=user_id,
                    created_at=now,
                )
            )
            connection.execute(
                insert(self._identities_table).values(
                    user_id=user_id,
                    im_type=im_type,
                    third_party_user_id=third_party_user_id,
                    created_at=now,
                )
            )
            return user_id


def _build_lock_key(im_type: str, third_party_user_id: str) -> str:
    return f"{im_type}:{third_party_user_id}"
