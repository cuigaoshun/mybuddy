from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, Identity, Integer, MetaData, Table, Text, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine

from app.memory.models import UserMemory, UserMemoryAffinity, UserMemoryAttribute, UserMemoryAttributes, UserMemoryProfile, UserMemoryRelationship
from app.memory.repositories import UserMemoryRepository

USER_MEMORY_SCHEMA = "public"


class PostgresUserMemoryRepository(UserMemoryRepository):
    """基于 SQLAlchemy 的 user_memory PostgreSQL 仓储实现。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._metadata = MetaData(schema=USER_MEMORY_SCHEMA)
        self._table = Table(
            "user_memory",
            self._metadata,
            Column("id", BigInteger, Identity(always=True), primary_key=True),
            Column("user_id", Uuid(as_uuid=False), nullable=False),
            Column("im_type", Text, nullable=False),
            Column("long_term_memory_summary", Text, nullable=True),
            Column("user_profile_json", JSONB, nullable=False),
            Column("last_processed_message_id", Text, nullable=True),
            Column("version", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

    def get_by_user(self, user_id: str, im_type: str) -> UserMemory | None:
        statement = (
            select(
                self._table.c.user_id,
                self._table.c.im_type,
                self._table.c.long_term_memory_summary,
                self._table.c.user_profile_json,
                self._table.c.last_processed_message_id,
                self._table.c.version,
                self._table.c.created_at,
                self._table.c.updated_at,
            )
            .where(
                self._table.c.user_id == user_id,
                self._table.c.im_type == im_type,
            )
            .limit(1)
        )

        with self._engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return UserMemory(
            user_id=row["user_id"],
            im_type=row["im_type"],
            long_term_memory_summary=row["long_term_memory_summary"],
            user_profile=_parse_user_memory_profile(dict(row["user_profile_json"] or {})),
            last_processed_message_id=row["last_processed_message_id"],
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save(self, user_memory: UserMemory) -> None:
        statement = insert(self._table).values(
            user_id=user_memory.user_id,
            im_type=user_memory.im_type,
            long_term_memory_summary=user_memory.long_term_memory_summary,
            user_profile_json=user_memory.user_profile.to_dict(),
            last_processed_message_id=user_memory.last_processed_message_id,
            version=user_memory.version,
            created_at=user_memory.created_at,
            updated_at=user_memory.updated_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["user_id", "im_type"],
            set_={
                "long_term_memory_summary": user_memory.long_term_memory_summary,
                "user_profile_json": user_memory.user_profile.to_dict(),
                "last_processed_message_id": user_memory.last_processed_message_id,
                "version": user_memory.version,
                "updated_at": user_memory.updated_at,
            },
        )

        with self._engine.begin() as connection:
            connection.execute(statement)


def _parse_user_memory_profile(payload: dict[str, object]) -> UserMemoryProfile:
    return UserMemoryProfile(
        profile=_parse_user_memory_attributes(payload.get("profile")),
        preferences=_parse_user_memory_attributes(payload.get("preferences")),
        relationship=_parse_user_memory_relationship(payload.get("relationship")),
    )


def _parse_user_memory_attributes(raw_value: object) -> UserMemoryAttributes:
    if not isinstance(raw_value, dict):
        return UserMemoryAttributes()
    items: list[UserMemoryAttribute] = []
    for key, value in raw_value.items():
        normalized_value = _normalize_attribute_value(value)
        if normalized_value is None:
            continue
        items.append(UserMemoryAttribute(key=key, value=normalized_value))
    return UserMemoryAttributes(items=tuple(items))


def _parse_user_memory_relationship(raw_value: object) -> UserMemoryRelationship:
    if not isinstance(raw_value, dict):
        return UserMemoryRelationship()
    affinity_value = raw_value.get("affinity")
    if not isinstance(affinity_value, dict):
        return UserMemoryRelationship()
    return UserMemoryRelationship(
        affinity=UserMemoryAffinity(
            level=_normalize_int(affinity_value.get("level")),
            confidence=_normalize_float(affinity_value.get("confidence")),
            updated_at=_normalize_optional_datetime(affinity_value.get("updated_at")),
            notes=_normalize_string(affinity_value.get("notes")),
        )
    )


def _normalize_attribute_value(value: object) -> str | bool | int | float | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        normalized_value = value.strip()
        return normalized_value or None
    return None


def _normalize_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip()
    return normalized_value or None


def _normalize_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normalize_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _normalize_optional_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    try:
        parsed_value = datetime.fromisoformat(normalized_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value.astimezone(UTC)
