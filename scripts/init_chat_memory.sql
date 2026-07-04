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
    userid text NOT NULL,
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
COMMENT ON COLUMN public.chat_memory.userid IS '用户标识，当前一期使用飞书 sender_id';
COMMENT ON COLUMN public.chat_memory.chat_id IS '会话标识';
COMMENT ON COLUMN public.chat_memory.message_id IS '消息标识，用于去重';
COMMENT ON COLUMN public.chat_memory."type" IS '消息方向，0 表示用户消息，1 表示助手消息';
COMMENT ON COLUMN public.chat_memory.im_type IS 'IM 平台类型，一期固定为 feishu';
COMMENT ON COLUMN public.chat_memory.message_time IS '消息时间，带时区时间';
COMMENT ON COLUMN public.chat_memory.content_type IS '内容类型，一期固定为 text';
COMMENT ON COLUMN public.chat_memory.content IS '消息内容，JSONB 结构，当前为 {"text": "..."}';
COMMENT ON COLUMN public.chat_memory.content_vector IS '内容向量，维度固定为 384';

-- 3. 用户时间联合索引，用于按用户时间线读取消息。
CREATE INDEX IF NOT EXISTS idx_chat_memory_userid_message_time
ON public.chat_memory (userid, message_time);

-- 4. 去重索引，避免同一平台同一消息方向重复落库。
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_memory_im_type_message_id_type
ON public.chat_memory (im_type, message_id, "type");

-- 5. 向量 HNSW 索引，用于后续语义检索。
CREATE INDEX IF NOT EXISTS idx_chat_memory_content_vector_hnsw
ON public.chat_memory
USING hnsw (content_vector vector_cosine_ops);
