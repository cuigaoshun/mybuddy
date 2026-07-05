-- chat_memory 初始化脚本
-- 使用方式：先手动连接目标 PostgreSQL 数据库，再执行本文件。

-- 1. 启用 pgvector 扩展，用于存储内容向量。
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 创建对话记忆表。
-- 说明：
-- - message_time 使用 TIMESTAMPTZ，统一存带时区时间。
-- - content_type 当前一期只存 text。
-- - content 使用 JSONB，当前内容结构为 {"text": "..."}。
CREATE TABLE IF NOT EXISTS public.chat_memory (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id text NOT NULL,
    chat_id text NOT NULL,
    message_id text NOT NULL,
    "type" smallint NOT NULL,
    im_type text NOT NULL,
    message_time timestamptz NOT NULL,
    content_type text NOT NULL,
    content jsonb NOT NULL,
    content_vector vector(384) NOT NULL
);

-- 字段注释。
COMMENT ON COLUMN public.chat_memory.id IS '主键，自增标识';
COMMENT ON COLUMN public.chat_memory.user_id IS '用户标识，当前一期使用飞书 sender_id';
COMMENT ON COLUMN public.chat_memory.chat_id IS '会话标识';
COMMENT ON COLUMN public.chat_memory.message_id IS '消息标识，用于去重';
COMMENT ON COLUMN public.chat_memory."type" IS '消息方向，0 表示用户消息，1 表示助手消息';
COMMENT ON COLUMN public.chat_memory.im_type IS 'IM 平台类型，一期固定为 feishu';
COMMENT ON COLUMN public.chat_memory.message_time IS '消息时间，带时区时间';
COMMENT ON COLUMN public.chat_memory.content_type IS '内容类型，一期固定为 text';
COMMENT ON COLUMN public.chat_memory.content IS '消息内容，JSONB 结构，当前为 {"text": "..."}';
COMMENT ON COLUMN public.chat_memory.content_vector IS '内容向量，维度固定为 384';

-- 3. 用户平台时间联合索引，用于按用户最近时间线读取消息。
CREATE INDEX IF NOT EXISTS idx_chat_memory_user_id_im_type_message_time
ON public.chat_memory (user_id, im_type, message_time);

-- 4. 去重索引，避免同一平台同一消息方向重复落库。
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_memory_im_type_message_id_type
ON public.chat_memory (im_type, message_id, "type");

-- 5. 向量 HNSW 索引，用于后续语义检索。
CREATE INDEX IF NOT EXISTS idx_chat_memory_content_vector_hnsw
ON public.chat_memory
USING hnsw (content_vector vector_cosine_ops);

-- 6. content.text 全文检索 GIN 索引，用于历史消息关键词检索。
CREATE INDEX IF NOT EXISTS idx_chat_memory_content_text_fts
ON public.chat_memory
USING gin (to_tsvector('simple', coalesce(content->>'text', '')));

-- 7. 创建会话信息表，当前用于维护 user_id + im_type + chat_id 维度的最新回复时间。
CREATE TABLE IF NOT EXISTS public.chat_session_info (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id text NOT NULL,
    im_type text NOT NULL,
    chat_id text NOT NULL,
    first_reply_time timestamptz NULL,
    latest_reply_time timestamptz NULL,
    reply_lease_owner text NULL,
    reply_lease_until timestamptz NULL
);

COMMENT ON COLUMN public.chat_session_info.id IS '主键，自增标识';
COMMENT ON COLUMN public.chat_session_info.user_id IS '用户标识，当前一期使用飞书 sender_id';
COMMENT ON COLUMN public.chat_session_info.im_type IS 'IM 平台类型，一期固定为 feishu';
COMMENT ON COLUMN public.chat_session_info.chat_id IS '会话标识';
COMMENT ON COLUMN public.chat_session_info.first_reply_time IS '该会话第一次被成功回复覆盖的用户消息时间';
COMMENT ON COLUMN public.chat_session_info.latest_reply_time IS '该会话最近一次被成功回复覆盖的用户消息时间';
COMMENT ON COLUMN public.chat_session_info.reply_lease_owner IS '当前回复租约持有者';
COMMENT ON COLUMN public.chat_session_info.reply_lease_until IS '当前回复租约过期时间';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_chat_session_info_user_id_im_type_chat_id
ON public.chat_session_info (user_id, im_type, chat_id);
