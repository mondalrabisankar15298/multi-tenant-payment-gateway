CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================
-- CORE DB: Public schema (shared across all merchants)
-- =============================================

-- Merchant registry
CREATE TABLE public.merchants (
    merchant_id     SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    schema_name     VARCHAR(100) UNIQUE NOT NULL,
    api_key         UUID,
    status          VARCHAR(20) DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Transactional outbox (domain events)
CREATE TABLE public.domain_events (
    event_id        UUID PRIMARY KEY,
    merchant_id     INT NOT NULL REFERENCES public.merchants(merchant_id),
    schema_name     VARCHAR(100) NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for outbox worker polling
CREATE INDEX idx_domain_events_pending
    ON public.domain_events(status, created_at)
    WHERE status = 'pending';

-- =============================================
-- THIRD-PARTY CONSUMER SYSTEM
-- =============================================

-- Third-party consumer registry
CREATE TABLE public.third_party_consumers (
    consumer_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     VARCHAR(255) NOT NULL,
    description              TEXT,
    client_id                VARCHAR(64) UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    client_secret_hash       VARCHAR(255) NOT NULL,
    scopes                   TEXT[] DEFAULT '{}',
    status                   VARCHAR(20) DEFAULT 'active',
    webhook_url              VARCHAR(500),
    webhook_event_types      TEXT[] DEFAULT '{}',
    webhook_signing_secret   VARCHAR(255),
    rate_limit_requests      INT DEFAULT 1000,
    rate_limit_window_seconds INT DEFAULT 300,
    metadata                 JSONB DEFAULT '{}',
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW(),
    created_by               VARCHAR(100)
);

-- Merchant-to-consumer access mapping
CREATE TABLE public.consumer_merchant_access (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id     UUID NOT NULL REFERENCES public.third_party_consumers(consumer_id) ON DELETE CASCADE,
    merchant_id     INT NOT NULL REFERENCES public.merchants(merchant_id) ON DELETE CASCADE,
    scopes          TEXT[] DEFAULT '{}',
    granted_at      TIMESTAMPTZ DEFAULT NOW(),
    granted_by      VARCHAR(100) NOT NULL,
    UNIQUE(consumer_id, merchant_id)
);

CREATE INDEX idx_cma_consumer ON consumer_merchant_access(consumer_id);
CREATE INDEX idx_cma_merchant ON consumer_merchant_access(merchant_id);

-- Third-party webhook endpoints
CREATE TABLE public.tp_webhook_endpoints (
    endpoint_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id      UUID NOT NULL REFERENCES public.third_party_consumers(consumer_id) ON DELETE CASCADE,
    merchant_id      INT REFERENCES public.merchants(merchant_id),
    url              VARCHAR(500) NOT NULL,
    event_types      TEXT[] NOT NULL,
    signing_secret   VARCHAR(255) NOT NULL,
    status           VARCHAR(20) DEFAULT 'pending_verification',
    metadata         JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tp_wh_consumer ON tp_webhook_endpoints(consumer_id);
CREATE INDEX idx_tp_wh_merchant ON tp_webhook_endpoints(merchant_id);
CREATE INDEX idx_tp_wh_active ON tp_webhook_endpoints(status) WHERE status = 'active';

-- Webhook delivery event log
CREATE TABLE public.tp_webhook_events (
    event_delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id       UUID NOT NULL REFERENCES public.tp_webhook_endpoints(endpoint_id),
    consumer_id       UUID NOT NULL,
    event_id          UUID NOT NULL,
    event_type        VARCHAR(100) NOT NULL,
    merchant_id       INT NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(20) DEFAULT 'pending',
    attempts          INT DEFAULT 0,
    last_status_code  INT,
    last_response     TEXT,
    next_retry_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tp_whe_pending ON tp_webhook_events(status, next_retry_at)
    WHERE status IN ('pending', 'failed');
CREATE INDEX idx_tp_whe_endpoint ON tp_webhook_events(endpoint_id);
CREATE INDEX idx_tp_whe_consumer ON tp_webhook_events(consumer_id);
CREATE INDEX idx_tp_whe_created ON tp_webhook_events(created_at);

-- Dead Letter Queue
CREATE TABLE public.tp_dead_letter_queue (
    dlq_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id      UUID NOT NULL REFERENCES public.tp_webhook_endpoints(endpoint_id),
    consumer_id      UUID NOT NULL,
    event_id         UUID NOT NULL,
    merchant_id      INT NOT NULL,
    payload          JSONB NOT NULL,
    failure_reason   TEXT,
    max_attempts     INT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tp_dlq_consumer ON tp_dead_letter_queue(consumer_id);
CREATE INDEX idx_tp_dlq_created ON tp_dead_letter_queue(created_at);

-- API call audit log
CREATE TABLE public.api_call_audit_log (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consumer_id      UUID NOT NULL,
    merchant_id      INT,
    endpoint         VARCHAR(255) NOT NULL,
    method           VARCHAR(10) NOT NULL,
    status_code      INT,
    response_time_ms INT,
    request_params   JSONB DEFAULT '{}',
    error_message    TEXT,
    called_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_consumer ON api_call_audit_log(consumer_id);
CREATE INDEX idx_audit_called_at ON api_call_audit_log(called_at);
CREATE INDEX idx_audit_consumer_time ON api_call_audit_log(consumer_id, called_at);
CREATE INDEX idx_audit_consumer_endpoint ON api_call_audit_log(consumer_id, endpoint);
