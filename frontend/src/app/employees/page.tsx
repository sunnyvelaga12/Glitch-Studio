"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

type Message = { role: "user" | "assistant"; content: string; error?: boolean };
type Tab = "overview" | "attendance" | "leaves" | "profile" | "chatbot";

// ─── Google Material Icon Component ───────────────────────────────────────────
function Icon({ name, size = 20, color, style, className = "" }: { name: string; size?: number; color?: string; style?: React.CSSProperties; className?: string }) {
  return (
    <span
      className={`material-symbols-rounded ${className}`}
      style={{ fontSize: size, color: color, verticalAlign: "middle", userSelect: "none", lineHeight: 1, ...style }}
    >
      {name}
    </span>
  );
}

const TAB_LABELS: Record<Tab, { label: string; icon: string }> = {
  overview:   { label: "Overview",        icon: "analytics" },
  attendance: { label: "Attendance",      icon: "schedule" },
  leaves:     { label: "Leaves",          icon: "event_available" },
  profile:    { label: "My Profile",      icon: "person" },
  chatbot:    { label: "AI Policy Assist",icon: "auto_awesome" },
};

interface EmployeeProfile {
  employee_id: string; first_name: string; last_name: string; email: string;
  department: string; designation: string; manager_name: string;
  office_location: string; work_mode: string; years_with_company: number;
  performance_rating: number; phone?: string; skills?: string[];
  certifications?: string[]; date_of_joining?: string;
}
interface LeaveBalance {
  casual_leave_remaining: number; sick_leave_remaining: number;
  privilege_leave_remaining: number; floating_holidays_remaining: number;
}
interface AttendanceRecord { date: string; status: string; hours_worked: number; }

// ─── Design tokens (Google / Microsoft / Zoho Enterprise Palette) ───────────────
const T = {
  pageBg:       "#f8fafd",
  cardBg:       "#ffffff",
  cardBorder:   "#dadce0",
  inputBg:      "#f1f3f4",
  mutedBg:      "#f8f9fa",
  accentBg:     "#e8f0fe",
  textPrimary:  "#1f1f1f",
  textSecondary:"#444746",
  textMuted:    "#727775",
  indigo:       "#0b57d0",
  blue:         "#1a73e8",
  emerald:      "#1e8e3e",
  amber:        "#f9ab00",
  rose:         "#d93025",
  primaryGrad:  "linear-gradient(135deg,#1a73e8 0%,#0b57d0 100%)",
};

// ─── Quick Queries ─────────────────────────────────────────────────────────────
type Topic = "all" | "leave" | "wfh" | "expenses" | "attendance" | "appraisal" | "conduct";
interface QuickQuery { label: string; icon: string; topic: Topic; query: string; }

const QUICK_QUERIES: QuickQuery[] = [
  { label: "Leave Entitlements", icon: "event_note",      topic: "leave",      query: "What are the different leave categories and how many days am I entitled to?" },
  { label: "WFH Eligibility",    icon: "home_work",       topic: "wfh",        query: "What is the work-from-home policy and who is eligible?" },
  { label: "Expense Submission", icon: "receipt_long",    topic: "expenses",   query: "How do I submit an expense claim and what expenses are covered?" },
  { label: "Office Timings",     icon: "schedule",        topic: "attendance", query: "What are the office timings, core hours, and late arrival policy?" },
  { label: "Performance Rating", icon: "trending_up",     topic: "appraisal",  query: "How does the annual appraisal work and what are the rating guidelines?" },
  { label: "Dress Code Guide",   icon: "checkroom",        topic: "conduct",    query: "What is the dress code for regular days and client visits?" },
];

const INITIAL_MESSAGE: Message = {
  role: "assistant",
  content: "Hello! I'm your AI HR Assistant. Ask me anything about your company's policies — leave balance, WFH, expense claims, appraisals, or attendance rules.",
};

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ─── Shared micro components ──────────────────────────────────────────────────
function Spinner({ size = 20 }: { size?: number }) {
  return <div style={{ width: size, height: size, borderRadius: "50%", border: "2.5px solid #e0e7ff", borderTopColor: T.indigo, animation: "spin 0.8s linear infinite", flexShrink: 0 }} />;
}

// ─── Markdown Renderer ─────────────────────────────────────────────────────────
function FormattedChatMarkdown({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(null);

  const renderText = (text: string) =>
    text.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} style={{ color: T.textPrimary, fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`") && part.endsWith("`")) return <code key={i} style={{ background: "#eef2ff", color: T.indigo, padding: "1px 6px", borderRadius: 4, fontSize: "0.9em", fontFamily: "monospace" }}>{part.slice(1, -1)}</code>;
      return part;
    });

  const renderBlocks = (raw: string) => {
    const lines = raw.split("\n");
    const elements: React.ReactNode[] = [];
    let tableHeader: string[] = [], tableRows: string[][] = [], inTable = false;

    const flushTable = (key: number) => {
      if (!tableHeader.length) return;
      elements.push(
        <div key={`t-${key}`} style={{ overflowX: "auto", borderRadius: 10, border: `1px solid ${T.cardBorder}`, margin: "8px 0" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead style={{ background: T.mutedBg }}>
              <tr>{tableHeader.map((h, i) => <th key={i} style={{ padding: "8px 12px", textAlign: "left", color: T.textSecondary, fontWeight: 700 }}>{renderText(h.trim())}</th>)}</tr>
            </thead>
            <tbody>
              {tableRows.map((row, ri) => (
                <tr key={ri} style={{ borderTop: "1px solid #f1f5f9" }}>
                  {row.map((cell, ci) => <td key={ci} style={{ padding: "8px 12px", color: T.textSecondary }}>{renderText(cell.trim())}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableHeader = []; tableRows = []; inTable = false;
    };

    lines.forEach((line, idx) => {
      const t = line.trim();
      if (t.startsWith("|") && t.endsWith("|")) {
        const cells = t.split("|").slice(1, -1);
        if (cells.every(c => c.trim().startsWith(":") || c.trim().startsWith("-"))) return;
        if (!inTable) { inTable = true; tableHeader = cells; } else tableRows.push(cells);
        return;
      }
      if (inTable) flushTable(idx);
      if (t.startsWith("### ")) { elements.push(<p key={idx} style={{ margin: "6px 0 2px", fontSize: 13, fontWeight: 800, color: T.textPrimary }}>{renderText(t.slice(4))}</p>); return; }
      if (t.startsWith("## "))  { elements.push(<p key={idx} style={{ margin: "8px 0 4px", fontSize: 14, fontWeight: 800, color: T.textPrimary }}>{renderText(t.slice(3))}</p>); return; }
      if (/^[-*•]\s+/.test(t)) {
        elements.push(<li key={idx} style={{ marginLeft: 16, marginBottom: 3, fontSize: 12, lineHeight: 1.6, color: T.textSecondary, listStyleType: "disc" }}>{renderText(t.replace(/^[-*•]\s+/, ""))}</li>);
        return;
      }
      if (t === "---") { elements.push(<hr key={idx} style={{ borderColor: T.cardBorder, margin: "8px 0" }} />); return; }
      if (t) elements.push(<p key={idx} style={{ margin: "3px 0", fontSize: 12, lineHeight: 1.65, color: T.textSecondary }}>{renderText(t)}</p>);
    });
    if (inTable) flushTable(lines.length);
    return elements;
  };

  return (
    <div>
      <div>{renderBlocks(content)}</div>
      <div style={{ paddingTop: 8, marginTop: 8, borderTop: `1px solid ${T.cardBorder}`, display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11, color: T.textMuted }}>
        <span style={{ color: T.indigo, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
          <Icon name="auto_awesome" size={14} color={T.indigo} /> Grounded HR AI Answer
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={() => { navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            style={{ border: "none", background: "none", color: copied ? T.emerald : T.textMuted, fontWeight: 600, cursor: "pointer", fontSize: 11, display: "flex", alignItems: "center", gap: 3 }}>
            <Icon name={copied ? "check" : "content_copy"} size={14} />
            {copied ? "Copied" : "Copy"}
          </button>
          <button onClick={() => setRating(r => r === "up" ? null : "up")} style={{ border: "none", background: "none", cursor: "pointer", opacity: rating === "up" ? 1 : 0.5 }}>
            <Icon name="thumb_up" size={14} color={rating === "up" ? T.emerald : T.textMuted} />
          </button>
          <button onClick={() => setRating(r => r === "down" ? null : "down")} style={{ border: "none", background: "none", cursor: "pointer", opacity: rating === "down" ? 1 : 0.5 }}>
            <Icon name="thumb_down" size={14} color={rating === "down" ? T.rose : T.textMuted} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Message Bubble ───────────────────────────────────────────────────────────
function MessageBubble({ message, timestamp }: { message: Message; timestamp: Date }) {
  const isUser = message.role === "user";
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", flexDirection: isUser ? "row-reverse" : "row" }} className="animate-fade-in">
      <div style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 11,
        background: isUser ? T.primaryGrad : "linear-gradient(135deg,#4f46e5,#818cf8)", color: "#fff", boxShadow: "0 2px 8px rgba(79,70,229,.25)" }}>
        {isUser ? "You" : <Icon name="auto_awesome" size={18} color="#fff" />}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: "82%", alignItems: isUser ? "flex-end" : "flex-start" }}>
        <div style={{
          padding: "10px 16px", borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? T.primaryGrad : "#ffffff",
          border: isUser ? "none" : `1px solid ${T.cardBorder}`,
          boxShadow: isUser ? "0 4px 14px rgba(79,70,229,.2)" : "0 1px 4px rgba(0,0,0,.06)",
          color: isUser ? "#fff" : T.textPrimary,
          fontSize: 12, lineHeight: 1.6,
        }}>
          {isUser
            ? <p style={{ margin: 0, color: "#fff" }}>{message.content}</p>
            : message.error
              ? <p style={{ margin: 0, color: T.rose, fontSize: 12 }}>{message.content}</p>
              : <FormattedChatMarkdown content={message.content} />}
        </div>
        <p style={{ fontSize: 10, color: T.textMuted, margin: 0, padding: "0 2px" }}>
          {isUser ? `You · ${formatTime(timestamp)}` : `HR Assistant · ${formatTime(timestamp)}`}
        </p>
      </div>
    </div>
  );
}

// ─── Typing Indicator ─────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px", borderRadius: "18px 18px 18px 4px", background: "#fff", border: `1px solid ${T.cardBorder}`, boxShadow: "0 1px 4px rgba(0,0,0,.06)", width: "fit-content" }} className="animate-fade-in">
      <Icon name="auto_awesome" size={18} color={T.indigo} className="animate-spin" />
      <span style={{ fontSize: 11, fontWeight: 600, color: T.indigo }}>Generating AI policy response...</span>
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        {[0, 1, 2].map(i => <span key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: T.indigo, display: "inline-block", animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite` }} />)}
      </div>
    </div>
  );
}

// ─── Chatbot Component ────────────────────────────────────────────────────────
function TailwindChatbot({ token }: { token: string }) {
  const [messages, setMessages] = useState<Message[]>([INITIAL_MESSAGE]);
  const [timestamps, setTimestamps] = useState<Date[]>([new Date()]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, isLoading]);

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading || !token) return;
    const userMsg: Message = { role: "user", content: trimmed };
    setMessages(prev => [...prev, userMsg]);
    setTimestamps(prev => [...prev, new Date()]);
    setInput(""); setIsLoading(true);
    try {
      const history = [...messages, userMsg].map(({ role, content }) => ({ role, content }));
      
      // Attempt low-latency SSE streaming first
      const res = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: trimmed, history }),
      });

      if (!res.ok) {
        // Fallback to standard chat endpoint if streaming returns error
        const fallbackRes = await fetch(`${BACKEND_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ message: trimmed, history }),
        });
        const data = fallbackRes.headers.get("content-type")?.includes("application/json") ? await fallbackRes.json() : {};
        if (!fallbackRes.ok) throw new Error(data.detail ?? data.error ?? "Server error");
        setMessages(prev => [...prev, { role: "assistant", content: data.response ?? "Sorry, I couldn't generate a response.", error: Boolean(data.error) }]);
        return;
      }

      if (!res.body) {
        throw new Error("Streaming connection body not available.");
      }

      // Initialize assistant placeholder
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);
      setTimestamps(prev => [...prev, new Date()]);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (trimmedLine.startsWith("data: ")) {
            const dataStr = trimmedLine.replace("data: ", "").trim();
            if (dataStr === "[DONE]") break;
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.token) {
                accumulated += parsed.token;
                setMessages(prev => {
                  const copy = [...prev];
                  const lastIdx = copy.length - 1;
                  if (lastIdx >= 0 && copy[lastIdx].role === "assistant") {
                    copy[lastIdx] = { ...copy[lastIdx], content: accumulated };
                  }
                  return copy;
                });
              }
            } catch {
              // Ignore partial frame parse errors
            }
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessages(prev => [...prev, { role: "assistant", content: `Unable to connect to backend.\n\nError: ${msg}`, error: true }]);
    } finally {
      setIsLoading(false); setTimestamps(prev => [...prev, new Date()]); inputRef.current?.focus();
    }
  }, [isLoading, messages, token]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Quick suggestion chips */}
      <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }} className="light-scrollbar">
        {QUICK_QUERIES.map((item, i) => (
          <button key={i} onClick={() => sendMessage(item.query)}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 99, border: `1.5px solid ${T.cardBorder}`, background: "#fff", color: T.textSecondary, fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", cursor: "pointer", flexShrink: 0, transition: "all 0.15s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "#c7d2fe"; e.currentTarget.style.background = "#eef2ff"; e.currentTarget.style.color = T.indigo; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = T.cardBorder; e.currentTarget.style.background = "#fff"; e.currentTarget.style.color = T.textSecondary; }}
          >
            <Icon name={item.icon} size={16} color={T.indigo} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>

      {/* Chat canvas — Google Gemini Aesthetic */}
      <div style={{ background: "#fff", border: "1px solid #dadce0", borderRadius: 24, boxShadow: "0 2px 10px rgba(60,64,67,0.08)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header */}
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #e0e5ed", display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f8fafd" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 12, background: "var(--grad-gemini)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 2px 8px rgba(26,115,232,.25)" }}>
              <Icon name="auto_awesome" size={20} color="#fff" />
            </div>
            <div>
              <p style={{ margin: 0, fontSize: 10, fontWeight: 800, color: "#1a73e8", textTransform: "uppercase", letterSpacing: "0.1em" }}>Glitch AI</p>
              <p style={{ margin: "1px 0 0", fontSize: 13.5, fontWeight: 700, color: "#1f1f1f" }}>Policy Assistant</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 12px", borderRadius: 99, background: "#e6f4ea", border: "1px solid #ceead6", fontSize: 11, fontWeight: 700, color: "#137333" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#34a853", animation: "pulse 2s infinite", display: "inline-block" }} />
            Gemini Connected
          </div>
        </div>

        {/* Messages */}
        <div className="light-scrollbar" style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 18, overflowY: "auto", maxHeight: 480, minHeight: 280, background: "#fafbff" }} role="log" aria-live="polite">
          {messages.map((msg, i) => <MessageBubble key={i} message={msg} timestamp={timestamps[i] ?? new Date()} />)}
          {isLoading && (
            <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <div style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0, background: "var(--grad-gemini)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon name="auto_awesome" size={18} color="#fff" />
              </div>
              <TypingIndicator />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input bar — Google Gemini floating prompt pill */}
        <div style={{ padding: "14px 16px", borderTop: "1px solid #e0e5ed", background: "#fff" }}>
          <div className="gemini-prompt-box" style={{ display: "flex", gap: 10, alignItems: "center", position: "relative", padding: "4px 6px 4px 16px" }}>
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
              placeholder="Ask any policy question (e.g. leave balance, WFH guidelines, reimbursement)..."
              disabled={isLoading}
              style={{ flex: 1, border: "none", background: "transparent", outline: "none", fontSize: 13.5, color: "#1f1f1f", padding: "8px 0" }}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={isLoading || !input.trim()}
              style={{ padding: "8px 18px", borderRadius: 24, border: "none", background: "#1a73e8", color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer", opacity: (isLoading || !input.trim()) ? 0.45 : 1, display: "flex", alignItems: "center", gap: 6, transition: "all 0.15s", boxShadow: "0 1px 3px rgba(26,115,232,0.3)" }}
            >
              <span>Ask</span>
              <Icon name="send" size={14} color="#fff" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main Employee Dashboard ───────────────────────────────────────────────────
export default function EmployeeDashboard() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [profile, setProfile] = useState<EmployeeProfile | null>(null);
  const [leaveBalance, setLeaveBalance] = useState<LeaveBalance | null>(null);
  const [attendance, setAttendance] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [leaveApplication, setLeaveApplication] = useState({ from_date: "", to_date: "", reason: "", leave_type: "casual_leave" });
  const [leaveSuccess, setLeaveSuccess] = useState(false);
  const [submittingLeave, setSubmittingLeave] = useState(false);
  const [myLeaveRequests, setMyLeaveRequests] = useState<any[]>([]);

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    const storedEmployee = localStorage.getItem("employee_profile");
    if (!storedToken) { router.push("/login"); return; }
    setToken(storedToken);
    if (storedEmployee) { try { setProfile(JSON.parse(storedEmployee)); } catch {} }
    loadEmployeeData(storedToken);
  }, [router]);

  const loadEmployeeData = async (authToken: string) => {
    setLoading(true);
    try {
      const [profileRes, leaveRes, attendanceRes, requestsRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/v1/employees/profile/me`, { credentials: "include", headers: { Authorization: `Bearer ${authToken}` } }),
        fetch(`${BACKEND_URL}/api/v1/employees/leave-balance/me`, { credentials: "include", headers: { Authorization: `Bearer ${authToken}` } }),
        fetch(`${BACKEND_URL}/api/v1/employees/attendance/me?days=5`, { credentials: "include", headers: { Authorization: `Bearer ${authToken}` } }),
        fetch(`${BACKEND_URL}/api/v1/employees/leaves/my-requests`, { credentials: "include", headers: { Authorization: `Bearer ${authToken}` } }),
      ]);
      if (profileRes.ok) setProfile(await profileRes.json());
      if (leaveRes.ok) {
        const d = await leaveRes.json();
        setLeaveBalance({
          casual_leave_remaining: d.casual_leave_remaining ?? 12,
          sick_leave_remaining: d.sick_leave_remaining ?? 8,
          privilege_leave_remaining: d.privilege_leave_remaining ?? 15,
          floating_holidays_remaining: d.floating_holidays_remaining ?? 3,
        });
      }
      if (attendanceRes.ok) setAttendance(await attendanceRes.json());
      if (requestsRes.ok) setMyLeaveRequests(await requestsRes.json());
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  const handleLeaveApplication = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leaveApplication.from_date || !leaveApplication.to_date) { alert("Please select both start and end dates."); return; }
    setSubmittingLeave(true);
    try {
      const idempotencyKey = typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `IDEM-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

      const res = await fetch(`${BACKEND_URL}/api/v1/employees/leaves/apply`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify(leaveApplication),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const msg = errData.error?.message || (typeof errData.detail === "string" ? errData.detail : errData.detail?.message) || "Failed to submit leave application";
        throw new Error(msg);
      }

      setLeaveSuccess(true);
      setTimeout(() => setLeaveSuccess(false), 4000);
      setLeaveApplication({ from_date: "", to_date: "", reason: "", leave_type: "casual_leave" });
      
      // Authoritative state refetch from backend
      await loadEmployeeData(token);
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    } finally {
      setSubmittingLeave(false);
    }
  };

  const handleLogout = () => { localStorage.removeItem("token"); localStorage.removeItem("employee_profile"); router.push("/login"); };

  if (!profile && loading) {
    return (
      <div className="light-page" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, color: T.textSecondary }}>
          <Spinner size={28} /><span style={{ fontSize: 14, fontWeight: 600 }}>Loading your workspace…</span>
        </div>
      </div>
    );
  }

  const userInitials = profile ? `${profile.first_name?.[0] ?? "E"}${profile.last_name?.[0] ?? ""}` : "EM";
  const fullName = profile ? `${profile.first_name} ${profile.last_name}` : "Employee";

  const attBadge = (status: string) => {
    if (status === "Present")  return { bg: "var(--google-green-container)", text: "var(--google-green-text)", border: "var(--google-green-border)" };
    if (status === "WFH")      return { bg: "var(--google-blue-container)", text: "var(--google-blue-text)", border: "var(--google-blue-border)" };
    if (status === "Absent")   return { bg: "var(--google-red-container)", text: "var(--google-red-text)", border: "var(--google-red-border)" };
    return { bg: "var(--google-yellow-container)", text: "var(--google-yellow-text)", border: "var(--google-yellow-border)" };
  };

  return (
    <div className="light-page" style={{ minHeight: "100vh", position: "relative" }}>
      <style>{`
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
        @keyframes pulse{0%,100%{opacity:.8}50%{opacity:1}}
      `}</style>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="light-header" style={{ position: "sticky", top: 0, zIndex: 50 }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 16px", height: 64, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 14, background: "var(--grad-gemini)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 14px rgba(26,115,232,.25)", flexShrink: 0 }}>
              <Icon name="auto_awesome" size={22} color="#fff" />
            </div>
            <div>
              <p style={{ margin: 0, fontSize: 10, fontWeight: 800, color: "#1a73e8", textTransform: "uppercase", letterSpacing: "0.12em", lineHeight: 1 }}>Glitch</p>
              <p style={{ margin: "2px 0 0", fontSize: 14, fontWeight: 800, color: T.textPrimary, lineHeight: 1 }}>{fullName}</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 14px 5px 6px", borderRadius: 28, background: "#f8fafd", border: "1px solid #dadce0", boxShadow: "0 1px 2px rgba(60,64,67,0.08)" }}>
              <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--grad-gemini)", color: "#fff", fontWeight: 800, fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" }}>{userInitials}</div>
              <span className="hide-on-mobile" style={{ fontSize: 13, fontWeight: 600, color: "#3c4043" }}>{profile?.department ?? "General"}</span>
            </div>
            <button onClick={handleLogout}
              style={{ padding: "7px 18px", borderRadius: 28, border: "1px solid #dadce0", background: "#fff", color: "#3c4043", fontWeight: 600, fontSize: 13, cursor: "pointer", transition: "all 0.2s", display: "flex", alignItems: "center", gap: 6, boxShadow: "0 1px 2px rgba(60,64,67,0.08)" }}
              onMouseEnter={e => { e.currentTarget.style.background = "#fce8e6"; e.currentTarget.style.color = "#c5221f"; e.currentTarget.style.borderColor = "#fad2cf"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "#fff"; e.currentTarget.style.color = "#3c4043"; e.currentTarget.style.borderColor = "#dadce0"; }}
            >
              <Icon name="logout" size={16} />
              <span className="hide-on-mobile">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Container ─────────────────────────────────────────────────── */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 16px 84px", display: "flex", flexDirection: "column", gap: 20 }}>

        {/* Navigation tabs — Google Material You Pill Design */}
        <nav style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 2 }} className="light-scrollbar">
          {(["overview", "attendance", "leaves", "profile", "chatbot"] as const).map(tab => {
            const active = activeTab === tab;
            const meta = TAB_LABELS[tab];
            return (
              <button key={tab} onClick={() => setActiveTab(tab)}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 20px", borderRadius: 28, fontSize: 13, fontWeight: active ? 700 : 500, whiteSpace: "nowrap", cursor: "pointer", transition: "all 0.2s ease", border: "none",
                  background: active ? "#e8f0fe" : "#ffffff",
                  color: active ? "#1a73e8" : "#5f6368",
                  boxShadow: active ? "0 1px 3px rgba(60,64,67,0.12)" : "0 1px 2px rgba(60,64,67,0.06)",
                  outline: !active ? "1px solid #dadce0" : "none",
                }}>
                <Icon name={meta.icon} size={19} color={active ? "#1a73e8" : "#5f6368"} />
                <span>{meta.label}</span>
              </button>
            );
          })}
        </nav>

        {/* ── OVERVIEW TAB ─────────────────────────────────────────────────── */}
        {activeTab === "overview" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }} className="animate-fade-in">
            {/* Welcome banner — Google Gemini Ambient Gradient */}
            <div className="light-card" style={{ padding: "24px 28px", background: "var(--grad-gemini-soft)", border: "1px solid #dadce0", boxShadow: "var(--shadow-sm)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: 22, fontWeight: 900, color: T.textPrimary, display: "flex", alignItems: "center", gap: 8 }}>
                    <span>Welcome back, <span style={{ background: "var(--grad-gemini)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>{profile?.first_name ?? "Employee"}</span>!</span>
                    <Icon name="waving_hand" size={24} color={T.amber} />
                  </h2>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSecondary }}>Here is your Glitch workplace summary, leave balance, and quick policy shortcuts.</p>
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <button onClick={() => setActiveTab("chatbot")}
                    style={{ padding: "9px 20px", borderRadius: 12, border: "none", background: "#1a73e8", color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer", boxShadow: "0 4px 14px rgba(26,115,232,.25)", display: "flex", alignItems: "center", gap: 6 }}>
                    <Icon name="auto_awesome" size={18} color="#fff" />
                    <span>Ask Glitch AI</span>
                  </button>
                  <button onClick={() => setActiveTab("leaves")}
                    style={{ padding: "9px 20px", borderRadius: 12, border: `1px solid ${T.cardBorder}`, background: "#fff", color: T.textSecondary, fontWeight: 700, fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
                    <Icon name="event_available" size={18} color="#1a73e8" />
                    <span>Apply Leave</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Metric cards — Responsive 2x2 on Mobile, 4x1 on Desktop */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 14 }}>
              {[
                { icon: "corporate_fare", label: "Department",        value: profile?.department ?? "Engineering",        bg: "var(--google-blue-container)",   color: "var(--google-blue)" },
                { icon: "badge",          label: "Designation",       value: profile?.designation ?? "Software Engineer", bg: "var(--google-purple-container)", color: "var(--google-purple)" },
                { icon: "person",         label: "Reporting Manager", value: profile?.manager_name ?? "—",            bg: "var(--google-yellow-container)", color: "var(--google-yellow)" },
                { icon: "star",           label: "Performance Rating", value: `${profile?.performance_rating ?? 4.8} / 5.0`, bg: "var(--google-green-container)",  color: "var(--google-green)" },
              ].map(c => (
                <div key={c.label} className="light-card light-card-lift" style={{ padding: "16px 18px", display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: c.bg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Icon name={c.icon} size={22} color={c.color} />
                  </div>
                  <div>
                    <p style={{ margin: 0, fontSize: 11, color: T.textMuted, fontWeight: 500 }}>{c.label}</p>
                    <p style={{ margin: "2px 0 0", fontSize: 13.5, fontWeight: 800, color: T.textPrimary, lineHeight: 1.2 }}>{c.value}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Leave Balance — Google M3 4-Color Tonal System */}
            <div className="light-card" style={{ padding: "20px 24px" }}>
              <p style={{ margin: "0 0 16px", fontSize: 14, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="event_available" size={20} color="var(--google-blue)" /> Leave Balances
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: 12 }}>
                {[
                  { label: "Casual Leave",       val: leaveBalance?.casual_leave_remaining ?? 12,   color: "var(--google-blue-text)",    bg: "var(--google-blue-container)", border: "var(--google-blue-border)" },
                  { label: "Sick Leave",          val: leaveBalance?.sick_leave_remaining ?? 8,      color: "var(--google-green-text)",   bg: "var(--google-green-container)", border: "var(--google-green-border)" },
                  { label: "Privilege Leave",     val: leaveBalance?.privilege_leave_remaining ?? 15, color: "var(--google-purple-text)",  bg: "var(--google-purple-container)", border: "var(--google-purple-border)" },
                  { label: "Floating Holidays",  val: leaveBalance?.floating_holidays_remaining ?? 3, color: "var(--google-yellow-text)",  bg: "var(--google-yellow-container)", border: "var(--google-yellow-border)" },
                ].map(l => (
                  <div key={l.label} style={{ padding: "16px 14px", borderRadius: 14, background: l.bg, border: `1px solid ${l.border}`, textAlign: "center" }}>
                    <p style={{ margin: 0, fontSize: 28, fontWeight: 900, color: l.color }}>{l.val}</p>
                    <p style={{ margin: "4px 0 0", fontSize: 11, color: l.color, opacity: 0.85, fontWeight: 600 }}>{l.label}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── AI CHATBOT TAB ───────────────────────────────────────────────── */}
        {activeTab === "chatbot" && (
          <div className="animate-fade-in">
            <TailwindChatbot token={token} />
          </div>
        )}

        {/* ── ATTENDANCE TAB ───────────────────────────────────────────────── */}
        {activeTab === "attendance" && (
          <div className="light-card animate-fade-in" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.cardBorder}`, display: "flex", alignItems: "center", gap: 8 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="schedule" size={20} color="#1a73e8" /> Attendance Log <span style={{ color: T.textMuted, fontWeight: 400, fontSize: 13 }}>(Recent 5 Days)</span>
              </h2>
            </div>
            <div className="table-responsive">
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead style={{ background: T.mutedBg }}>
                  <tr>
                    {["Date", "Status", "Hours Worked"].map(h => <th key={h} style={{ padding: "11px 18px", textAlign: "left", fontWeight: 700, color: T.textSecondary, fontSize: 12 }}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {(attendance.length > 0 ? attendance : [
                    { date: "29 Jul 2026", status: "Present", hours_worked: 8.5 },
                    { date: "28 Jul 2026", status: "WFH",     hours_worked: 8.0 },
                    { date: "25 Jul 2026", status: "Present", hours_worked: 9.0 },
                    { date: "24 Jul 2026", status: "Present", hours_worked: 8.0 },
                    { date: "23 Jul 2026", status: "Present", hours_worked: 8.5 },
                  ]).map((row, idx) => {
                    const b = attBadge(row.status);
                    return (
                      <tr key={idx} style={{ borderTop: `1px solid #f1f5f9`, transition: "background 0.15s" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#f8faff")}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                        <td style={{ padding: "13px 18px", fontWeight: 600, color: T.textSecondary }}>{row.date}</td>
                        <td style={{ padding: "13px 18px" }}>
                          <span style={{ padding: "3px 12px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: b.bg, color: b.text, border: `1px solid ${b.border}` }}>{row.status}</span>
                        </td>
                        <td style={{ padding: "13px 18px", color: T.textSecondary }}>{row.hours_worked}h</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── LEAVES TAB ───────────────────────────────────────────────────── */}
        {activeTab === "leaves" && (
          <div className="light-card animate-fade-in" style={{ padding: "24px 28px" }}>
            <h2 style={{ margin: "0 0 20px", fontSize: 15, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="event_available" size={20} color="#1a73e8" /> Apply for Leave
            </h2>
            {leaveSuccess && (
              <div style={{ marginBottom: 16, padding: "12px 16px", borderRadius: 12, background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#15803d", fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }} className="animate-fade-in">
                <Icon name="check_circle" size={18} color="#15803d" /> Leave application submitted successfully! Your manager will review it.
              </div>
            )}
            <form onSubmit={handleLeaveApplication} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 16 }}>
              {[
                { label: "Leave Type", isSelect: true, key: "leave_type" },
                { label: "Start Date",  isDate: true,   key: "from_date" },
                { label: "End Date",    isDate: true,   key: "to_date" },
                { label: "Reason",      isText: true,   key: "reason" },
              ].map(f => (
                <div key={f.key} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.06em" }}>{f.label}</label>
                  {f.isSelect ? (
                    <select value={leaveApplication.leave_type} onChange={e => setLeaveApplication({ ...leaveApplication, leave_type: e.target.value })} className="light-select" style={{ width: "100%", height: 44 }}>
                      <option value="casual_leave">Casual Leave</option>
                      <option value="sick_leave">Sick Leave</option>
                      <option value="privilege_leave">Privilege Leave</option>
                    </select>
                  ) : (
                    <input type={f.isDate ? "date" : "text"}
                      value={(leaveApplication as any)[f.key]}
                      onChange={e => setLeaveApplication({ ...leaveApplication, [f.key]: e.target.value })}
                      placeholder={f.isText ? "Brief reason…" : undefined}
                      className="light-input"
                      style={{ height: 44 }}
                    />
                  )}
                </div>
              ))}
              <div style={{ gridColumn: "1/-1", paddingTop: 4 }}>
                <button type="submit" disabled={submittingLeave}
                  style={{ padding: "11px 28px", borderRadius: 24, border: "none", background: "#1a73e8", color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer", boxShadow: "0 4px 14px rgba(26,115,232,.25)", display: "flex", alignItems: "center", gap: 6, opacity: submittingLeave ? 0.5 : 1 }}>
                  <Icon name="send" size={16} color="#fff" />
                  <span>{submittingLeave ? "Submitting…" : "Submit Leave Application"}</span>
                </button>
              </div>
            </form>

            {/* Submitted requests history */}
            <div style={{ marginTop: 32, paddingTop: 24, borderTop: `1px solid ${T.cardBorder}` }}>
              <p style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="history" size={18} color="#1a73e8" /> My Submitted Leave Requests
              </p>
              {myLeaveRequests.length === 0 ? (
                <p style={{ fontSize: 12, color: T.textMuted, margin: 0 }}>No leave applications submitted yet.</p>
              ) : (
                <div className="table-responsive">
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead style={{ background: T.mutedBg }}>
                      <tr>
                        {["Request ID", "Leave Type", "Date Range", "Days", "Reason", "Status"].map(h => (
                          <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontWeight: 700, color: T.textSecondary }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {myLeaveRequests.map((req, idx) => {
                        const st = req.status || "pending";
                        const b = st === "approved" ? { bg: "#f0fdf4", text: "#15803d", border: "#bbf7d0", label: "Approved" }
                                : st === "rejected" ? { bg: "#fff1f2", text: "#be123c", border: "#fecdd3", label: "Rejected" }
                                : { bg: "#fffbeb", text: "#b45309", border: "#fde68a", label: "Pending HR Review" };
                        return (
                          <tr key={req.id || idx} style={{ borderTop: "1px solid #f1f5f9" }}>
                            <td style={{ padding: "11px 14px", fontWeight: 700, color: T.textPrimary }}>{req.id || "LV-001"}</td>
                            <td style={{ padding: "11px 14px", color: "#1a73e8", fontWeight: 600 }}>{req.leave_type?.replace("_", " ").toUpperCase()}</td>
                            <td style={{ padding: "11px 14px", color: T.textSecondary }}>{req.from_date} to {req.to_date}</td>
                            <td style={{ padding: "11px 14px", color: T.textSecondary }}>{req.days || 1} day(s)</td>
                            <td style={{ padding: "11px 14px", color: T.textMuted, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{req.reason || "—"}</td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{ padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: b.bg, color: b.text, border: `1px solid ${b.border}` }}>
                                {b.label}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── PROFILE TAB ──────────────────────────────────────────────────── */}
        {activeTab === "profile" && profile && (
          <div className="light-card animate-fade-in" style={{ padding: "24px 28px", display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Avatar + name */}
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ width: 64, height: 64, borderRadius: 20, background: "var(--grad-gemini)", color: "#fff", fontWeight: 900, fontSize: 24, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 6px 18px rgba(26,115,232,.25)" }}>{userInitials}</div>
              <div>
                <h2 style={{ margin: 0, fontSize: 20, fontWeight: 900, color: T.textPrimary }}>{profile.first_name} {profile.last_name}</h2>
                <p style={{ margin: "3px 0 0", fontSize: 13, color: "#1a73e8", fontWeight: 700 }}>{profile.designation} · {profile.department}</p>
              </div>
            </div>

            {/* Details grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14 }}>
              {[
                { title: "Contact Info", rows: [
                  { k: "Employee ID", v: profile.employee_id },
                  { k: "Work Email",  v: profile.email },
                  { k: "Phone",       v: profile.phone || "+91 98765 43210" },
                ]},
                { title: "Work Details", rows: [
                  { k: "Manager",         v: profile.manager_name },
                  { k: "Office Location", v: profile.office_location },
                  { k: "Work Mode",       v: profile.work_mode },
                ]},
                { title: "Career Stats", rows: [
                  { k: "Years at Company",    v: `${profile.years_with_company ?? 2} years` },
                  { k: "Performance Rating",  v: `${profile.performance_rating ?? 4.8} / 5.0` },
                  { k: "Date of Joining",     v: profile.date_of_joining ?? "—" },
                ]},
              ].map(section => (
                <div key={section.title} style={{ padding: "16px 18px", borderRadius: 14, background: T.mutedBg, border: `1px solid ${T.cardBorder}` }}>
                  <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 800, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.08em" }}>{section.title}</p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {section.rows.map(r => (
                      <div key={r.k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                        <span style={{ color: T.textMuted, fontWeight: 500 }}>{r.k}</span>
                        <span style={{ color: T.textPrimary, fontWeight: 700, textAlign: "right", maxWidth: "60%" }}>{r.v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Skills */}
            {profile.skills && profile.skills.length > 0 && (
              <div>
                <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 800, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.08em" }}>Skills</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {profile.skills.map(s => <span key={s} style={{ padding: "4px 12px", borderRadius: 99, background: "#eef2ff", border: "1px solid #c7d2fe", color: "#1a73e8", fontSize: 11, fontWeight: 700 }}>{s}</span>)}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Google Material 3 Bottom Navigation Bar (Mobile / Tablet) ────────── */}
      <div className="google-bottom-nav">
        {(["overview", "attendance", "leaves", "profile", "chatbot"] as const).map(tab => {
          const active = activeTab === tab;
          const meta = TAB_LABELS[tab];
          return (
            <button
              key={tab}
              className={`bottom-nav-item ${active ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
            >
              <div className="nav-icon-pill">
                <Icon name={meta.icon} size={20} color={active ? "#1a73e8" : "#5f6368"} />
              </div>
              <span>{meta.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
