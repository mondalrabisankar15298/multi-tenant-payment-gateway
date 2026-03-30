<div align="center">

# ⚡ Multi-Tenant Event-Driven Payment Gateway

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=22&pause=1000&color=6366F1&center=true&vCenter=true&width=600&lines=CQRS+%2B+Transactional+Outbox+Pattern;Schema-Per-Tenant+Isolation;Kafka+Event+Streaming;Automated+E2E+Smoke+Testing;Production-Grade+Microservices" alt="Typing SVG" />

<br />

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Redpanda](https://img.shields.io/badge/Redpanda-Kafka--Compatible-E50695?style=for-the-badge&logo=apachekafka&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Celery](https://img.shields.io/badge/Celery-Workers-37814A?style=for-the-badge&logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<br/>

> A **production-grade multi-tenant B2B payment gateway** — built from scratch to demonstrate enterprise-level backend engineering.
> Designed with **CQRS**, **Transactional Outbox**, **Schema-per-Tenant isolation**, **real-time Kafka event streaming**,
> **HMAC-signed webhooks**, and a **self-monitoring E2E health system**.

<br/>

[🚀 Quick Start](#-quick-start) · [🏗 Architecture](#-architecture) · [📦 Services](#-services--ports) · [🖥 Platform Monitor](#-platform-monitor) · [🧪 Testing](#-testing) · [📮 Postman](#-postman-collection)

</div>

---

## 🧩 Why This Project?

Most "payment gateway" projects are CRUD APIs. This one is different.

This platform replicates real-world patterns used by companies like **Stripe**, **Razorpay**, and **Adyen** — without integrating with actual banks. The goal is to showcase how **enterprise backend engineering** works at scale:

| 🏆 Pattern | ✅ How It's Done Here |
|---|---|
| **CQRS** | System 1 is the write side. System 3 is a completely separate read projection. No shared DB. |
| **Transactional Outbox** | Domain events are written in the same database transaction as the business record. Zero event loss, ever. |
| **Event Streaming** | All inter-system communication flows through Redpanda (Kafka-compatible). No direct service calls. |
| **Multi-Tenancy** | PostgreSQL schema-per-merchant. Complete data isolation. `merchant_1.*`, `merchant_2.*`, etc. |
| **Idempotent Consumers** | `processed_events` table + `ON CONFLICT` upserts prevent phantom duplicates on replay. |
| **Webhook Delivery** | HMAC-SHA256 signed HTTP callbacks. Exponential backoff. Dead Letter Queue with manual retry. |
| **Pre-Aggregated Analytics** | Read DB has `daily_revenue` and `payment_method_stats` — pre-built for dashboards, not queries. |
| **Self-Monitoring** | A dedicated Platform Monitor runs automated E2E smoke tests and persists health history in Redis. |
| **React Error Boundaries** | Frontends degrade gracefully — no blank screens on JS crashes. |
| **Request Cancellation** | API client uses `AbortSignal` to cancel in-flight fetch requests on component unmount. |

---

## 🏗 Architecture

### High-Level System Design

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                          WRITE SIDE  (System 1)                             ║
║                                                                              ║
║   ┌─────────────────┐   HTTP    ┌──────────────────────────────┐            ║
║   │  Admin Portal   │ ────────► │  Payment Core Service        │  Port 8001 ║
║   │  React UI       │           │  FastAPI (Write API)         │            ║
║   │  Port 5173      │           └──────────────┬───────────────┘            ║
║   └─────────────────┘                          │  SAME TRANSACTION          ║
║                                                ▼                            ║
║                              ┌─────────────────────────────────┐            ║
║                              │  Core DB  (PostgreSQL)  :5433   │            ║
║                              │  ├─ public.merchants             │            ║
║                              │  ├─ public.domain_events         │ ← OUTBOX  ║
║                              │  ├─ merchant_1.payments          │            ║
║                              │  ├─ merchant_1.customers         │            ║
║                              │  ├─ merchant_1.refunds           │            ║
║                              │  └─ merchant_1.ledger_entries    │            ║
║                              └───────────────┬─────────────────┘            ║
╚══════════════════════════════════════════════│═════════════════════════════╝
                                               │ Celery Beat polls every 2s
                                               ▼
                               ┌───────────────────────────────┐
                               │     Redis  (Port 6379)        │
                               │     Celery Broker + Backend   │
                               └───────────────────────────────┘
                                               │
                                               ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                         EVENT BUS  (Redpanda)                               ║
║                                                                              ║
║              Topic: payments.events  │  Partition Key: merchant_id          ║
║              Guarantees in-order processing per tenant                      ║
║              Console UI at http://localhost:8080                            ║
╚═══════════════════════════╦════════════════════╦════════════════════════════╝
                            │                    │
            Consumer Group 1│                    │Consumer Group 2
                            ▼                    ▼
            ┌────────────────────┐    ┌─────────────────────────┐
            │  DB Sync Consumer  │    │  Webhook Consumer        │
            │  Transform+Upsert  │    │  HMAC Sign + HTTP POST  │
            └─────────┬──────────┘    └──────────┬──────────────┘
                      │                          │
                      ▼                          ▼
╔═════════════════════╧═══════════╗   ┌─────────────────────────┐
║      READ SIDE  (System 3)      ║   │  Celery Retry Worker     │
║                                 ║   │  Exponential Backoff     │
║  ┌───────────────────────────┐  ║   │  Attempt 1→2→4→8→16→32s │
║  │  Read DB  (PostgreSQL)    │  ║   │  After 6 fails → DLQ    │
║  │  :5434                    │  ║   └─────────────────────────┘
║  │  ├─ public.processed_events│  ║
║  │  ├─ public.webhook_subs    │  ║
║  │  ├─ public.delivery_logs   │  ║
║  │  ├─ public.dead_letter_q   │  ║
║  │  ├─ merchant_1.payments    │  ║
║  │  ├─ merchant_1.customers   │  ║
║  │  ├─ merchant_1.daily_rev   │  ║  ← Pre-aggregated
║  │  └─ merchant_1.method_stats│  ║  ← Pre-aggregated
║  └──────────────┬─────────────┘  ║
╚═════════════════│═════════════════╝
                  │
                  ▼
   ┌──────────────────────────────────┐
   │  Dashboard Service  (Port 8003) │
   │  FastAPI  (Strictly Read-Only)  │
   │         │                        │
   │         ▼                        │
   │  Merchant Dashboard UI (5174)   │
   └──────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════════════╗
║                     OBSERVABILITY  (System 4)                               ║
║                                                                              ║
║   Platform Monitor  (Port 8888)                                             ║
║   ├─ Health checks every 5 minutes (7+ components, latency tracking)        ║
║   ├─ Automated E2E Smoke Test every 1 hour (full payment lifecycle)         ║
║   ├─ Last 50 snapshots persisted in Redis (survive restarts)                ║
║   └─ Interactive dashboard: live view + historical log modal popup          ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

### 💳 Payment State Machine

```
              ┌─────────┐
  POST /pay → │ pending │
              └────┬────┘
                   │  POST /authorize
                   ▼
          ┌────────────────┐
          │  authorized    │
          └────┬───────────┘
               │  POST /capture
               ▼
          ┌──────────┐         ┌──────────────┐
          │ captured │ ──────► │   settled    │
          └──────────┘         └──────────────┘
               │
               ▼  (partial or full)
          ┌──────────────┐    ┌───────────┐    ┌─────────┐
          │  initiated   │ ─► │ processed │ ─► │ settled │
          │  (refund)    │    └───────────┘    └─────────┘
          └──────────────┘
```

---

### 🌐 Dynamic Schema — How Multi-Tenancy Works

When a merchant is created, three things happen **atomically in one database transaction**:

```
POST /api/merchants { "name": "Acme Corp", "email": "acme@example.com" }
          │
          └─► BEGIN;
                  1. INSERT INTO public.merchants → gets merchant_id = 7
                  2. CREATE SCHEMA merchant_7
                  3. CREATE TABLE merchant_7.customers  (...)
                  4. CREATE TABLE merchant_7.payments   (...)
                  5. CREATE TABLE merchant_7.refunds    (...)
                  6. CREATE TABLE merchant_7.ledger_entries (...)
                  7. INSERT INTO public.domain_events  ← Outbox record
              COMMIT;
          │
          └─► Celery picks up domain_events → publishes to Kafka
                  │
                  └─► DB Sync Consumer receives merchant.created.v1
                          └─► Creates merchant_7.* schema in READ DB too
```

Both databases are ready in seconds. The merchant instantly appears in all dropdowns across both UIs.

---

## 🛠 Tech Stack

| Layer | Technology | Version | Why |
|---|---|---|---|
| **Backend Framework** | FastAPI | 0.110 | Async, type-safe, auto-generated OpenAPI docs |
| **Async DB Driver** | asyncpg | latest | Native async PostgreSQL — fastest available |
| **Sync DB Driver** | psycopg2 | latest | Used by Celery tasks (sync context) |
| **Background Jobs** | Celery | 5.x | Outbox poller, webhook retry, async tasks |
| **Task Scheduler** | Celery Beat | — | Schedules outbox polling every 2 seconds |
| **Health Scheduler** | APScheduler | 3.x | Health checks (5m) + E2E tests (1h) |
| **Event Broker** | Redpanda | latest | Kafka-compatible, no ZooKeeper required |
| **Cache / Queue** | Redis | 7 | Celery broker + monitoring history store |
| **Write Database** | PostgreSQL | 16 | Schema-per-tenant, JSONB, transactional outbox |
| **Read Database** | PostgreSQL | 16 | Denormalized, pre-aggregated for fast reads |
| **Frontend** | React + Vite | 18 | Fast HMR, modern build tooling |
| **HTTP Client** | httpx | latest | Async webhook dispatch, timeout control |
| **Metrics** | prometheus-client | latest | Exposes `/metrics` on System 1 |
| **Containerization** | Docker Compose | v2 | One-command full stack orchestration |

---

## 📦 Services & Ports

| # | Container | Port | Role |
|---|---|---|---|
| 1 | `core-db` | **5433** | PostgreSQL — Write database (schema-per-tenant) |
| 2 | `read-db` | **5434** | PostgreSQL — Read database (transformed, aggregated) |
| 3 | `redis` | **6379** | Celery broker + monitoring history |
| 4 | `redpanda` | **19092** | Kafka-compatible event broker |
| 5 | `redpanda-console` | **8080** | Redpanda web UI (topics, consumers, lag) |
| 6 | `topic-init` | — | One-shot: creates `payments.events` topic |
| 7 | `payment-core-service` | **8001** | System 1 — Write API + `/metrics` |
| 8 | `core-celery-worker` | — | Celery Beat — Outbox poller (every 2s) |
| 9 | `connect-service` | **8002** | System 2 — Kafka consumers + Webhook API |
| 10 | `connect-celery-worker` | — | Webhook retry worker (exponential backoff) |
| 11 | `merchant-dashboard-service` | **8003** | System 3 — Read-only analytics API |
| 12 | `admin-portal` | **5173** | React UI — Merchant & payment management |
| 13 | `merchant-dashboard` | **5174** | React UI — Analytics & reporting |
| 14 | `platform-monitor` | **8888** | System 4 — Health dashboard + E2E tests |

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** v24+ with at least **8 GB RAM** allocated
- **Git**

### Step 1 — Clone

```bash
git clone https://github.com/your-username/multi-tenant-payment-gateway.git
cd multi-tenant-payment-gateway
```

### Step 2 — Configure Environment

```bash
cp .env.example .env
# The defaults work out of the box.
# Edit .env only if you need custom ports or passwords.
```

### Step 3 — Launch Everything

```bash
docker compose up --build -d
```

Wait ~30 seconds for all services to initialise. Verify they're healthy:

```bash
docker compose ps
# All containers should show: healthy or running
```

### Step 4 — Access the Platform

| 🌐 Interface | 🔗 URL | 📝 Purpose |
|---|---|---|
| **Admin Portal** | http://localhost:5173 | Create merchants, customers, payments |
| **Merchant Dashboard** | http://localhost:5174 | Analytics, refunds, reporting |
| **Platform Monitor** | http://localhost:8888 | System health + E2E test history |
| **System 1 API Docs** | http://localhost:8001/docs | Payment Core OpenAPI |
| **System 2 API Docs** | http://localhost:8002/docs | Connect Service OpenAPI |
| **System 3 API Docs** | http://localhost:8003/docs | Dashboard Service OpenAPI |
| **Redpanda Console** | http://localhost:8080 | Inspect topics, messages, consumer lag |

### Step 5 — Create Your First Merchant

```bash
curl -X POST http://localhost:8001/api/merchants \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "email": "acme@example.com"}'
```

**Response:**
```json
{
  "merchant_id": 1,
  "name": "Acme Corp",
  "email": "acme@example.com",
  "schema_name": "merchant_1",
  "api_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "active",
  "created_at": "2026-03-30T08:00:00Z"
}
```

> ⚠️ **Save the `api_key`** — it's required for all tenant-scoped API calls.

### Step 6 — Run a Full Payment Lifecycle

```bash
API_KEY="your-api-key-here"
MID=1

# Create Customer
curl -X POST http://localhost:8001/api/$MID/customers \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@doe.com", "phone": "9999999999"}'

# Create Payment
curl -X POST http://localhost:8001/api/$MID/payments \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "amount": 1500.00, "currency": "INR", "method": "upi", "description": "Order #001"}'

# Authorize → Capture
PAYMENT_ID="your-payment-uuid"
curl -X POST http://localhost:8001/api/$MID/payments/$PAYMENT_ID/authorize -H "X-API-Key: $API_KEY"
curl -X POST http://localhost:8001/api/$MID/payments/$PAYMENT_ID/capture  -H "X-API-Key: $API_KEY"

# Check in Read DB (~5 seconds for sync)
curl http://localhost:8003/api/$MID/payments/$PAYMENT_ID -H "X-API-Key: $API_KEY"
```

### Stop / Reset

```bash
# Stop all services (data is preserved in volumes)
docker compose down

# Full reset — removes all data
docker compose down -v
```

---

## 📡 API Reference

> Full OpenAPI docs: http://localhost:8001/docs · http://localhost:8002/docs · http://localhost:8003/docs

### 🔑 Authentication

All tenant-scoped endpoints require:

```http
X-API-Key: <merchant-uuid-api-key>
```

Admin endpoints (`/api/merchants`, `/api/events`) are public.

---

<details>
<summary>📋 <strong>System 1 — Merchants</strong></summary>

| Method | Endpoint | Description | Event Emitted |
|---|---|---|---|
| `POST` | `/api/merchants` | Onboard merchant + create DB schemas | `merchant.created.v1` |
| `GET` | `/api/merchants` | List all merchants | — |
| `GET` | `/api/merchants/{id}` | Get merchant detail | — |
| `PUT` | `/api/merchants/{id}` | Update name / email / status | — |
| `GET` | `/api/events` | View domain_events outbox | — |

</details>

<details>
<summary>👤 <strong>System 1 — Customers</strong></summary>

| Method | Endpoint | Description | Event Emitted |
|---|---|---|---|
| `POST` | `/api/{mid}/customers` | Create customer | `customer.created.v1` |
| `GET` | `/api/{mid}/customers` | List all customers | — |
| `GET` | `/api/{mid}/customers/{id}` | Customer detail | — |
| `PUT` | `/api/{mid}/customers/{id}` | Update customer | `customer.updated.v1` |
| `DELETE` | `/api/{mid}/customers/{id}` | Remove customer | `customer.deleted.v1` |

</details>

<details>
<summary>💳 <strong>System 1 — Payments & Refunds</strong></summary>

| Method | Endpoint | Description | Event Emitted |
|---|---|---|---|
| `POST` | `/api/{mid}/payments` | Create payment (`pending`) | `payment.created.v1` |
| `GET` | `/api/{mid}/payments` | List payments (with filters) | — |
| `GET` | `/api/{mid}/payments/{id}` | Payment detail | — |
| `POST` | `/api/{mid}/payments/{id}/authorize` | Authorize | `payment.authorized.v1` |
| `POST` | `/api/{mid}/payments/{id}/capture` | Capture | `payment.captured.v1` |
| `POST` | `/api/{mid}/payments/{id}/fail` | Mark failed | `payment.failed.v1` |
| `POST` | `/api/{mid}/payments/{id}/refund` | Create refund | `refund.initiated.v1` |
| `POST` | `/api/{mid}/refunds/{id}/process` | Process refund | `refund.processed.v1` |
| `GET` | `/api/{mid}/refunds` | List refunds | — |

**Payment query filters:** `status` · `method` · `from` · `to` · `customer_id` · `min_amount` · `max_amount` · `page` · `limit`

</details>

<details>
<summary>🔔 <strong>System 2 — Webhooks</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/webhooks` | Register a webhook subscription |
| `GET` | `/api/webhooks?merchant_id=` | List subscriptions |
| `GET` | `/api/webhooks/{id}` | Subscription detail |
| `PUT` | `/api/webhooks/{id}` | Update URL or event filter |
| `DELETE` | `/api/webhooks/{id}` | Remove subscription |
| `GET` | `/api/webhooks/{id}/logs` | Delivery attempt logs |
| `GET` | `/api/webhooks/dlq?merchant_id=` | Dead letter queue entries |
| `POST` | `/api/webhooks/dlq/{id}/retry` | Manually retry a DLQ entry |

**Webhook Signature Header:**
```http
X-Webhook-Signature: sha256=<hmac-sha256-hex>
X-Webhook-Event: payment.captured.v1
X-Webhook-Id: <event_uuid>
```

**Retry Schedule:** 1s → 2s → 4s → 8s → 16s → 32s → **DLQ**

</details>

<details>
<summary>📊 <strong>System 3 — Analytics & Read API</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/{mid}/analytics/summary` | Total revenue, count, success rate |
| `GET` | `/api/{mid}/analytics/daily` | Day-by-day revenue (pre-aggregated) |
| `GET` | `/api/{mid}/analytics/methods` | Payment method distribution |
| `GET` | `/api/{mid}/payments` | Filtered payments list |
| `GET` | `/api/{mid}/payments/{id}` | Payment with customer name denormalized |
| `GET` | `/api/{mid}/customers` | Customers with `total_payments`, `total_spent` |
| `GET` | `/api/{mid}/refunds` | Refunds with payment amount denormalized |

</details>

<details>
<summary>🖥 <strong>System 4 — Platform Monitor API</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Latest health snapshot + `e2e_next_run_seconds` |
| `GET` | `/api/history` | Last 50 full snapshots from Redis |
| `POST` | `/api/e2e/run` | Manually trigger E2E smoke test |
| `POST` | `/api/toggle` | Start / stop background monitoring |
| `GET` | `/health` | Monitor liveness check |

</details>

---

## 🖥 Platform Monitor

> **Dashboard:** http://localhost:8888

The Platform Monitor is a fully self-contained observability service with a rich dark-mode dashboard. It runs as its own Docker container and monitors the entire platform from the outside.

### 🔬 What It Monitors

| Component | Check Type |
|---|---|
| Core DB | TCP ping + latency (ms) |
| Read DB | TCP ping + latency (ms) |
| Redis | PING command check |
| Redpanda (Kafka) | Broker connectivity |
| Payment Core Service | HTTP GET `/health` |
| Connect Service | HTTP GET `/health` |
| Dashboard Service | HTTP GET `/health` |
| Outbox Pending Events | Count + oldest age (seconds) |
| Read DB Mirror Sync | Merchant count cross-check |

### 🧪 Automated E2E Smoke Test (every 1 hour)

Every hour, the monitor automatically runs a **complete payment journey** through the real APIs:

```
Step 1  ✅  Create Merchant        → POST /api/merchants
Step 2  ✅  Create Customer        → POST /api/{mid}/customers
Step 3  ✅  Create Payment         → POST /api/{mid}/payments
Step 4  ✅  Full Lifecycle         → authorize → capture
Step 5  ✅  Event Published        → Poll domain_events for 'published' status (up to 24s)
Step 6  ✅  Read-DB Sync           → Poll read-db for record arrival (up to 15s)
Step 7  ✅  Cleanup                → Purge test merchant from BOTH core-db AND read-db
```

> The cleanup step is sync-aware — it polls read-db for replication before deletion to avoid race conditions.

### 📊 Persistent History

- Last **50 full snapshots** stored as JSON in Redis (`monitor:history`)
- Data survives `docker compose restart` — history is never lost
- Click any dot in the history timeline to open a **log popup modal** showing every check result, latency, and E2E step for that exact run

### ⏱ Live Countdowns

The dashboard header shows:
- **Health check in `N`s** — time until the next automated check
- **Next run in `Nm Ns`** — countdown to the next E2E smoke test

---

## 🗃 Event Catalog

Every mutation in System 1 emits a domain event. All 12 event types flow through Kafka and are consumed by System 2.

| Event Type | Trigger | Read DB Effect |
|---|---|---|
| `merchant.created.v1` | Merchant onboarded | Create full schema in read DB |
| `customer.created.v1` | New customer | Insert customer row |
| `customer.updated.v1` | Customer edited | Update row + cascade denormalized fields |
| `customer.deleted.v1` | Customer removed | Delete row |
| `payment.created.v1` | Payment initiated | Insert payment row |
| `payment.authorized.v1` | Payment authorized | Update status |
| `payment.captured.v1` | Payment captured | Update status + recalculate aggregates |
| `payment.failed.v1` | Payment failed | Update status + increment failure count |
| `payment.settled.v1` | Funds settled | Update status |
| `refund.initiated.v1` | Refund requested | Insert refund row + adjust revenue |
| `refund.processed.v1` | Refund processed | Update refund status |
| `refund.failed.v1` | Refund failed | Update status |

### Kafka Message Format

```json
{
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "merchant_id": 1,
  "schema_name": "merchant_1",
  "event_type": "payment.captured.v1",
  "entity_type": "payment",
  "entity_id": "pay_f8e7d6c5-abcd-1234-5678-ef9012345678",
  "payload": {
    "amount": 1500.00,
    "currency": "INR",
    "status": "captured",
    "method": "upi"
  },
  "created_at": "2026-03-30T08:01:30Z"
}
```

---

## 🧪 Testing

The project ships with a full **pytest-based integration and E2E test suite** — no mocking, all real Docker services.

### Run the Tests

```bash
# Make sure all services are up
docker compose up -d

# Run everything
pytest tests/ -v

# Run a specific suite
pytest tests/test_e2e_flow.py -v
```

### Test Suites

| File | What It Tests |
|---|---|
| `tests/test_smoke.py` | Basic reachability — all `/health` endpoints return 200 |
| `tests/test_integration.py` | Individual service API correctness |
| `tests/test_e2e_flow.py` | Full lifecycle: merchant → customer → payment → authorize → capture → refund → sync |

### How `merchant_setup` Works

The `merchant_setup` pytest fixture creates a **real merchant, real schema, and real test data** before every test, then **automatically tears everything down** from both databases after the test completes. No manual cleanup needed. No data bleeds between tests.

```python
@pytest.fixture(scope="function")
async def merchant_setup(client):
    # Before test: POST /api/merchants → full schema created
    merchant = await create_merchant(client)
    yield merchant
    # After test: DROP SCHEMA merchant_N CASCADE in both DBs
    await cleanup_merchant(merchant)
```

---

## 📮 Postman Collection

Import `multi-tenant-payment-gateway.postman_collection.json` directly into Postman.

**Pre-configured collection variables:**

| Variable | Default | Set after... |
|---|---|---|
| `core_base_url` | `http://localhost:8001` | — |
| `connect_base_url` | `http://localhost:8002` | — |
| `dashboard_base_url` | `http://localhost:8003` | — |
| `merchant_id` | `1` | Creating a merchant |
| `api_key` | *(empty)* | Creating a merchant |
| `payment_id` | *(empty)* | Creating a payment |
| `customer_id` | *(empty)* | Creating a customer |
| `refund_id` | *(empty)* | Creating a refund |
| `subscription_id` | `1` | Registering a webhook |

**Collection folders:**
- 🏦 **System 1**: Health · Merchants · Customers · Payments · Refunds · Events Log
- 🔗 **System 2**: Health · Webhook Subscriptions · Delivery Logs · Dead Letter Queue
- 📊 **System 3**: Health · Merchants · Analytics · Payments · Refunds · Customers

---

## 🎯 Design Principles

| # | Principle | Implementation |
|---|---|---|
| 1 | **Single Source of Truth** | System 1 is the only writer. System 3 is a projection — never directly mutated. |
| 2 | **Zero Event Loss** | Business writes and domain events commit atomically in the same PostgreSQL transaction. |
| 3 | **Complete Decoupling** | Systems communicate exclusively via Kafka events. No HTTP service-to-service calls. |
| 4 | **Safe Kafka Replay** | `processed_events` + `ON CONFLICT DO UPDATE` ensures idempotency at the consumer. |
| 5 | **Hard Tenant Isolation** | PostgreSQL schema-per-merchant. Cross-schema queries are architecturally impossible. |
| 6 | **Fault-Tolerant Webhooks** | 6 retries with exponential backoff. Persistent DLQ with manual retry API. |
| 7 | **Proactive Observability** | Automated hourly E2E tests verify every layer end-to-end, not just service ping. |
| 8 | **Graceful Frontend Degradation** | React Error Boundaries + request `AbortSignal` cancellation on component unmount. |

---

## 📁 Project Structure

```
multi-tenant-payment-gateway/
│
├── 📄 docker-compose.yml                        # 14-service orchestration
├── 📄 .env.example                              # Environment variable template
├── 📄 .env                                      # Local config (gitignored)
├── 📄 ARCHITECTURE.md                           # Complete technical reference
├── 📄 pytest.ini                                # asyncio_mode = auto
├── 📄 multi-tenant-payment-gateway.postman_collection.json
│
├── 📁 .github/
│   └── workflows/
│       └── ci.yml                               # GitHub Actions CI/CD pipeline
│
├── 📁 services/
│   │
│   ├── 📁 payment-core-service/                 # ── SYSTEM 1 ──────────────────
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── main.py                          # FastAPI entry + /health + /metrics
│   │       ├── config.py                        # Pydantic Settings
│   │       ├── database.py                      # asyncpg connection pool
│   │       ├── celery_app.py                    # Celery instance + beat schedule
│   │       ├── tasks/
│   │       │   └── outbox_task.py               # Beat task: poll domain_events → Kafka
│   │       ├── routers/
│   │       │   ├── merchants.py
│   │       │   ├── customers.py
│   │       │   ├── payments.py
│   │       │   └── refunds.py
│   │       ├── services/
│   │       │   ├── merchant_service.py           # Schema creation logic
│   │       │   ├── customer_service.py
│   │       │   ├── payment_service.py            # State machine transitions
│   │       │   └── refund_service.py
│   │       ├── models/
│   │       │   └── schemas.py                   # Pydantic request/response models
│   │       └── utils/
│   │           ├── auth.py                      # X-API-Key validation
│   │           ├── event_emitter.py
│   │           ├── logger.py                    # Structured JSON logging
│   │           └── validators.py
│   │
│   ├── 📁 connect-service/                      # ── SYSTEM 2 ──────────────────
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── main.py                          # FastAPI + consumer startup + /health
│   │       ├── config.py
│   │       ├── database.py
│   │       ├── celery_app.py
│   │       ├── consumers/
│   │       │   ├── db_sync_consumer.py           # Consumer Group 1: Transform → Read DB
│   │       │   └── webhook_consumer.py           # Consumer Group 2: HMAC → HTTP delivery
│   │       ├── tasks/
│   │       │   └── webhook_retry_task.py         # Celery: exponential backoff + DLQ
│   │       ├── services/
│   │       │   ├── sync_service.py
│   │       │   ├── schema_manager.py
│   │       │   └── webhook_service.py
│   │       ├── routers/
│   │       │   └── webhooks.py
│   │       └── utils/
│   │           ├── idempotency.py               # processed_events check
│   │           ├── logger.py
│   │           └── validators.py
│   │
│   ├── 📁 merchant-dashboard-service/           # ── SYSTEM 3 ──────────────────
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── main.py                          # FastAPI + /health
│   │       ├── config.py
│   │       ├── database.py
│   │       └── routers/
│   │           ├── payments.py
│   │           ├── refunds.py
│   │           ├── customers.py
│   │           └── analytics.py                 # Pre-aggregated queries
│   │
│   └── 📁 platform-monitor/                     # ── SYSTEM 4 ──────────────────
│       ├── Dockerfile
│       ├── requirements.txt
│       └── src/
│           ├── main.py                          # FastAPI + APScheduler + Redis history
│           ├── checker.py                       # All health checks + E2E smoke test
│           └── static/
│               └── index.html                   # Dark-mode dashboard + history modal
│
├── 📁 frontends/
│   ├── 📁 admin-portal/                         # React (Vite) — Port 5173
│   │   └── src/
│   │       ├── App.jsx                          # Wrapped in <ErrorBoundary>
│   │       ├── contexts/MerchantContext.jsx      # Global merchant state
│   │       ├── pages/
│   │       │   ├── MerchantsPage.jsx
│   │       │   ├── CustomersPage.jsx
│   │       │   ├── PaymentsPage.jsx
│   │       │   ├── RefundsPage.jsx
│   │       │   └── EventsLogPage.jsx
│   │       ├── components/
│   │       │   ├── ErrorBoundary.jsx            # React class error boundary
│   │       │   └── DataTable.jsx
│   │       └── api/client.js                    # fetch + AbortSignal + X-API-Key
│   │
│   └── 📁 merchant-dashboard/                  # React (Vite) — Port 5174
│       └── src/
│           ├── App.jsx                          # Wrapped in <ErrorBoundary>
│           ├── contexts/MerchantContext.jsx
│           ├── pages/
│           │   ├── DashboardPage.jsx
│           │   ├── PaymentsPage.jsx
│           │   ├── RefundsPage.jsx
│           │   └── CustomersPage.jsx
│           ├── components/
│           │   ├── ErrorBoundary.jsx
│           │   └── StatCard.jsx
│           └── api/client.js
│
├── 📁 infra/
│   ├── postgres/
│   │   ├── init-core-db.sql                    # Core DB init (merchants, domain_events)
│   │   └── init-read-db.sql                    # Read DB init (idempotency, webhook tables)
│   └── redpanda/
│       └── topic-init.sh                       # Creates payments.events topic via rpk
│
└── 📁 tests/
    ├── conftest.py                              # Shared fixtures + DB cleanup
    ├── test_smoke.py                            # Basic /health reachability
    ├── test_integration.py                      # Service-level API correctness
    └── test_e2e_flow.py                         # Full payment lifecycle (create→settle→refund→sync)
```

---

## ✅ Verification Checklist

After `docker compose up --build -d`:

- [ ] All 14 containers show `healthy` or `running`
- [ ] `topic-init` exits with `service_completed_successfully`
- [ ] Create a merchant → schema exists in **both** `core-db` and `read-db`
- [ ] Merchant appears in the dropdown on **both** UIs
- [ ] Create customer → visible in System 3 dashboard within ~5 seconds
- [ ] Payment lifecycle: create → authorize → capture → verify in System 3
- [ ] Refund a payment → analytics revenue adjusts accordingly
- [ ] Second merchant → data is **strictly isolated** (not visible to merchant 1)
- [ ] Replay a Kafka message → no duplicate in read DB (`processed_events` idempotency)
- [ ] Register a webhook → fire event → appears in delivery logs
- [ ] Bad webhook URL → 6 retry attempts → lands in Dead Letter Queue
- [ ] DLQ manual retry via `POST /api/webhooks/dlq/{id}/retry` re-dispatches
- [ ] Redpanda Console (port 8080) shows topics, messages, and consumer lag
- [ ] `GET /health` on ports 8001, 8002, 8003 returns `{ "status": "healthy" }`
- [ ] `GET /metrics` on port 8001 returns Prometheus format metrics
- [ ] `pytest tests/` passes — all green
- [ ] Platform Monitor (port 8888) shows all components healthy
- [ ] Click a history dot → modal popup shows full log for that run
- [ ] `docker compose restart platform-monitor` → history dots still present (Redis persistence)

---

<div align="center">

---

**Built with meticulous attention to production engineering patterns.**

⚡ FastAPI &nbsp;·&nbsp; 🐘 PostgreSQL &nbsp;·&nbsp; 🎯 Redpanda &nbsp;·&nbsp; ⚛️ React &nbsp;·&nbsp; 🐳 Docker

📖 See **[ARCHITECTURE.md](./ARCHITECTURE.md)** for the complete technical deep-dive including all schemas, DDL, transformation matrices, and end-to-end flow diagrams.

</div>
