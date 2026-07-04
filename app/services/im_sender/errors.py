from __future__ import annotations


class SendMessageError(Exception):
    def __init__(self, chat_id: str, error_code: int, error_message: str) -> None:
        self.chat_id = chat_id
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(chat_id, error_code, error_message)

    def __str__(self) -> str:
        return (
            f"飞书消息发送失败: chat_id={self.chat_id} "
            f"code={self.error_code} msg={self.error_message}"
        )
