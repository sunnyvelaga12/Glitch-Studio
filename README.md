# 👔 TechNovance HR Policy Chatbot

An AI-powered Human Resources Policy Assistant built for **TechNovance Solutions Pvt. Ltd.** 
This is a **production-grade college team project** designed to answer employee policy questions accurately from a local policy document, avoiding AI hallucinations and citing specific policy sections.

---

## 🚀 Key Features

**Core Functionality:**
- **Strict Policy Compliance**: The chatbot only answers queries covered in the policy document. If a query is out-of-scope, it redirects users to the HR email (`hr@technovance.com`).
- **Policy Section Citations**: Every policy response automatically cites the exact section (e.g. *"Per Section 2.3 (Sick Leave Policy)..."*).
- **Personal Data Protection**: Questions about individual salaries, leave balances, or appraisal scores are securely redirected to the internal HRMS portal.
- **Scenario-Based Assistance**: Evaluates user situations (e.g. sick family member, weekend work) and recommends the correct policy action (e.g., Casual Leave, Comp-off).

**Production Features:**
- ✨ **Connection Pooling** — 5-10x faster API calls with HTTP keepalive
- ✨ **Response Caching** — 100% instant for repeated queries (LRU + TTL)
- ✨ **Rate Limiting** — Per-IP protection: 60 req/min, 1000 req/hour
- ✨ **Exponential Backoff** — Automatic retry on transient failures
- ✨ **Structured Logging** — JSON logs for ELK/CloudWatch integration
- ✨ **Security Hardening** — Input sanitization, secure CORS, API key masking
- ✨ **Multi-Environment** — Development, staging, production configurations

**User Experience:**
- **Modern Responsive UI**: Built with a sleek, responsive Next.js frontend with Quick Query access buttons for instant policy lookups.

---

## 🛠️ Technology Stack

**Frontend:**
- Next.js (TypeScript, React 19, Tailwind CSS, App Router)

**Backend:**
- FastAPI (Python 3.11, Uvicorn ASGI server)
- Pydantic 2.13 (data validation)
- httpx 0.28.1 (connection pooling for GROQ API)
- Production features: Caching, rate limiting, structured logging, retry logic

**AI Core:**
- Configurable LLM provider: `google_genai` (Gemini 2.0 Flash) or `groq` (Llama 3.1 8B Instant)
- Strict system instructions to prevent hallucinations

**Knowledge Base:**
- Structured JSON policy database (`backend/data/hr_policies.json`)

---

## 📁 Folder Structure
```text
TEAM 12 PROJECT/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI + production middleware
│   │   ├── config.py          # Multi-environment configuration
│   │   ├── bot.py             # AI provider abstraction + connection pooling
│   │   ├── cache.py           # LRU cache + rate limiter (production)
│   │   ├── utils.py           # Structured logging + retry logic (production)
│   │   ├── schemas.py         # Request/response validation
│   │   └── policies.py        # Cached JSON parser
│   ├── data/
│   │   └── hr_policies.json   # Structured HR policy database
│   ├── tests/
│   │   ├── test_backend.py    # 10/10 API unit tests passing
│   │   └── run_test_cases.py  # Automation script (28 test cases)
│   ├── PRODUCTION.md          # Detailed production documentation
│   ├── PRODUCTION_REVIEW.md   # Quick reference guide
│   ├── requirements.txt       # Python dependencies
│   └── .env                   # Environment configuration
└── frontend/
    ├── src/
    │   └── app/
    │       ├── layout.tsx     # Page layout with SEO metadata
    │       ├── page.tsx       # Chat interface with Tailwind styling
    │       └── globals.css    # Global styling
    ├── package.json           # Frontend dependencies
    └── tsconfig.json          # TypeScript settings
```

---

## ⚙️ How to Run Locally

### 1. Backend Setup
1. Open a terminal and navigate to the `backend` folder:
   ```bash
   cd backend
   ```
2. Activate the virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     .\venv\Scripts\activate
     ```
   - **Mac/Linux**:
     ```bash
     source venv/bin/activate
     ```
3. Configure your AI provider and API key in `backend/.env`.
   - For Gemini:
     ```env
     AI_PROVIDER=google_genai
     GEMINI_API_KEY=AIzaSy_your_actual_key_here
     ```
   - For GROQ:
     ```env
     AI_PROVIDER=groq
     GROQ_API_KEY=your-groq-key-here
     ```

4. Run the development server:
   ```bash
   uvicorn app.main:app --reload
   ```
   *FastAPI documentation will be running at [http://localhost:8000/docs](http://localhost:8000/docs).*

### 2. Frontend Setup
1. Open a new terminal and navigate to the `frontend` folder:
   ```bash
   cd frontend
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```
   *The application frontend UI will be running at [http://localhost:3000](http://localhost:3000).*

---

## 📋 Running Automated Tests & QA Log
To run the automated API suite:
```bash
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_backend.py"
```

To run the complete 28-question QA log execution script (which populates the test results in `backend/tests/test_log.md`):
```bash
cd backend
.\venv\Scripts\python.exe tests/run_test_cases.py
```

---

## 👥 Team 12 Project Members
| Member Name | Project Role |
|---|---|
| Nandakishor Kalagarla | Backend & Frontend Architect |
| (Team Member 2) | Knowledge Base Manager |
| (Team Member 3) | Prompt Engineer |
| (Team Member 4) | UI Developer |
| (Team Member 5) | Testing & Deployment |
"# team12" 
