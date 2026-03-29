-- ============================================================
-- Supabase schema для Email Agent CRM
-- Запустить в Supabase Dashboard → SQL Editor
-- ============================================================

-- Основная CRM — лиды
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT DEFAULT '',
    company TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    telegram_username TEXT DEFAULT '',
    whatsapp_number TEXT DEFAULT '',
    stage TEXT DEFAULT 'NEW_REPLY',
    source_channel TEXT DEFAULT 'email',   -- email | telegram | telegram_mtproto | whatsapp | avito
    traffic_source TEXT DEFAULT 'unknown', -- cold_email | inbound_email | avito_listing | referral | ...
    assigned_role TEXT DEFAULT 'sales_manager',  -- sales_manager | recruiter | consultant | support_agent
    lead_score INTEGER DEFAULT 0,          -- 0-100, обновляется автоматически
    niche TEXT DEFAULT '',
    follow_up_count INTEGER DEFAULT 0,
    last_contacted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Путь лида (каждое значимое событие)
CREATE TABLE IF NOT EXISTS journey_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_email TEXT NOT NULL,
    event_type TEXT NOT NULL,   -- stage_change | message_sent | message_received | handoff | follow_up
    from_stage TEXT DEFAULT '',
    to_stage TEXT DEFAULT '',
    channel TEXT NOT NULL,       -- email | telegram | telegram_mtproto | whatsapp | avito
    role_used TEXT DEFAULT '',
    message_preview TEXT DEFAULT '',  -- первые 200 символов
    classification TEXT DEFAULT '',   -- INTERESTED | NOT_INTERESTED | READY_TO_ORDER | ...
    confidence FLOAT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Полный лог всех сообщений
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_email TEXT NOT NULL,
    channel TEXT NOT NULL,
    direction TEXT NOT NULL,    -- inbound | outbound
    message_text TEXT DEFAULT '',
    classification TEXT DEFAULT '',
    confidence FLOAT DEFAULT 0,
    role_used TEXT DEFAULT '',
    stage_at_time TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы для быстрых запросов
CREATE INDEX IF NOT EXISTS idx_journey_events_lead_email ON journey_events(lead_email);
CREATE INDEX IF NOT EXISTS idx_journey_events_created_at ON journey_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_lead_email ON conversations(lead_email);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_leads_source_channel ON leads(source_channel);
CREATE INDEX IF NOT EXISTS idx_leads_lead_score ON leads(lead_score DESC);

-- Автообновление updated_at для таблицы leads
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

-- Row Level Security (опционально — включить если нужна защита)
-- ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE journey_events ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- Полезные представления для дашборда менеджера
CREATE OR REPLACE VIEW funnel_summary AS
SELECT
    stage,
    source_channel,
    assigned_role,
    COUNT(*) as count,
    ROUND(AVG(lead_score), 1) as avg_score
FROM leads
GROUP BY stage, source_channel, assigned_role
ORDER BY count DESC;

CREATE OR REPLACE VIEW hot_leads AS
SELECT
    email, name, company, stage, source_channel,
    assigned_role, lead_score, last_contacted_at, updated_at
FROM leads
WHERE lead_score >= 60
  AND stage NOT IN ('HANDOFF_TO_MANAGER', 'ORDER', 'NOT_INTERESTED', 'ARCHIVED')
ORDER BY lead_score DESC, updated_at DESC;

CREATE OR REPLACE VIEW recent_activity AS
SELECT
    je.lead_email,
    l.name,
    je.event_type,
    je.from_stage,
    je.to_stage,
    je.channel,
    je.role_used,
    je.classification,
    je.message_preview,
    je.created_at
FROM journey_events je
LEFT JOIN leads l ON l.email = je.lead_email
ORDER BY je.created_at DESC
LIMIT 100;
