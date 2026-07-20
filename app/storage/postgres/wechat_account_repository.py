from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Identity, Index, MetaData, Table, Text, Uuid, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from app.storage.models import WeChatAccount
from app.storage.repositories import WeChatAccountRepository

WECHAT_ACCOUNT_SCHEMA = "public"


class PostgresWeChatAccountRepository(WeChatAccountRepository):
    """基于 PostgreSQL 的微信账号运行态仓储。"""

    def __init__(self, engine: Engine) -> None:
        # 复用现有 PG 仓储模式，在初始化时声明整张表的 SQLAlchemy 映射。
        self._engine = engine
        self._metadata = MetaData(schema=WECHAT_ACCOUNT_SCHEMA)
        self._table = Table(
            "wechat_account",
            self._metadata,
            Column("id", BigInteger, Identity(always=True), primary_key=True),
            Column("user_id", Uuid(as_uuid=False), nullable=True),
            Column("bot_account_id", Text, nullable=True),
            Column("third_party_user_id", Text, nullable=True),
            Column("qrcode", Text, nullable=False),
            Column("qrcode_status", Text, nullable=False),
            Column("bot_token", Text, nullable=True),
            Column("get_updates_buf", Text, nullable=True),
            Column("context_token", Text, nullable=True),
            Column("typing_ticket", Text, nullable=True),
            Column("source_message_id", Text, nullable=True),
            Column("is_active", Boolean, nullable=False),
            Column("logged_in_at", DateTime(timezone=True), nullable=True),
            Column("qrcode_updated_at", DateTime(timezone=True), nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            Index("uidx_wechat_account_qrcode", "qrcode", unique=True),
        )

    def get_by_qrcode(self, qrcode: str) -> WeChatAccount | None:
        # 扫码轮询阶段主要靠 qrcode 查询当前记录。
        return self._select_one(self._table.c.qrcode == qrcode)

    def get_by_user_id(self, user_id: str) -> WeChatAccount | None:
        return self._select_one(self._table.c.user_id == user_id)

    def get_by_bot_account_id(self, bot_account_id: str) -> WeChatAccount | None:
        return self._select_one(self._table.c.bot_account_id == bot_account_id)

    def mark_session_expired(self, bot_account_id: str) -> WeChatAccount | None:
        now = datetime.now(UTC)
        # 会话过期后，主动清空所有依赖当前登录态的运行时字段。
        statement = (
            update(self._table)
            .where(self._table.c.bot_account_id == bot_account_id)
            .values(
                bot_token=None,
                get_updates_buf=None,
                context_token=None,
                typing_ticket=None,
                source_message_id=None,
                is_active=False,
                updated_at=now,
            )
            .returning(*self._table.c)
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return _to_model(row)

    def create_pending_login(self, qrcode: str, qrcode_status: str, user_id: str | None) -> WeChatAccount:
        now = datetime.now(UTC)
        # 扫码发起时先落一条待确认登录记录，后续再回填正式账号信息。
        statement = insert(self._table).values(
            user_id=user_id,
            qrcode=qrcode,
            qrcode_status=qrcode_status,
            is_active=True,
            qrcode_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        statement = statement.returning(*self._table.c)
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return _to_model(row)

    def refresh_pending_login(self, user_id: str, qrcode: str, qrcode_status: str) -> WeChatAccount:
        now = datetime.now(UTC)
        statement = (
            update(self._table)
            .where(self._table.c.user_id == user_id)
            .values(
                qrcode=qrcode,
                qrcode_status=qrcode_status,
                bot_account_id=None,
                third_party_user_id=None,
                bot_token=None,
                context_token=None,
                typing_ticket=None,
                source_message_id=None,
                logged_in_at=None,
                is_active=True,
                qrcode_updated_at=now,
                updated_at=now,
            )
            .returning(*self._table.c)
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return _to_model(row)

    def complete_login(
        self,
        qrcode: str,
        user_id: str,
        bot_account_id: str,
        bot_token: str,
        qrcode_status: str,
    ) -> WeChatAccount | None:
        now = datetime.now(UTC)
        # 扫码确认成功后，在同一条记录里回填 bot 正式凭证。
        statement = (
            update(self._table)
            .where(self._table.c.qrcode == qrcode)
            .values(
                user_id=user_id,
                bot_account_id=bot_account_id,
                bot_token=bot_token,
                qrcode_status=qrcode_status,
                logged_in_at=now,
                updated_at=now,
            )
            .returning(*self._table.c)
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return _to_model(row)

    def update_qrcode_status(self, qrcode: str, qrcode_status: str) -> WeChatAccount | None:
        now = datetime.now(UTC)
        # 未确认前只允许变更二维码状态和刷新时间。
        statement = (
            update(self._table)
            .where(self._table.c.qrcode == qrcode)
            .values(qrcode_status=qrcode_status, qrcode_updated_at=now, updated_at=now)
            .returning(*self._table.c)
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return _to_model(row)

    def update_runtime(
        self,
        bot_account_id: str,
        *,
        third_party_user_id: str | None,
        get_updates_buf: str | None,
        context_token: str | None,
        source_message_id: str | None,
        typing_ticket: str | None = None,
    ) -> WeChatAccount | None:
        now = datetime.now(UTC)
        # 只更新本次调用明确给出的字段，避免把已有缓存误清空。
        values: dict[str, object] = {"updated_at": now}
        if third_party_user_id is not None:
            values["third_party_user_id"] = third_party_user_id
        if get_updates_buf is not None:
            values["get_updates_buf"] = get_updates_buf
        if context_token is not None:
            values["context_token"] = context_token
            # 上下文 token 变化后，旧的 typing ticket 不再可靠，下一次由 sender 重新获取。
            values["typing_ticket"] = None
        if source_message_id is not None:
            values["source_message_id"] = source_message_id
        if typing_ticket is not None:
            values["typing_ticket"] = typing_ticket
        statement = (
            update(self._table)
            .where(self._table.c.bot_account_id == bot_account_id)
            .values(**values)
            .returning(*self._table.c)
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return _to_model(row)

    def list_active_accounts(self) -> list[WeChatAccount]:
        # 只有已经登录成功且仍处于激活状态的账号才会被 runner 拉起。
        statement = (
            select(*self._table.c)
            .where(
                self._table.c.is_active.is_(True),
                self._table.c.bot_account_id.is_not(None),
                self._table.c.bot_token.is_not(None),
            )
            .order_by(self._table.c.updated_at, self._table.c.id)
        )
        with self._engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        return [_to_model(row) for row in rows]

    def _select_one(self, *conditions) -> WeChatAccount | None:
        statement = select(*self._table.c).where(*conditions).limit(1)
        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return _to_model(row)


def _to_model(row) -> WeChatAccount:
    # 统一把数据库行映射回领域模型，避免调用层依赖原始 Row 结构。
    return WeChatAccount(
        user_id=row["user_id"],
        bot_account_id=row["bot_account_id"],
        third_party_user_id=row["third_party_user_id"],
        qrcode=row["qrcode"],
        qrcode_status=row["qrcode_status"],
        bot_token=row["bot_token"],
        get_updates_buf=row["get_updates_buf"],
        context_token=row["context_token"],
        typing_ticket=row["typing_ticket"],
        source_message_id=row["source_message_id"],
        is_active=row["is_active"],
        logged_in_at=row["logged_in_at"],
        qrcode_updated_at=row["qrcode_updated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
