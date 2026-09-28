<<<<<<< HEAD
#  Glitch HR AI (VirtualHR)
=======
# 👔 Glitch HR AI (VirtualHR)
>>>>>>> c058bbe (feat(leaves): overhaul leaves workflow, live DB sync, and role-based privacy guardrails)

> **Next-Generation Enterprise Multi-Tenant HR Intelligence Platform with 6-Level RAG Pipeline**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16.2.7-black.svg?style=flat&logo=next.js)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19.2.4-blue.svg?style=flat&logo=react)](https://react.dev)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas%20Cluster-green.svg?style=flat&logo=mongodb)](https://www.mongodb.com)
[![Pinecone](https://img.shields.io/badge/Pinecone-Serverless%20RAG-000000.svg?style=flat&logo=pinecone)](https://www.pinecone.io)
[![Groq](https://img.shields.io/badge/Groq-LPU%20Inference-f55036.svg?style=flat)](https://groq.com)
[![Docker](https://img.shields.io/badge/Docker-Production%20Hardened-2496ED.svg?style=flat&logo=docker)](https://www.docker.com)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg?style=flat)](#)

---

<<<<<<< HEAD
##  Overview
=======
## 🌟 Overview
>>>>>>> c058bbe (feat(leaves): overhaul leaves workflow, live DB sync, and role-based privacy guardrails)

**Glitch HR AI** (internally designated **VirtualHR**) is an enterprise-grade, multi-tenant B2B Human Resources platform. It unifies core HRIS operations—such as employee directory management, attendance tracking, leave applications, and policy administration—with a high-precision **6-Level Retrieval-Augmented Generation (RAG)** pipeline powered by **Pinecone Serverless** and **Groq / Google Gemini** LLMs.

### Key Architectural Pillars
- **Strict Multi-Tenant Isolation**: Complete isolation of users, documents, leave policies, and vector embeddings using scoped tenant IDs (`company_id`).
- **Deterministic 6-Level RAG**: Hybrid search combining dense Pinecone vectors and lexical MongoDB Atlas text search with Reciprocal Rank Fusion (RRF, $k=60$) and dynamic similarity thresholds to eliminate hallucinations.
- **Zero-Codebase Data Architecture**: All operational data, employee PII, attendance logs, and leave balances reside exclusively in encrypted databases (**MongoDB Atlas** & **Pinecone**). No operational data is stored in the Git repository.
- **Atomic Leave State Machine**: Concurrency-safe leave applications with `Idempotency-Key` deduplication, atomic `$expr` balance reservation, and automatic rollback on rejection.
- **Role-Based Workspaces**: Tailored experiences for Employees, HR Managers, and Super Administrators.

---

<<<<<<< HEAD
##  System Architecture
=======
## 🏗️ System Architecture
>>>>>>> c058bbe (feat(leaves): overhaul leaves workflow, live DB sync, and role-based privacy guardrails)

```mermaid
graph TB
    subgraph Client ["Client Tier (Next.js 16 SPA)"]
        UI_Login["Auth (/login, /signup)"]
        UI_Emp["Employee Workspace (/employees)"]
        UI_HR["HR Admin Studio (/hr)"]
        UI_Admin["Super Admin Console (/admin)"]
    end

    subgraph Gateway ["API Gateway & Middleware (FastAPI :9000)"]
        MW_Tracing["RequestTracing (ContextVars)"]
        MW_RateLimit["IP Rate Limiting (Redis / In-Memory)"]
        MW_CORS["Secure CORS Middleware"]
        MW_Security["SecurityHeaders & Double-Submit Anti-CSRF"]
        Router_Auth["routes_auth.py"]
        Router_HR["routes_hr.py"]
        Router_Emp["routes_employee.py"]
        Router_Doc["routes_document_ingest.py"]
        Router_Chat["main.py (/api/chat, /api/chat/stream)"]
    end

    subgraph Processing ["AI & Processing Pipeline"]
        Engine_RAG["rag_chunking.py (Levels 2-3)"]
        Engine_Search["hybrid_search.py (Level 5 RRF)"]
        Engine_Bot["bot.py (Level 6 LLM Grounding)"]
        Engine_Cost["ai_cost_tracker.py (Outbox Pattern)"]
        Engine_Malware["malware_scanner.py (ClamAV)"]
    end

    subgraph Storage ["Database & Vector Store Tier"]
        DB_Mongo[(MongoDB Atlas Cluster\nhrbot Database)]
        DB_Pinecone[(Pinecone Serverless\n1024d multilingual-e5-large)]
        Cache_Redis[(Redis 7 Cache)]
    end

    subgraph Providers ["Inference Engines"]
        LLM_Groq["Groq API (Qwen / Llama 3)"]
        LLM_Google["Google Gemini 1.5/2.0"]
    end

    Client -->|HTTPS / SSE| Gateway
    Gateway --> Processing
    Processing --> Storage
    Engine_Bot --> Providers
    Engine_Search --> DB_Pinecone
    Engine_Search --> DB_Mongo
    Engine_Cost --> DB_Mongo
<<<<<<< HEAD
=======
```

---

## 🧠 The 6-Level RAG Pipeline

| Level | Component | Technology & Strategy |
| :---: | :--- | :--- |
| **Level 1** | **Secure Ingestion & Validation** | Magic byte binary validation (`python-magic`), ClamAV antivirus stream scanning, `pdfplumber` layout-aware extraction, and `python-docx` heading extraction. |
| **Level 2** | **Hierarchy-Aware Chunking** | Unicode NFKC normalization, administrative boilerplate stripping, and structural splitting preserving Markdown headings (`#`, `##`, `###`) and table geometries. |
| **Level 3** | **Parent-Child Decoupling** | **Small-to-Big Retrieval**: 600–800 token parent chunks stored in MongoDB `parent_chunks`; 150–200 token child chunks with 18% token overlap (~35 tokens) vectorized to Pinecone. |
| **Level 4** | **Pinecone Vector Store** | 1024-dimensional embeddings via Pinecone Inference (`multilingual-e5-large`). Asymmetric embeddings (`input_type="passage"` vs `"query"`) with strict tenant namespace isolation (`namespace=company_id`). |
| **Level 5** | **Hybrid Search & RRF** | Parallel execution of Pinecone dense search and MongoDB Atlas lexical search. Fused using **Reciprocal Rank Fusion (RRF, $k=60$)**:<br>$$\text{RRF}(d) = \frac{1}{60 + \text{rank}_{\text{dense}}(d)} + \frac{1}{60 + \text{rank}_{\text{lexical}}(d)}$$<br>Dynamic thresholds: $\ge 0.80$ (High confidence), $0.70 - 0.80$ (Moderate with disclaimer), $< 0.70$ (Zero-hallucination fallback to HR ticket). |
| **Level 6** | **Grounded Generation & Guardrails** | Parent chunk context window compaction (budget: 2,500 tokens), dynamic employee profile injection, and strict algorithmic guardrails preventing privacy leaks of colleague data. |

---

## 💻 Workspaces & Portals

### 1. 👤 Employee Self-Service (`/employees`)
- **Dashboard Overview**: Personalized metrics: remaining leave days, today's attendance, performance ratings, and reporting manager info.
- **Attendance Tab**: Historical punch logs with check-in/out timestamps, hours worked, and work mode chips (Office, WFH, Remote).
- **Leaves Tab**: Interactive leave application form with date validation, remaining balance cards, and live approval status tracker.
- **My Profile Tab**: Complete employee profile, contact numbers, department, verified skills tags, and professional certifications.
- **AI Policy Assistant**: Interactive conversational chat grounded in company policies with suggested quick queries.

### 2. 🏢 HR Management Studio (`/hr`)
- **Executive Analytics**: Real-time employee headcounts, document ingestion progress, and department distribution graphs.
- **Employee Directory**: Searchable, filterable staff roster with individual creation and bulk CSV/XLSX imports.
- **Leave Approval Queue**: Centralized review queue for approving or rejecting leave submissions with manager remarks.
- **Document Manager**: Drag-and-drop policy document ingestion with real-time parsing status and vector sync badges.
- **Workspace Settings**: Passkey generation and regeneration, company name updates, and employee query audit logs.

### 3. 🛡️ Super Administrator Console (`/admin`)
- **Tenant Management**: Provisioning organizations, assigning admin roles, and managing platform telemetry.
- **AI FinOps Registry**: Multi-version model pricing table and transactional outbox dead-letter queue (DLQ) replay.

---

## 📂 Project Structure

```text
HR_ai/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint, middleware, health, chat routes
│   │   ├── config.py                # Environment settings & startup validations
│   │   ├── db.py                    # Motor connection pool & compound index creation
│   │   ├── deps.py                  # Hybrid Auth, CSRF, RBAC, tenant isolation dependencies
│   │   ├── auth.py                  # JWT (HS256), bcrypt password hashing
│   │   ├── passkey_service.py       # Argon2id workspace passkey hashing & verification
│   │   ├── bot.py                   # Multi-provider LLM response generation (Groq / Gemini)
│   │   ├── hybrid_search.py         # Level 5 Hybrid Search (Pinecone + Mongo Lexical + RRF)
│   │   ├── rag_chunking.py          # Levels 2-3 hierarchy & small-to-big chunking
│   │   ├── vector_store.py          # Pinecone Serverless client, batch embeddings, purge
│   │   ├── document_ingest.py       # Level 1 parsing (PDF, DOCX, TXT), ClamAV scanning
│   │   ├── company_policies.py      # Scoped policy retrieval, directory lookup, guardrails
│   │   ├── ai_cost_tracker.py       # FinOps outbox worker & AI pricing registry
│   │   ├── routes_auth.py           # Signup, login, logout, passkey verification
│   │   ├── routes_employee.py       # Employee portal API (profile, attendance, leaves)
│   │   ├── routes_hr.py             # HR Admin API (directory, documents, approvals)
│   │   ├── routes_document_ingest.py# Multipart file upload & batch ingestion endpoints
│   │   ├── routes_admin.py          # Super-admin routes & DLQ management
│   │   ├── schemas.py               # Pydantic data schemas
│   │   ├── models_hr.py             # System-of-record canonical HR models
│   │   ├── metrics.py               # Prometheus metrics exposition (/metrics)
│   │   └── sentry_integration.py    # Sentry error monitoring & PII scrubbing
│   ├── scripts/
│   │   ├── migrate_csv_to_db.py     # CLI utility to migrate CSV/TSV data into MongoDB
│   │   ├── migrate_canonical_schema.py # Idempotent schema migration for canonical fields
│   │   ├── seed_phase1_data.py      # Multi-tenant test company and employee seed script
│   │   ├── disaster_recovery.py     # Empirical DR drill with AES-256 encrypted dumps
│   │   └── deploy_rollback.py       # Deployment rollback utility
│   ├── requirements.txt             # Pinned Python dependencies
│   └── gunicorn.conf.py             # Production Gunicorn worker configuration
├── frontend/
│   ├── src/
│   │   └── app/
│   │       ├── page.tsx             # Intelligent role-based entry splash screen
│   │       ├── login/               # Authentication screen (HR & Employee)
│   │       ├── signup/              # Company registration & employee activation
│   │       ├── hr/                  # HR Studio (Overview, Directory, Leaves, Docs)
│   │       ├── employees/           # Employee Workspace (Attendance, Leaves, Profile, Chat)
│   │       ├── admin/               # Super Administrator Console
│   │       └── globals.css          # Design tokens & Material Icons
│   ├── package.json                 # Next.js 16, React 19, Tailwind CSS 4
│   └── tsconfig.json
├── .github/workflows/
│   ├── ci-cd.yml                    # Automated CI/CD (Bandit, Semgrep, Gitleaks, Trivy)
│   └── keep_alive.yml               # Workflow liveness scheduler
├── Dockerfile                       # Multi-stage production container build
├── docker-compose.prod.yml          # Production multi-service stack
├── render.yaml                      # Render.com IaC deployment blueprint
└── .gitignore                       # Multi-layer repository ignore rules
```

---

## 🚀 Quickstart & Local Setup

### Prerequisites
- **Python**: 3.11+
- **Node.js**: 20+ (with npm)
- **MongoDB Atlas** account (or local MongoDB 7+ replica set)
- **Pinecone** account (Serverless index: `hrbot-policies-employees`, 1024 dimensions)
- **Groq API Key** or **Google Gemini API Key**

---

### 1. Backend Setup
1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\activate

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables in `backend/.env` (see template below).
5. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 9000 --reload
   ```
   *FastAPI documentation will be accessible at [http://127.0.0.1:9000/docs](http://127.0.0.1:9000/docs).*

---

### 2. Frontend Setup
1. Open a second terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   *The frontend will be running on [http://localhost:3005](http://localhost:3005).*

---

## ⚙️ Environment Configuration (`backend/.env`)

```env
# ── MongoDB Atlas ─────────────────────────────────────────────────────────────
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/hrbot?retryWrites=true&w=majority

# ── JWT Authentication ────────────────────────────────────────────────────────
JWT_SECRET=your-strong-production-jwt-secret-minimum-32-chars
JWT_EXP_MINUTES=10080
ADMIN_JWT_EXP_MINUTES=60

# ── AI Provider (Groq / Google GenAI) ─────────────────────────────────────────
AI_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL_NAME=qwen/qwen3.8-27b
GROQ_API_URL=https://api.groq.com/openai/v1

# Alternative Gemini Provider:
# AI_PROVIDER=google_genai
# GEMINI_API_KEY=AIzaSy_your_gemini_key

# ── Pinecone Serverless Vector Database ───────────────────────────────────────
PINECONE_API_KEY=pcsk_your_pinecone_api_key
PINECONE_INDEX_NAME=hrbot-policies-employees
PINECONE_ENVIRONMENT=us-east-1

# ── CORS & Runtime ────────────────────────────────────────────────────────────
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3005,http://127.0.0.1:3005
PROMETHEUS_METRICS_TOKEN=your-metrics-bearer-token
```

---

## 🐳 Production Deployment

### 1. Docker Compose
Run the production multi-container stack (API, Worker, Redis, ClamAV):
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
*Healthchecks verify liveness on `http://localhost:9000/health/liveness`.*

### 2. Render.com
The repository includes a ready-to-use [`render.yaml`](./render.yaml) specification:
- Deploys `backend` via Gunicorn (`gunicorn.conf.py`).
- Automatic health check validation on `/health/liveness`.
- Automated HTTPS configuration and environment variable bindings.

---

## 🔒 Security, Compliance & Invariants

- **Zero-Codebase-Data Rule**: Real employee records, attendance history, and leave balances are prohibited from being saved in flat files inside Git. All operational data is stored strictly in MongoDB Atlas.
- **Cryptographic Standards**:
  - Passwords: **bcrypt** (cost factor 12).
  - Workspace Passkeys: Memory-hard **Argon2id** (64MB memory, 2 iterations, 2 parallelism threads).
  - JWT Tokens: Signed with **HS256**, validated against `token_version` on every authenticated request.
- **Container Hardening**:
  - Unprivileged user execution (`appuser:10001`).
  - Read-only root filesystem with `tmpfs` mounts for `/tmp` and `/run`.
  - Dropped Linux capabilities (`cap_drop: ALL`) and `no-new-privileges: true`.
- **Disaster Recovery**:
  - Automated empirical DR drill testing via [`backend/scripts/disaster_recovery.py`](./backend/scripts/disaster_recovery.py).
  - AES-256 Fernet backup encryption using PBKDF2HMAC (SHA-256, 100,000 iterations).

---

## 🧪 Testing & CI/CD Pipeline

The GitHub Actions pipeline (`.github/workflows/ci-cd.yml`) executes automated gates on every push to `main` or `production`:

```bash
# 1. Syntax & Compilation Check
python -m py_compile backend/app/*.py backend/scripts/*.py

# 2. Static Security Analysis (Bandit SAST)
bandit -r backend/app

# 3. Semgrep Vulnerability Scanning
semgrep scan --config auto backend/app

# 4. Gitleaks Secret Auditing
gitleaks detect --verbose

# 5. Dependency Vulnerability Audit
pip-audit -r backend/requirements.txt

# 6. Container Vulnerability Scanning (Trivy)
trivy image virtualhr-api:latest
```

---

## 📄 License
This codebase is private and proprietary. All rights reserved.
