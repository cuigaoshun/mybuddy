from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.storage.reminder_models import ReminderConversationContext, ReminderJob, ReminderSchedule


class ReminderGraphState(BaseModel):
    """提醒图运行态。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    schedule: ReminderSchedule
    job: ReminderJob
    conversation_context: ReminderConversationContext
    final_text: str | None = None


ReminderGraphState.model_rebuild()
