import json
import httpx
import logging
import os
import warnings
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.config import settings
from app.schemas import ChatMessage
from app.utils import retry_with_backoff

logger = logging.getLogger(__name__)

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None

try:
    import google.api_core.exceptions as google_exceptions
except ImportError:
    google_exceptions = None

try:
    from google import genai
    from google.genai.errors import APIError as GenaiClientError
    _USE_NEW_GENAI = True
except ImportError:
    genai = None
    GenaiClientError = Exception
    _USE_NEW_GENAI = False


class AIServiceError(RuntimeError):
    """Raised when the configured AI provider returns a service error."""


class AIRateLimitError(AIServiceError):
    """Raised when the configured AI provider is rate-limited or quota-exhausted."""


# Global connection pool for GROQ (production optimization)
_groq_client: Optional[httpx.Client] = None
_async_groq_client = None


def get_async_groq_client():
    """Get or create singleton AsyncGroq client for low-latency streaming."""
    global _async_groq_client
    if _async_groq_client is not None:
        return _async_groq_client

    api_key = settings.GROQ_API_KEY
    if not api_key or api_key == "YOUR_GROQ_API_KEY":
        raise ValueError("GROQ_API_KEY is not configured in backend/.env")

    if AsyncGroq is None:
        raise RuntimeError("groq library is not installed.")

    _async_groq_client = AsyncGroq(api_key=api_key)
    logger.info("AsyncGroq client initialized for non-blocking token streaming.")
    return _async_groq_client


def _get_groq_client() -> httpx.Client:
    """
    Get or create a reusable GROQ HTTP client.
    
    Connection pooling eliminates per-request overhead.
    Thread-safe singleton pattern.
    """
    global _groq_client
    
    if _groq_client is None:
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "YOUR_GROQ_API_KEY":
            raise ValueError(
                "GROQ_API_KEY is not configured. Please set a valid key in backend/.env before starting the server."
            )
        
        _groq_client = httpx.Client(
            base_url=settings.GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "Glitch-HRBot/1.0",
            },
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        logger.info("GROQ HTTP client initialized with connection pooling")
    
    return _groq_client


@retry_with_backoff(
    max_retries=3,
    base_backoff_ms=100,
    exponential_base=2.0,
)
def _call_groq_chat(message: str, conversation_history: list[dict[str, str]]) -> str:
    """
    Call GROQ API with automatic retry on transient failures.
    
    Exponential backoff protects against rate limits and transient network issues.
    """
    candidate_models = [settings.GROQ_MODEL_NAME, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    client = _get_groq_client()
    last_exc = None
    response = None

    messages_payload = list(conversation_history)
    if message and (not messages_payload or messages_payload[-1].get("role") != "user" or messages_payload[-1].get("content") != message):
        messages_payload.append({"role": "user", "content": message})

    for model_name in models_to_try:
        payload = {
            "model": model_name,
            "messages": messages_payload,
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        try:
            response = client.post("/chat/completions", json=payload)
            if response.status_code == 404:
                logger.warning(f"Groq model '{model_name}' not found (404). Trying next fallback model...")
                continue
            response.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code == 404:
                continue
            if exc.response.status_code == 429:
                raise AIRateLimitError("GROQ rate limit exceeded. Please try again later.") from exc
            if exc.response.status_code >= 500:
                raise AIServiceError(f"GROQ API error ({exc.response.status_code}): Server error") from exc
            raise AIServiceError(f"GROQ API error ({exc.response.status_code})") from exc
        except httpx.RequestError as exc:
            raise AIServiceError("Unable to contact GROQ API: Connection error") from exc

    if response is None or not response.is_success:
        raise AIServiceError(f"GROQ API error: all candidate models failed. Last error: {last_exc}")

    try:
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AIServiceError("GROQ API response malformed: missing choices.")

        message_data = choices[0].get("message") or {}
        content = message_data.get("content") or choices[0].get("text") or ""
        if isinstance(content, dict):
            content = content.get("content", "")

        return (content or "").strip()
    except (KeyError, TypeError) as exc:
        raise AIServiceError(f"Failed to parse GROQ response: {str(exc)}") from exc


def close_groq_client() -> None:
    """Close the GROQ client connection pool (cleanup on shutdown)."""
    global _groq_client, _async_groq_client
    if _groq_client is not None:
        _groq_client.close()
        _groq_client = None
        logger.info("GROQ HTTP client closed")
    if _async_groq_client is not None:
        _async_groq_client = None
        logger.info("AsyncGroq client cleared")


# ============================================================================
# Level 6: Grounded Prompt Engineering & Algorithmic Guardrails
# ============================================================================

def check_algorithmic_guardrails(query: str) -> Optional[str]:
    """
    Level 6: Algorithmic Guardrails and Preemptive Refusal.
    Preemptively intercepts queries requesting out-of-scope or sensitive legal/payroll data
    and returns a compliant refusal without invoking the LLM.
    """
    q = query.lower()
    # Refusal: Other employees' confidential salary / payroll
    if any(k in q for k in ["ceo compensation", "ceo salary", "salary of ", "compensation of ", "how much does my colleague", "what does my manager earn", "payroll list", "all salaries"]):
        return (
            "🔒 **Access Prohibited**: Individual compensation details of other employees "
            "are strictly confidential. For your own compensation inquiries, please consult your "
            "employment contract or contact HR directly."
        )

    # Refusal: Legal disputes / suing company
    if any(k in q for k in ["sue the company", "file a lawsuit", "hire a lawyer against", "take legal action against"]):
        return (
            "⚖️ **Legal Policy Directive**: Glitch HR AI cannot discuss legal proceedings or litigation. "
            "Please refer to the internal Dispute Resolution and Grievance Policy or reach out to legal@glitch.com."
        )

    return None


def construct_hr_system_prompt(
    employee_state: Optional[Dict[str, Any]],
    retrieved_context: str,
    disclaimer_required: bool = False,
) -> str:
    """
    Constructs a heavily grounded, ChatGPT-grade system prompt integrating real-time DB state and retrieved context.
    Enforces Zero Hallucination, Mandatory Inline Citations, and Polished Conversational Prose.
    """
    emp = employee_state or {}
    emp_name = emp.get("full_name") or emp.get("fullName") or emp.get("name") or "Employee"
    emp_id = emp.get("employee_id") or emp.get("employeeId") or "EMP001"
    dept = emp.get("department", "Engineering")
    role_title = emp.get("designation") or emp.get("jobTitle") or "Team Member"
    manager = emp.get("manager_name") or emp.get("manager") or "Reporting Manager"
    work_mode = emp.get("work_mode") or emp.get("workMode") or "Remote"
    office_loc = emp.get("office_location") or emp.get("officeLocation") or "Hyderabad"

    balances = emp.get("leave_balance") or emp.get("leave_balances") or {}
    casual_bal = balances.get("casual_leave_remaining", balances.get("casual", 12))
    casual_tot = balances.get("casual_leave_total", 12)
    sick_bal = balances.get("sick_leave_remaining", balances.get("sick", 10))
    sick_tot = balances.get("sick_leave_total", 10)
    priv_bal = balances.get("privilege_leave_remaining", balances.get("privilege", 15))
    priv_tot = balances.get("privilege_leave_total", 20)
    float_bal = balances.get("floating_holidays_remaining", balances.get("floating", 3))

    disclaimer_instruction = ""
    if disclaimer_required:
        disclaimer_instruction = (
            "\n4. MODERATE RELEVANCE NOTICE: The retrieved context is moderately related. "
            "Please conclude your answer with: \"*This appears related, but please verify with HR.*\""
        )

    return f"""You are the official HR AI Assistant for this organization.
Your mission is to deliver ChatGPT-grade, articulate, beautifully structured, and accurate HR guidance based strictly on the authoritative policy documents and the logged-in employee's real-time company record.

RESPONSE STYLE & COMMUNICATION STANDARDS (ChatGPT-Style Excellence):
1. DIRECT ANSWER FIRST: Begin immediately with a clear, concise, and direct answer to the user's question in natural, friendly prose. Do not stall or repeat their question back to them.
2. ELEGANT STRUCTURE:
   - Use clean Markdown headers (### Summary, ### Key Guidelines, ### Approval Workflow) to break up concepts.
   - Use concise bullet points with **bold lead-ins** for effortless scanning.
   - Use clean Markdown tables whenever comparing figures, leave days, timelines, expense caps, or office hours.
3. CONTEXTUAL INTELLIGENCE (Personalized vs. Universal):
   - PERSONALIZED QUERIES (Leave balances, time-off requests, manager sign-offs, WFH/remote eligibility, appraisals):
     Naturally personalize the response using the employee's real profile (e.g., greet {emp_name}, reference their manager {manager}, cite their {casual_bal} remaining Casual Leaves, or address their {dept} department).
   - UNIVERSAL POLICIES (Dress code, core office hours, company holidays, travel reimbursement, medical insurance terms):
     Answer with crisp, authoritative company guidelines directly from the policy documents without forcing awkward personal references.
4. ACTIONABLE GUIDANCE: Where relevant, guide the employee on exact next steps (e.g., "You can submit this request in the Leaves tab above for {manager}'s review.").
5. ACCURACY & INTEGRITY:
   - ZERO HALLUCINATION: If the policy documents do not contain the answer, politely state: "I cannot find this information in the current HR policies."
   - Every factual rule must cite the source policy (e.g., [Source: HR Policy Manual]).
   - Strictly refuse inquiries about other employees' private salaries or confidential data.{disclaimer_instruction}

LOGGED-IN EMPLOYEE PROFILE (Real-Time Database Context):
- Name: {emp_name}
- Employee Code: {emp_id}
- Department: {dept} | Designation: {role_title}
- Reporting Manager: {manager}
- Work Mode: {work_mode} | Location: {office_loc}
- Personal Leave Balances: {casual_bal} Casual (of {casual_tot}), {sick_bal} Sick (of {sick_tot}), {priv_bal} Privilege (of {priv_tot}), {float_bal} Floating Holidays

AUTHORITATIVE POLICY DOCUMENTS:
{retrieved_context}
"""


async def stream_groq_response(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Level 6: Streaming Responses via FastAPI Server-Sent Events (SSE).
    Uses AsyncGroq client for non-blocking asynchronous streaming token deltas.
    Yields data: {"token": token}\n\n and terminates with data: [DONE]\n\n.
    """
    candidate_models = [model, getattr(settings, "GROQ_MODEL_NAME", None), "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    try:
        client = get_async_groq_client()
        stream = None
        for model_name in models_to_try:
            try:
                stream = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    temperature=0.0,
                    max_tokens=1024,
                )
                break
            except Exception as exc:
                if "404" in str(exc) or "not found" in str(exc).lower():
                    logger.warning(f"Groq stream model '{model_name}' not found. Trying next fallback...")
                    continue
                raise exc

        if stream is None:
            raise RuntimeError("All candidate Groq models failed to create a stream.")

        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                token = chunk.choices[0].delta.content
                if token:
                    payload = json.dumps({"token": token})
                    yield f"data: {payload}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        logger.error(f"Groq SSE token streaming failed: {exc}")
        err_msg = str(exc)
        if "rate" in err_msg.lower():
            err_text = "System Notice: AI inference rate limit reached. Please retry in a moment."
        else:
            err_text = "I cannot find this information in the current HR policies."
        err_payload = json.dumps({"token": err_text})
        yield f"data: {err_payload}\n\n"
        yield "data: [DONE]\n\n"


# System Prompt Template (Backward Compatibility)
SYSTEM_PROMPT = """
You are the official HR AI Executive Assistant for {company_name}.

YOUR Core Directive:
Provide clear, executive-grade, beautifully structured answers grounded strictly in official company HR policy, directory context, and the logged-in employee's personal attendance & leave data provided below.

Rules:
1. Ground all answers strictly in the company policy document and the employee's personal context provided.
2. ZERO HALLUCINATION: If the policy context does not contain the answer, state that you cannot find this information in the current HR policies.
3. Every factual claim must include an inline citation [Source: <Policy_Name>, Section <Header>].
4. Refuse out-of-scope inquiries on other employees' confidential salary or lawsuits.

LOGGED-IN EMPLOYEE DATA & ATTENDANCE CONTEXT:
{employee_context}

COMPANY HR POLICY & DIRECTORY CONTEXT:
{policy_document}
"""


def get_system_instruction(
    query: str,
    *,
    policy_document_text: str | None = None,
    employee_context_text: str | None = None,
    company_name: str | None = None,
    hr_email: str | None = None,
) -> str:
    """Build system instruction with dynamic company context and employee details."""
    c_name = company_name or settings.COMPANY_NAME or "the Company"
    h_email = hr_email or settings.HR_EMAIL or f"hr@{c_name.lower().replace(' ', '')}.com"
    emp_ctx = employee_context_text or "No employee personal context provided."

    doc_text = policy_document_text or "No specific policy document provided. Answer strictly within standard company policies."

    return SYSTEM_PROMPT.format(
        company_name=c_name,
        hr_email=h_email,
        employee_context=emp_ctx,
        policy_document=doc_text,
    )


def _build_history(history: List[ChatMessage]) -> list[dict[str, str]]:
    """Limit history to the most recent 10 messages and map roles for the Gemini client."""
    return [
        {"role": "user" if msg.role == "user" else "assistant", "content": msg.content}
        for msg in history[-10:]
    ]


def _create_genai_client():
    if genai is None:
        raise ValueError(
            "google-genai client library is not installed. Please install 'google-genai'."
        )
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing.")
    return genai.Client(api_key=api_key)


def generate_fallback_response(
    message: str,
    policy_text: str | None = None,
    employee_context: dict | None = None,
    company_name: str | None = None,
    hr_email: str | None = None,
) -> str:
    """Provides structured policy response from DB policy text or context."""
    h_email = hr_email or settings.HR_EMAIL or "hr@company.com"
    msg_lower = message.lower()

    if any(k in msg_lower for k in ["data of", "who is", "find employee", "search directory"]):
        if policy_text and ("### 👤 Employee" in policy_text or "Privacy Restricted" in policy_text):
            return f"{policy_text.strip()}\n\n---\n*Need additional clarification? Contact HR directly at {h_email}.*"
        return (
            "### 👤 Employee Directory Search\n\n"
            "No matching employee record was found in your company directory.\n\n"
            "💡 **Tip**: HR Admins can upload or import employee records directly via the **Employees** tab in the HR Dashboard."
        )

    if policy_text and policy_text.strip() and "(No policy document" not in policy_text:
        return f"{policy_text.strip()}\n\n---\n*Need additional clarification? Contact HR directly at {h_email} or visit your HR portal.*"

    from app.company_policies import synthesize_policy_answer
    return f"{synthesize_policy_answer('', message, employee_context=employee_context)}\n\n---\n*Need additional clarification? Contact HR directly at {h_email}.*"


def generate_bot_response(
    message: str,
    history: List[ChatMessage],
    *,
    policy_document_text: str | None = None,
    employee_context_text: str | None = None,
    employee_context_dict: dict | None = None,
    company_name: str | None = None,
    hr_email: str | None = None,
    company_id: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
) -> str:
    # Level 6: Algorithmic Guardrails Check
    guardrail_refusal = check_algorithmic_guardrails(message)
    if guardrail_refusal:
        logger.info("Algorithmic guardrail intercepted query", extra={"company_id": company_id})
        return guardrail_refusal

    if not settings.is_api_configured:
        return generate_fallback_response(
            message,
            policy_document_text,
            employee_context=employee_context_dict,
            company_name=company_name,
            hr_email=hr_email,
        )

    from app.cache import cache_key_for_query, response_cache

    if employee_context_dict and policy_document_text:
        system_instruction = construct_hr_system_prompt(
            employee_state=employee_context_dict,
            retrieved_context=policy_document_text,
        )
    else:
        system_instruction = get_system_instruction(
            message,
            policy_document_text=policy_document_text,
            employee_context_text=employee_context_text,
            company_name=company_name,
            hr_email=hr_email,
        )

    # Try cache first (isolated by company, user, role to prevent cross-tenant leaks)
    cache_key = cache_key_for_query(
        message,
        len(history),
        company_id=company_id or "",
        user_id=user_id or "",
        role=role or "",
    )
    cached_response = response_cache.get(cache_key)
    if cached_response:
        logger.info("Cache hit for query", extra={"message_len": len(message), "company_id": company_id})
        return cached_response

    # Include the system prompt at the head of history to enforce policy rules.
    conversation_history = [
        {"role": "system", "content": system_instruction},
        *(_build_history(history)),
    ]

    if settings.active_provider == "groq":
        response = _call_groq_chat(message=message, conversation_history=conversation_history)
    else:
        client = _create_genai_client()
        try:
            gemini_history = [
                {"role": item["role"] if item["role"] != "assistant" else "model", "parts": [{"text": item["content"]}]}
                for item in _build_history(history)
            ]
            chat = client.chats.create(
                model=settings.AI_MODEL_NAME,
                history=gemini_history,
                config={"system_instruction": system_instruction}
            )
            response = chat.send_message(message)
            response = response.text or ""
        except Exception as exc:
            # Map Google API errors to our custom error types
            if google_exceptions is not None:
                if isinstance(exc, google_exceptions.ResourceExhausted):
                    raise AIRateLimitError(
                        "Gemini API quota exceeded. Please try again later."
                    ) from exc
                if isinstance(exc, (google_exceptions.Unauthenticated, google_exceptions.InvalidArgument)):
                    raise AIServiceError(
                        f"Gemini API configuration error: {str(exc)}"
                    ) from exc
                if isinstance(exc, google_exceptions.GoogleAPIError):
                    raise AIServiceError(
                        f"Gemini API error: {str(exc)}"
                    ) from exc
            # Re-raise if not a Google API error
            raise

    # Cache the response for future identical queries
    response_cache.set(cache_key, response)
    return response
