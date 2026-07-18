from __future__ import annotations

import uuid

import uuid6


def generate_uuid7() -> uuid.UUID:
    """生成系统内部使用的 UUID v7。"""

    return uuid6.uuid7()
