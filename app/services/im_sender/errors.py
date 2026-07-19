from __future__ import annotations


class SendMessageError(Exception):
    def __init__(self, chat_id: str, error_code: int, error_message: str, im_type: str = "unknown") -> None:
        self.chat_id = chat_id
        self.error_code = error_code
        self.error_message = error_message
        self.im_type = im_type
        super().__init__(chat_id, error_code, error_message, im_type)

    def __str__(self) -> str:
        return (
            f"消息发送失败: im_type={self.im_type} chat_id={self.chat_id} "
            f"code={self.error_code} msg={self.error_message}"
        )
