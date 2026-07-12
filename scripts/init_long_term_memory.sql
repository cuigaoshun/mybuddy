-- 长期记忆初始化脚本
-- 使用方式：先手动连接目标 PostgreSQL 数据库，再执行本文件。

-- 1. 创建用户级长期记忆表。
-- 说明：
-- - 长期记忆按 user_id + im_type 维度维护，不挂在 chat_session_info 上。
-- - long_term_memory_summary 保存可直接注入上下文的长期记忆摘要。
-- - user_profile_json 保存结构化用户属性，当前建议包含 profile / preferences / relationship 三个顶层对象。
-- - last_processed_message_id 用于后续增量整理游标。
CREATE TABLE IF NOT EXISTS public.user_memory (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id text NOT NULL,
    im_type text NOT NULL,
    long_term_memory_summary text NULL,
    user_profile_json jsonb NOT NULL DEFAULT '{"profile": {}, "preferences": {}, "relationship": {}}'::jsonb,
    last_processed_message_id text NULL,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_user_memory_user_profile_json_object
        CHECK (jsonb_typeof(user_profile_json) = 'object')
);

-- 字段注释。
COMMENT ON COLUMN public.user_memory.id IS '主键，自增标识';
COMMENT ON COLUMN public.user_memory.user_id IS '用户标识，当前一期使用飞书 sender_id';
COMMENT ON COLUMN public.user_memory.im_type IS 'IM 平台类型，一期固定为 feishu';
COMMENT ON COLUMN public.user_memory.long_term_memory_summary IS '供上下文注入使用的长期记忆摘要';
COMMENT ON COLUMN public.user_memory.user_profile_json IS '结构化用户属性，当前建议包含 profile/preferences/relationship';
COMMENT ON COLUMN public.user_memory.last_processed_message_id IS '最近一次已进入长期记忆整理流程的消息游标';
COMMENT ON COLUMN public.user_memory.version IS '长期记忆版本号，用于后续合并或幂等控制';
COMMENT ON COLUMN public.user_memory.created_at IS '记录创建时间';
COMMENT ON COLUMN public.user_memory.updated_at IS '记录最近更新时间';

-- 2. 用户维度唯一索引，保证一个平台用户只有一份长期记忆快照。
CREATE UNIQUE INDEX IF NOT EXISTS uidx_user_memory_user_id_im_type
ON public.user_memory (user_id, im_type);

-- 3. 更新时间索引，用于后续整理、回扫或状态巡检。
CREATE INDEX IF NOT EXISTS idx_user_memory_updated_at
ON public.user_memory (updated_at);

-- 4. 游标索引，用于后续增量扫描定位未整理用户。
CREATE INDEX IF NOT EXISTS idx_user_memory_last_processed_message_id
ON public.user_memory (last_processed_message_id);
