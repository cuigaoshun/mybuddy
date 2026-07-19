-- 数据库初始化脚本
-- 使用方式：先手动连接目标 PostgreSQL 数据库，再执行本文件。

-- 1. 启用 pgvector 扩展，用于存储内容向量。
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 创建系统用户主表。
CREATE TABLE IF NOT EXISTS public.users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.users IS '系统用户主表';
COMMENT ON COLUMN public.users.id IS '数据库内部自增主键';
COMMENT ON COLUMN public.users.user_id IS '系统统一用户标识，使用 UUID v7';
COMMENT ON COLUMN public.users.created_at IS '创建时间';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_users_user_id
ON public.users (user_id);

-- 3. 创建第三方身份映射表。
CREATE TABLE IF NOT EXISTS public.user_external_identities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL,
    im_type text NOT NULL,
    third_party_user_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.user_external_identities IS '第三方身份到系统用户ID的映射表';
COMMENT ON COLUMN public.user_external_identities.id IS '数据库内部自增主键';
COMMENT ON COLUMN public.user_external_identities.user_id IS '系统统一用户标识';
COMMENT ON COLUMN public.user_external_identities.im_type IS '第三方平台类型，例如 feishu';
COMMENT ON COLUMN public.user_external_identities.third_party_user_id IS '第三方平台用户ID，例如飞书 open_id';
COMMENT ON COLUMN public.user_external_identities.created_at IS '创建时间';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_user_external_identities_im_type_third_party_user_id
ON public.user_external_identities (im_type, third_party_user_id);

CREATE INDEX IF NOT EXISTS idx_user_external_identities_user_id
ON public.user_external_identities (user_id);

-- 4. 创建对话记忆表。
-- 说明：
-- - message_time 使用 TIMESTAMPTZ，统一存带时区时间。
-- - content_type 当前一期只存 text。
-- - content 使用 JSONB，当前内容结构为 {"text": "..."}。
CREATE TABLE IF NOT EXISTS public.chat_memory (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL,
    chat_id text NOT NULL,
    message_id text NOT NULL,
    "type" smallint NOT NULL,
    im_type text NOT NULL,
    message_time timestamptz NOT NULL,
    content_type text NOT NULL,
    content jsonb NOT NULL,
    content_vector vector(768) NOT NULL
);

COMMENT ON TABLE public.chat_memory IS '对话记忆表，保存用户消息与助手消息的原始记录及向量';
COMMENT ON COLUMN public.chat_memory.id IS '主键，自增标识';
COMMENT ON COLUMN public.chat_memory.user_id IS '系统统一用户标识，值来自第三方身份映射';
COMMENT ON COLUMN public.chat_memory.chat_id IS '会话标识';
COMMENT ON COLUMN public.chat_memory.message_id IS '消息标识，用于去重';
COMMENT ON COLUMN public.chat_memory."type" IS '消息方向，0 表示用户消息，1 表示助手消息';
COMMENT ON COLUMN public.chat_memory.im_type IS 'IM 平台类型，一期固定为 feishu';
COMMENT ON COLUMN public.chat_memory.message_time IS '消息时间，带时区时间';
COMMENT ON COLUMN public.chat_memory.content_type IS '内容类型，一期固定为 text';
COMMENT ON COLUMN public.chat_memory.content IS '消息内容，JSONB 结构，当前为 {"text": "..."}';
COMMENT ON COLUMN public.chat_memory.content_vector IS '内容向量，维度固定为 768';

CREATE INDEX IF NOT EXISTS idx_chat_memory_user_id_im_type_message_time
ON public.chat_memory (user_id, im_type, message_time);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_memory_im_type_message_id_type
ON public.chat_memory (im_type, message_id, "type");

CREATE INDEX IF NOT EXISTS idx_chat_memory_content_vector_hnsw
ON public.chat_memory
USING hnsw (content_vector vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_chat_memory_content_text_fts
ON public.chat_memory
USING gin (to_tsvector('simple', coalesce(content->>'text', '')));

-- 5. 创建会话信息表。
CREATE TABLE IF NOT EXISTS public.chat_session_info (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL,
    first_reply_time timestamptz NULL,
    latest_reply_time timestamptz NULL,
    reply_lease_owner text NULL,
    reply_lease_until timestamptz NULL
);

COMMENT ON TABLE public.chat_session_info IS '会话信息表，维护 user_id 维度的回复状态与租约';
COMMENT ON COLUMN public.chat_session_info.id IS '主键，自增标识';
COMMENT ON COLUMN public.chat_session_info.user_id IS '系统统一用户标识，值来自第三方身份映射';
COMMENT ON COLUMN public.chat_session_info.first_reply_time IS '该会话第一次被成功回复覆盖的用户消息时间';
COMMENT ON COLUMN public.chat_session_info.latest_reply_time IS '该会话最近一次被成功回复覆盖的用户消息时间';
COMMENT ON COLUMN public.chat_session_info.reply_lease_owner IS '当前回复租约持有者';
COMMENT ON COLUMN public.chat_session_info.reply_lease_until IS '当前回复租约过期时间';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_chat_session_info_user_id
ON public.chat_session_info (user_id);

-- 6. 创建用户级长期记忆表。
-- 说明：
-- - 长期记忆按 user_id + im_type 维度维护，不挂在 chat_session_info 上。
-- - long_term_memory_summary 保存可直接注入上下文的长期记忆摘要。
-- - user_profile_json 保存结构化用户属性，当前建议包含 profile / preferences / relationship 三个顶层对象。
-- - last_processed_record_id 保存最近一次已处理 chat_memory 主键，用于精确增量整理游标。
CREATE TABLE IF NOT EXISTS public.user_memory (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL,
    long_term_memory_summary text NULL,
    user_profile_json jsonb NOT NULL DEFAULT '{"profile": {}, "preferences": {}, "relationship": {}}'::jsonb,
    last_processed_record_id bigint NULL,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_user_memory_user_profile_json_object
        CHECK (jsonb_typeof(user_profile_json) = 'object')
);

COMMENT ON TABLE public.user_memory IS '用户级长期记忆表，保存长期摘要、画像和整理游标';
COMMENT ON COLUMN public.user_memory.id IS '主键，自增标识';
COMMENT ON COLUMN public.user_memory.user_id IS '系统统一用户标识，值来自第三方身份映射';
COMMENT ON COLUMN public.user_memory.long_term_memory_summary IS '供上下文注入使用的长期记忆摘要';
COMMENT ON COLUMN public.user_memory.user_profile_json IS '结构化用户属性，当前建议包含 profile/preferences/relationship';
COMMENT ON COLUMN public.user_memory.last_processed_record_id IS '最近一次已进入长期记忆整理流程的 chat_memory 主键游标';
COMMENT ON COLUMN public.user_memory.version IS '长期记忆版本号，用于后续合并或幂等控制';
COMMENT ON COLUMN public.user_memory.created_at IS '记录创建时间';
COMMENT ON COLUMN public.user_memory.updated_at IS '记录最近更新时间';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_user_memory_user_id
ON public.user_memory (user_id);

CREATE INDEX IF NOT EXISTS idx_user_memory_updated_at
ON public.user_memory (updated_at);

CREATE INDEX IF NOT EXISTS idx_user_memory_last_processed_record_id
ON public.user_memory (last_processed_record_id);

-- 7. 创建微信账号运行态表。
-- 一期约束：一个微信 bot 账号只对应一个微信用户聊天对端。
CREATE TABLE IF NOT EXISTS public.wechat_account (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NULL,
    bot_account_id text NULL,
    third_party_user_id text NULL,
    qrcode text NOT NULL,
    qrcode_status text NOT NULL,
    bot_token text NULL,
    get_updates_buf text NULL,
    context_token text NULL,
    typing_ticket text NULL,
    source_message_id text NULL,
    is_active boolean NOT NULL DEFAULT true,
    logged_in_at timestamptz NULL,
    qrcode_updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.wechat_account IS '微信账号运行表，一期约束下同时保存扫码登录状态、bot 账号状态、长轮询游标和唯一聊天对端上下文';
COMMENT ON COLUMN public.wechat_account.id IS '主键，自增标识';
COMMENT ON COLUMN public.wechat_account.user_id IS '系统内部用户 ID；可在扫码发起时指定，也可在扫码成功后自动生成并回填';
COMMENT ON COLUMN public.wechat_account.bot_account_id IS '微信 bot 账号 ID，对应协议中的 ilink_bot_id';
COMMENT ON COLUMN public.wechat_account.third_party_user_id IS '当前唯一聊天对端的微信用户 ID，例如 ...@im.wechat';
COMMENT ON COLUMN public.wechat_account.qrcode IS '扫码登录轮询 token，用于查询二维码登录状态';
COMMENT ON COLUMN public.wechat_account.qrcode_status IS '当前二维码状态，例如 wait、scaned、confirmed、expired';
COMMENT ON COLUMN public.wechat_account.bot_token IS '扫码成功后得到的当前有效 bot_token';
COMMENT ON COLUMN public.wechat_account.get_updates_buf IS '当前 bot 账号最近一次持久化的长轮询游标';
COMMENT ON COLUMN public.wechat_account.context_token IS '当前唯一聊天对端最近一次可用的回复上下文令牌';
COMMENT ON COLUMN public.wechat_account.typing_ticket IS '当前唯一聊天对端最近一次可用的 typing ticket';
COMMENT ON COLUMN public.wechat_account.source_message_id IS '最近一次刷新 context_token 的来源消息 ID';
COMMENT ON COLUMN public.wechat_account.is_active IS '该微信账号当前是否生效';
COMMENT ON COLUMN public.wechat_account.logged_in_at IS '本次扫码确认成功时间';
COMMENT ON COLUMN public.wechat_account.qrcode_updated_at IS '最近一次生成或刷新二维码时间';
COMMENT ON COLUMN public.wechat_account.created_at IS '记录创建时间';
COMMENT ON COLUMN public.wechat_account.updated_at IS '记录最近更新时间';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_wechat_account_qrcode
ON public.wechat_account (qrcode);

CREATE UNIQUE INDEX IF NOT EXISTS uidx_wechat_account_bot_account_id
ON public.wechat_account (bot_account_id)
WHERE bot_account_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uidx_wechat_account_user_id
ON public.wechat_account (user_id)
WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uidx_wechat_account_third_party_user_id
ON public.wechat_account (third_party_user_id)
WHERE third_party_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_wechat_account_is_active
ON public.wechat_account (is_active);

CREATE INDEX IF NOT EXISTS idx_wechat_account_qrcode_status
ON public.wechat_account (qrcode_status);

CREATE INDEX IF NOT EXISTS idx_wechat_account_updated_at
ON public.wechat_account (updated_at);
