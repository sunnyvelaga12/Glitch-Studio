# 👔 Glitch HR AI (VirtualHR)

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

## 🌟 Overview

**Glitch HR AI** (internally designated **VirtualHR**) is an enterprise-grade, multi-tenant B2B Human Resources platform. It unifies core HRIS operations—such as employee directory management, attendance tracking, leave applications, and policy administration—with a high-precision **6-Level Retrieval-Augmented Generation (RAG)** pipeline powered by **Pinecone Serverless** and **Groq / Google Gemini** LLMs.

### Key Architectural Pillars
- **Strict Multi-Tenant Isolation**: Complete isolation of users, documents, leave policies, and vector embeddings using scoped tenant IDs (`company_id`).
- **Deterministic 6-Level RAG**: Hybrid search combining dense Pinecone vectors and lexical MongoDB Atlas text search with Reciprocal Rank Fusion (RRF, $k=60$) and dynamic similarity thresholds to eliminate hallucinations.
- **Zero-Codebase Data Architecture**: All operational data, employee PII, attendance logs, and leave balances reside exclusively in encrypted databases (**MongoDB Atlas** & **Pinecone**). No operational data is stored in the Git repository.
- **Atomic Leave State Machine**: Concurrency-safe leave applications with `Idempotency-Key` deduplication, atomic `$expr` balance reservation, and automatic rollback on rejection.
- **Role-Based Workspaces**: Tailored experiences for Employees, HR Managers, and Super Administrators.

---

## 🏗️ System Architecture

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
