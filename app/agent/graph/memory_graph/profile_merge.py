from __future__ import annotations

from app.agent.graph.memory_graph.state import UserMemoryAffinityPatch, UserProfilePatch, build_now
from app.memory.models import UserMemoryAffinity, UserMemoryAttribute, UserMemoryAttributes, UserMemoryProfile, UserMemoryRelationship


def merge_user_profile_patch(
    existing_profile: UserMemoryProfile,
    patch: UserProfilePatch,
) -> UserMemoryProfile:
    """把用户画像 patch 按确定性规则合并回完整画像。"""

    merged_profile_values = _merge_attribute_patch(
        base_values=existing_profile.profile.to_dict(),
        patch_values=patch.profile,
    )
    merged_preference_values = _merge_attribute_patch(
        base_values=existing_profile.preferences.to_dict(),
        patch_values=patch.preferences,
    )
    merged_affinity = _merge_affinity_patch(
        existing_affinity=existing_profile.relationship.affinity,
        affinity_patch=patch.relationship.affinity if patch.relationship is not None else None,
    )
    return UserMemoryProfile(
        profile=_build_user_memory_attributes(merged_profile_values),
        preferences=_build_user_memory_attributes(merged_preference_values),
        relationship=UserMemoryRelationship(affinity=merged_affinity),
    )


def _merge_attribute_patch(
    base_values: dict[str, str | bool | int | float],
    patch_values: dict[str, str | bool | int | float | None] | None,
) -> dict[str, str | bool | int | float]:
    merged_values = dict(base_values)
    if patch_values is None:
        return merged_values
    for key, value in patch_values.items():
        normalized_key = key.strip()
        if not normalized_key:
            continue
        if value is None:
            merged_values.pop(normalized_key, None)
            continue
        merged_values[normalized_key] = value
    return merged_values


def _build_user_memory_attributes(
    values: dict[str, str | bool | int | float],
) -> UserMemoryAttributes:
    items = tuple(
        UserMemoryAttribute(key=key, value=value)
        for key, value in sorted(values.items())
    )
    return UserMemoryAttributes(items=items)


def _merge_affinity_patch(
    existing_affinity: UserMemoryAffinity | None,
    affinity_patch: UserMemoryAffinityPatch | None,
) -> UserMemoryAffinity | None:
    if affinity_patch is None:
        return existing_affinity
    level = existing_affinity.level if existing_affinity is not None else None
    confidence = existing_affinity.confidence if existing_affinity is not None else None
    notes = existing_affinity.notes if existing_affinity is not None else None
    updated_at = existing_affinity.updated_at if existing_affinity is not None else None
    if affinity_patch.level is not None:
        level = affinity_patch.level
        updated_at = build_now()
    if affinity_patch.confidence is not None:
        confidence = affinity_patch.confidence
        updated_at = build_now()
    if affinity_patch.notes is not None:
        notes = affinity_patch.notes.strip() or None
        updated_at = build_now()
    if level is None and confidence is None and notes is None:
        return None
    return UserMemoryAffinity(
        level=level,
        confidence=confidence,
        updated_at=updated_at,
        notes=notes,
    )
