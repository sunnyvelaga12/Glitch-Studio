"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:9000";

// ─── Types ────────────────────────────────────────────────────────────────────
type Tab = "overview" | "knowledge" | "employees" | "documents" | "leaves" | "settings";

interface Doc {
  id: string;
  filename: string;
  size_bytes: number;
  status: "processing" | "ready" | "error";
  uploaded_at: string;
}

interface Employee {
  id: string;
  fullName: string;
  email: string;
  department: string;
  jobTitle: string;
  officeLocation?: string;
  workMode?: string;
  phone?: string;
  managerName?: string;
  employmentStatus?: string;
  employeeId?: string;
}

interface Stats {
  total_employees: number;
  total_documents: number;
  ready_documents: number;
  department_count: number;
  departments: { department: string; count: number }[];
}

interface ChatMsg { role: "user" | "assistant"; content: string; }
interface PreviewRow { fullName: string; email: string; role: string; department: string; }

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

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}
function fmtDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
async function apiFetch(url: string, opts: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const res = await fetch(url, { ...opts, headers: { ...(opts.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("token");
        setTimeout(() => {
          window.location.href = "/login?expired=1";
        }, 1800);
      }
      throw new Error("Your session has expired. Redirecting to login...");
    }
    throw new Error(typeof data === "string" ? data : (data?.detail ?? data?.error ?? "Request failed"));
  }
  return data;
}

// ─── Design Tokens ────────────────────────────────────────────────────────────
const T = {
  pageBg:      "#f8fafd", // Google Workspace & Cloud Console canvas
  cardBg:      "#ffffff",
  cardBorder:  "#dadce0", // Google hairline border
  inputBg:     "#f1f3f4", // Google M3 surface tint
  mutedBg:     "#f8f9fa",
  accentBg:    "#e8f0fe", // Google Blue container
  textPrimary: "#1f1f1f", // Google M3 High-emphasis text
  textSecondary:"#444746", // Google M3 Medium-emphasis text
  textMuted:   "#727775", // Google M3 Low-emphasis text
  indigo:      "#0b57d0", // Google M3 Blue
  blue:        "#1a73e8", // Google Blue
  emerald:     "#1e8e3e", // Google Green
  amber:       "#f9ab00", // Google Amber
  rose:        "#d93025", // Google Red
  purple:      "#a142f4", // Google Gemini Purple
  primaryGrad: "linear-gradient(135deg,#1a73e8 0%,#0b57d0 100%)",
  geminiGrad:  "linear-gradient(135deg,#1a73e8 0%,#4285f4 35%,#9c27b0 70%,#ea4335 100%)",
  successGrad: "linear-gradient(135deg,#1e8e3e 0%,#137333 100%)",
  dangerGrad:  "linear-gradient(135deg,#d93025 0%,#b3261e 100%)",
  headerBg:    "rgba(255,255,255,0.92)",
};

// ─── Shared UI Components ─────────────────────────────────────────────────────
function Spinner({ size = 20, color = "#6366f1" }: { size?: number; color?: string }) {
  return (
    <div style={{ width: size, height: size, borderRadius: "50%", border: `2.5px solid ${color}22`, borderTopColor: color, animation: "spin 0.8s linear infinite", flexShrink: 0 }} />
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div className="light-card" style={{ padding: 20, ...style }}>
      {children}
    </div>
  );
}

function ErrBanner({ msg, onClose }: { msg: string; onClose?: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 14px", borderRadius: 12, background: "#fff1f2", border: "1px solid #fecdd3", color: "#be123c", fontSize: 12 }} className="animate-fade-in">
      <Icon name="warning" size={18} color="#be123c" />
      <span style={{ flex: 1, lineHeight: 1.5 }}>{msg}</span>
      {onClose && <button onClick={onClose} style={{ background: "none", border: "none", color: "#be123c", cursor: "pointer", display: "flex", alignItems: "center" }}><Icon name="close" size={16} /></button>}
    </div>
  );
}

function SuccessBanner({ msg }: { msg: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 14px", borderRadius: 12, background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#15803d", fontSize: 12 }} className="animate-fade-in">
      <Icon name="check_circle" size={18} color="#15803d" />
      <span style={{ lineHeight: 1.5 }}>{msg}</span>
    </div>
  );
}

function StatCard({ label, value, icon, color, colorBg, sub }: { label: string; value: number | string; icon: string; color: string; colorBg: string; sub?: string }) {
  return (
    <div className="light-card light-card-lift" style={{ padding: "18px 20px", display: "flex", alignItems: "center", gap: 14, cursor: "default" }}>
      <div style={{ width: 46, height: 46, borderRadius: 14, background: colorBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <Icon name={icon} size={24} color={color} />
      </div>
      <div>
        <p style={{ margin: 0, fontSize: 24, fontWeight: 800, color: T.textPrimary, lineHeight: 1 }}>{value}</p>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: T.textSecondary, fontWeight: 500 }}>{label}</p>
        {sub && <p style={{ margin: "2px 0 0", fontSize: 10, color: T.textMuted }}>{sub}</p>}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; dot: string }> = {
    ready:      { bg: "var(--google-green-container)", text: "var(--google-green-text)", dot: "var(--google-green)" },
    processing: { bg: "var(--google-yellow-container)", text: "var(--google-yellow-text)", dot: "var(--google-yellow)" },
    error:      { bg: "var(--google-red-container)", text: "var(--google-red-text)", dot: "var(--google-red)" },
    active:     { bg: "var(--google-green-container)", text: "var(--google-green-text)", dot: "var(--google-green)" },
    inactive:   { bg: "#f1f3f4", text: "var(--text-500)", dot: "#dadce0" },
  };
  const c = map[status?.toLowerCase()] ?? map.processing;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 99, background: c.bg, color: c.text, fontSize: 11, fontWeight: 600, border: `1px solid ${c.dot}44`, whiteSpace: "nowrap" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot, display: "inline-block" }} />
      {status ? status.charAt(0).toUpperCase() + status.slice(1) : "—"}
    </span>
  );
}

function DropZone({ accept, label, onFile, file, icon }: { accept: string; label: string; onFile: (f: File) => void; file: File | null; icon: string }) {
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}
      onClick={() => ref.current?.click()}
      style={{
        border: `2px dashed ${over ? T.indigo : file ? T.emerald : "#cbd5e1"}`,
        borderRadius: 14, padding: "28px 20px", textAlign: "center", cursor: "pointer",
        background: over ? "#eef2ff" : file ? "#f0fdf4" : T.inputBg,
        transition: "all 0.2s",
      }}
    >
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }} onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      <div style={{ marginBottom: 6 }}>
        <Icon name={file ? "check_circle" : icon} size={32} color={file ? T.emerald : T.indigo} />
      </div>
      {file ? (
        <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: T.emerald }}>{file.name} · {fmtBytes(file.size)}</p>
      ) : (
        <>
          <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: T.textSecondary }}>Drag & drop or <span style={{ color: T.indigo, textDecoration: "underline" }}>browse</span></p>
          <p style={{ margin: "4px 0 0", fontSize: 11, color: T.textMuted }}>{label}</p>
        </>
      )}
    </div>
  );
}

// ─── Markdown Renderer ────────────────────────────────────────────────────────
function FormattedMarkdown({ content, isUser }: { content: string; isUser: boolean }) {
  if (isUser) return <span style={{ color: "#fff" }}>{content}</span>;
  const lines = content.split("\n");
  const blocks: { type: "text" | "table"; lines: string[] }[] = [];
  let cur: { type: "text" | "table"; lines: string[] } | null = null;
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith("|") && t.endsWith("|")) {
      if (cur?.type === "table") cur.lines.push(t);
      else { if (cur) blocks.push(cur); cur = { type: "table", lines: [t] }; }
    } else {
      if (cur?.type === "table") { blocks.push(cur); cur = null; }
      if (!cur) cur = { type: "text", lines: [line] }; else cur.lines.push(line);
    }
  }
  if (cur) blocks.push(cur);

  function renderText(text: string) {
    return text.split(/(\*\*.*?\*\*|`.*?`)/g).map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} style={{ color: T.textPrimary }}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`") && part.endsWith("`")) return <code key={i} style={{ background: "#eef2ff", color: T.indigo, padding: "1px 6px", borderRadius: 5, fontSize: "0.9em", fontFamily: "monospace" }}>{part.slice(1, -1)}</code>;
      return part;
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {blocks.map((block, bIdx) => {
        if (block.type === "table") {
          const rows = block.lines.filter(l => !l.includes(":---") && !l.includes("---:"));
          if (!rows.length) return null;
          const headers = rows[0].split("|").map(s => s.trim()).filter(Boolean);
          const body = rows.slice(1).map(r => r.split("|").map(s => s.trim()).filter(Boolean));
          return (
            <div key={bIdx} style={{ overflowX: "auto", borderRadius: 10, border: "1px solid #e2e8f0", marginTop: 4 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead style={{ background: "#f8fafc" }}>
                  <tr>{headers.map((h, i) => <th key={i} style={{ padding: "8px 12px", textAlign: "left", color: "#64748b", fontWeight: 700, whiteSpace: "nowrap" }}>{renderText(h)}</th>)}</tr>
                </thead>
                <tbody>
                  {body.map((row, ri) => (
                    <tr key={ri} style={{ borderTop: "1px solid #f1f5f9" }}>
                      {row.map((cell, ci) => <td key={ci} style={{ padding: "8px 12px", color: "#334155" }}>{renderText(cell)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        const txt = block.lines.join("\n");
        if (txt.startsWith("### ")) return <p key={bIdx} style={{ margin: "6px 0 2px", fontSize: 14, fontWeight: 700, color: T.textPrimary }}>{renderText(txt.replace("### ", ""))}</p>;
        if (txt.startsWith("ℹ️") || txt.startsWith("📌")) return <div key={bIdx} style={{ padding: "8px 12px", background: "#eef2ff", border: "1px solid #c7d2fe", borderRadius: 10, color: "#4338ca", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}><Icon name="info" size={16} color="#4338ca" />{renderText(txt.replace(/^[ℹ️📌]\s*/, ""))}</div>;
        return <p key={bIdx} style={{ margin: 0, whiteSpace: "pre-wrap", color: "#334155", fontSize: 13, lineHeight: 1.65 }}>{renderText(txt)}</p>;
      })}
    </div>
  );
}

// ─── TAB: Overview ────────────────────────────────────────────────────────────
function OverviewTab({ companyId }: { companyId: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [passkey, setPasskey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    Promise.all([
      apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/stats`),
      apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/passkey`),
    ]).then(([st, pk]) => { setStats(st); setPasskey(pk.passkey); })
      .catch(e => setErr(e.message)).finally(() => setLoading(false));
  }, [companyId]);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 64 }}><Spinner size={36} /></div>;
  if (err) return <ErrBanner msg={err} />;
  if (!stats) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }} className="animate-fade-in">
      {/* Passkey Banner */}
      {passkey && (
        <div className="light-card" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", background: "linear-gradient(135deg,#eef2ff,#dbeafe)", border: "1px solid #c7d2fe" }}>
          <div style={{ width: 40, height: 40, borderRadius: 12, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 2px 8px rgba(99,102,241,.15)" }}>
            <Icon name="key" size={22} color={T.indigo} />
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <p style={{ margin: 0, fontSize: 10, fontWeight: 800, color: T.indigo, textTransform: "uppercase", letterSpacing: "0.08em" }}>Workspace Passkey</p>
            <p style={{ margin: "2px 0 0", fontSize: 11.5, color: "#6366f1aa" }}>Share with employees to join your workspace</p>
          </div>
          <code style={{ fontSize: 20, fontWeight: 900, letterSpacing: "0.16em", color: T.indigo, fontFamily: "monospace" }}>{passkey}</code>
          <button
            onClick={() => { navigator.clipboard.writeText(passkey); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            style={{ padding: "8px 18px", borderRadius: 20, border: `1px solid ${copied ? "#bbf7d0" : "#c7d2fe"}`, background: copied ? "#f0fdf4" : "#fff", color: copied ? T.emerald : T.indigo, fontSize: 12, fontWeight: 700, cursor: "pointer", transition: "all 0.2s", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 4 }}
          >
            <Icon name={copied ? "check" : "content_copy"} size={16} />
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}

      {/* Stats Grid — Responsive 2x2 on Mobile, 4x1 on Desktop */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 14 }}>
        <StatCard label="Total Employees" value={stats.total_employees} icon="group" color="var(--google-blue)"     colorBg="var(--google-blue-container)" />
        <StatCard label="Policy Documents" value={stats.total_documents} icon="description" color="var(--google-green)"  colorBg="var(--google-green-container)" />
        <StatCard label="Ready for AI"     value={stats.ready_documents} icon="check_circle" color="var(--google-purple)" colorBg="var(--google-purple-container)" />
        <StatCard label="Departments"      value={stats.department_count} icon="corporate_fare" color="var(--google-yellow)"  colorBg="var(--google-yellow-container)" />
      </div>

      {/* Department Bars */}
      {stats.departments.length > 0 && (
        <Card>
          <p style={{ margin: "0 0 16px", fontSize: 15, fontWeight: 700, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="bar_chart" size={20} color={T.indigo} /> Department Breakdown
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {stats.departments.map(d => {
              const pct = stats.total_employees > 0 ? Math.round((d.count / stats.total_employees) * 100) : 0;
              return (
                <div key={d.department}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                    <span style={{ fontSize: 12, color: T.textSecondary, fontWeight: 600 }}>{d.department}</span>
                    <span style={{ fontSize: 11, color: T.textMuted }}>{d.count} · {pct}%</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 99, background: "#f1f5f9", overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", borderRadius: 99, background: T.primaryGrad, transition: "width 0.7s ease" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Google Cloud Enterprise Privacy Card */}
      <div className="light-card" style={{ padding: "16px 22px", display: "flex", alignItems: "center", gap: 14, border: "1px solid #dadce0", background: "#ffffff", boxShadow: "0 1px 3px rgba(60,64,67,0.08)" }}>
        <div style={{ width: 40, height: 40, borderRadius: 12, background: "#e8f0fe", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Icon name="verified_user" size={22} color="#1a73e8" />
        </div>
        <div>
          <p style={{ margin: 0, fontSize: 13.5, fontWeight: 700, color: "#202124" }}>Enterprise Data & Privacy Protection</p>
          <p style={{ margin: "2px 0 0", fontSize: 12, color: "#5f6368" }}>Workspace policy documentation and employee records are protected under enterprise tenant privacy controls.</p>
        </div>
        <span style={{ marginLeft: "auto", padding: "5px 14px", borderRadius: 28, background: "#e6f4ea", border: "1px solid #ceead6", color: "#137333", fontSize: 11.5, fontWeight: 700, whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="check_circle" size={15} color="#137333" /> Active
        </span>
      </div>
    </div>
  );
}

// ─── TAB: AI Knowledge Chat ───────────────────────────────────────────────────
function KnowledgeTab({ companyId }: { companyId: string }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([
    { role: "assistant", content: "Hi! I'm your HR AI Assistant. Ask me anything about your company's policies — leave, attendance, salary, or find employee details." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  async function send(q?: string) {
    const msg = (q ?? input).trim();
    if (!msg || loading) return;
    setInput(""); setErr(null);
    const history = msgs.map(m => ({ role: m.role, content: m.content }));
    setMsgs(prev => [...prev, { role: "user", content: msg }]);
    setLoading(true);
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    try {
      const res = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: msg, history }),
      });

      if (!res.ok) {
        // Fallback to standard /api/chat if streaming is unavailable
        const data = await apiFetch(`${BACKEND_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: msg, history }),
        });
        setMsgs(prev => [...prev, { role: "assistant", content: data.response }]);
        return;
      }

      if (!res.body) {
        throw new Error("Streaming connection body not available.");
      }

      // Initialize assistant message
      setMsgs(prev => [...prev, { role: "assistant", content: "" }]);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.replace("data: ", "").trim();
            if (dataStr === "[DONE]") break;
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.token) {
                accumulated += parsed.token;
                setMsgs(prev => {
                  const copy = [...prev];
                  const lastIdx = copy.length - 1;
                  if (lastIdx >= 0 && copy[lastIdx].role === "assistant") {
                    copy[lastIdx] = { ...copy[lastIdx], content: accumulated };
                  }
                  return copy;
                });
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  const CHIPS = [
    { label: "Leave Policy", icon: "event_note", q: "What is the leave policy?" },
    { label: "WFH Guidelines", icon: "home_work", q: "What is the work from home policy?" },
    { label: "Office Timings", icon: "schedule", q: "What are the office timings?" },
    { label: "HR Department", icon: "badge", q: "Who is in HR department?" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }} className="animate-fade-in">
      <div style={{ padding: "10px 14px", borderRadius: 12, background: "#eef2ff", border: "1px solid #c7d2fe", color: "#4338ca", fontSize: 12, display: "flex", alignItems: "center", gap: 8 }}>
        <Icon name="info" size={18} color="#4338ca" />
        <span>This chat uses AI — answers are pulled from your company's policy documents only.</span>
      </div>

      <Card style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column", height: 560 }}>
        {/* Messages */}
        <div className="light-scrollbar" style={{ flex: 1, overflowY: "auto", padding: "20px 20px 12px", display: "flex", flexDirection: "column", gap: 16 }}>
          {msgs.map((m, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 8, flexDirection: m.role === "user" ? "row-reverse" : "row" }}>
                {m.role === "assistant" && (
                  <div style={{ width: 32, height: 32, borderRadius: "50%", background: T.primaryGrad, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Icon name="auto_awesome" size={18} color="#fff" />
                  </div>
                )}
                <div style={{
                  maxWidth: "82%", padding: "10px 16px", borderRadius: m.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                  background: m.role === "user" ? T.primaryGrad : "#f8faff",
                  border: m.role === "user" ? "none" : "1px solid #e2e8f0",
                  boxShadow: m.role === "user" ? "0 4px 12px rgba(79,70,229,.25)" : "0 1px 4px rgba(0,0,0,.06)",
                  color: m.role === "user" ? "#fff" : T.textPrimary,
                }}>
                  <FormattedMarkdown content={m.content} isUser={m.role === "user"} />
                </div>
              </div>
              {i === 0 && msgs.length === 1 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginLeft: 40, marginTop: 4 }}>
                  {CHIPS.map((c, idx) => (
                    <button key={idx} onClick={() => send(c.q)}
                      style={{ padding: "6px 14px", borderRadius: 99, border: "1.5px solid #c7d2fe", background: "#eef2ff", color: T.indigo, fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "all 0.15s", display: "flex", alignItems: "center", gap: 6 }}
                      onMouseEnter={e => { e.currentTarget.style.background = T.indigo; e.currentTarget.style.color = "#fff"; }}
                      onMouseLeave={e => { e.currentTarget.style.background = "#eef2ff"; e.currentTarget.style.color = T.indigo; }}
                    >
                      <Icon name={c.icon} size={16} />
                      <span>{c.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
              <div style={{ width: 32, height: 32, borderRadius: "50%", background: T.primaryGrad, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon name="auto_awesome" size={18} color="#fff" />
              </div>
              <div style={{ padding: "10px 16px", borderRadius: "18px 18px 18px 4px", background: "#f8faff", border: "1px solid #e2e8f0", display: "flex", gap: 5, alignItems: "center" }}>
                {[0, 1, 2].map(k => <span key={k} style={{ width: 6, height: 6, borderRadius: "50%", background: "#94a3b8", display: "inline-block", animation: `bounce 1.2s ease-in-out ${k * 0.2}s infinite` }} />)}
                <style>{`@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}@keyframes spin{to{transform:rotate(360deg)}}`}</style>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        {err && <div style={{ padding: "0 16px 8px" }}><ErrBanner msg={err} onClose={() => setErr(null)} /></div>}
        {/* Input */}
        <div style={{ padding: "12px 16px 16px", borderTop: "1px solid #f1f5f9", display: "flex", gap: 10 }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Ask about leave policy, find an employee, check timings…"
            className="light-input"
            style={{ flex: 1 }}
          />
          <button
            onClick={() => send()} disabled={!input.trim() || loading}
            style={{ padding: "10px 22px", borderRadius: 12, border: "none", background: T.primaryGrad, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer", opacity: (!input.trim() || loading) ? 0.5 : 1, transition: "opacity 0.15s", display: "flex", alignItems: "center", gap: 6 }}
          >
            <span>Send</span>
            <Icon name="send" size={16} color="#fff" />
          </button>
        </div>
      </Card>
    </div>
  );
}

// ─── TAB: Employees ───────────────────────────────────────────────────────────
function EmployeesTab({ companyId }: { companyId: string }) {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<{ created: number; updated: number; skipped: number } | null>(null);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [sendInvites, setSendInvites] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [editEmp, setEditEmp] = useState<Employee | null>(null);
  const [editForm, setEditForm] = useState<Partial<Employee>>({});
  const [editSaving, setEditSaving] = useState(false);
  const [editSaveErr, setEditSaveErr] = useState<string | null>(null);

  function openEdit(e: Employee) { setEditEmp(e); setEditForm({ ...e }); setEditSaveErr(null); }

  async function saveEdit() {
    if (!editEmp) return;
    setEditSaving(true); setEditSaveErr(null);
    try {
      await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/${editEmp.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(editForm) });
      setEditEmp(null); loadEmployees();
    } catch (e: any) { setEditSaveErr(e.message); } finally { setEditSaving(false); }
  }

  async function deleteEmp() {
    if (!editEmp || !confirm(`Delete ${editEmp.fullName}?`)) return;
    setEditSaving(true);
    try { await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/${editEmp.id}`, { method: "DELETE" }); setEditEmp(null); loadEmployees(); }
    catch (e: any) { setEditSaveErr(e.message); } finally { setEditSaving(false); }
  }

  const loadEmployees = useCallback(() => {
    setLoading(true); setErr(null);
    apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees${search ? `?limit=200&search=${encodeURIComponent(search)}` : "?limit=200"}`)
      .then(d => { setEmployees(d.employees); setTotal(d.total); })
      .catch(e => setErr(e.message)).finally(() => setLoading(false));
  }, [companyId, search]);

  useEffect(() => { loadEmployees(); }, [companyId, search, loadEmployees]);

  async function handlePreview(file: File) {
    setCsvFile(file); setPreview(null); setPreviewErr(null); setImportResult(null); setPreviewLoading(true);
    try { const form = new FormData(); form.append("file", file); const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/preview`, { method: "POST", body: form }); setPreview(d.rows ?? []); }
    catch (e: any) { setPreviewErr(e.message); } finally { setPreviewLoading(false); }
  }

  async function handleImport() {
    if (!csvFile) return;
    setImportLoading(true); setImportErr(null);
    try { const form = new FormData(); form.append("file", csvFile); const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/import?sendInvites=${sendInvites}`, { method: "POST", body: form }); setImportResult(d); setCsvFile(null); setPreview(null); loadEmployees(); }
    catch (e: any) { setImportErr(e.message); } finally { setImportLoading(false); }
  }

  const filtered = employees.filter(e =>
    (e.fullName || "").toLowerCase().includes(search.toLowerCase()) ||
    (e.email || "").toLowerCase().includes(search.toLowerCase()) ||
    (e.department || "").toLowerCase().includes(search.toLowerCase())
  );

  const workModeBadge = (mode?: string) => {
    if (!mode) return { bg: "#f8fafc", text: "#94a3b8" };
    const m = mode.toLowerCase();
    if (m === "remote") return { bg: "#dbeafe", text: "#1d4ed8" };
    if (m === "hybrid") return { bg: "#ede9fe", text: "#6d28d9" };
    return { bg: "#d1fae5", text: "#065f46" };
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }} className="animate-fade-in">
      {/* Toolbar */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name, email or department…" className="light-input" style={{ flex: 1, minWidth: 220 }} />
        <button
          onClick={() => setShowImport(v => !v)}
          style={{ padding: "10px 20px", borderRadius: 12, border: "none", fontWeight: 700, fontSize: 13, cursor: "pointer", transition: "all 0.2s", display: "flex", alignItems: "center", gap: 6,
            background: showImport ? T.mutedBg : T.primaryGrad, color: showImport ? T.textSecondary : "#fff" }}
        >
          <Icon name={showImport ? "arrow_back" : "upload_file"} size={18} color={showImport ? T.textSecondary : "#fff"} />
          <span>{showImport ? "Back to List" : "Import CSV / Excel"}</span>
        </button>
      </div>

      {showImport ? (
        <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <p style={{ margin: "0 0 4px", fontWeight: 700, fontSize: 15, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="upload_file" size={20} color={T.indigo} /> Import Employees via CSV / Excel
            </p>
            <p style={{ margin: 0, fontSize: 12, color: T.textMuted }}>Columns: <code style={{ background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, fontSize: 11, color: T.indigo }}>first_name, last_name, email, department, designation, manager_name, work_mode</code></p>
          </div>
          {previewErr && <ErrBanner msg={previewErr} onClose={() => setPreviewErr(null)} />}
          {importErr && <ErrBanner msg={importErr} onClose={() => setImportErr(null)} />}
          {importResult && <SuccessBanner msg={`Import complete — Created: ${importResult.created} | Updated: ${importResult.updated} | Skipped: ${importResult.skipped}`} />}
          <DropZone accept=".csv,.xlsx,.xls,text/csv,text/plain,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" label="CSV or Excel (.csv, .xlsx) — drag & drop or click to browse" onFile={handlePreview} file={csvFile} icon="table_chart" />
          {previewLoading && <div style={{ display: "flex", justifyContent: "center", padding: 16 }}><Spinner /></div>}
          {preview && preview.length > 0 && (
            <div>
              <p style={{ margin: "0 0 10px", fontSize: 13, color: T.textSecondary, fontWeight: 600 }}>Preview ({preview.length} rows) — <span style={{ color: T.emerald }}>ready to import</span></p>
              <div style={{ overflowX: "auto", borderRadius: 10, border: `1px solid ${T.cardBorder}` }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead style={{ background: T.mutedBg }}>
                    <tr>{["Full Name", "Email", "Designation", "Department"].map(h => <th key={h} style={{ padding: "8px 14px", textAlign: "left", color: T.textSecondary, fontWeight: 600 }}>{h}</th>)}</tr>
                  </thead>
                  <tbody>{preview.map((row, i) => (
                    <tr key={i} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "8px 14px", fontWeight: 600, color: T.textPrimary }}>{row.fullName || "—"}</td>
                      <td style={{ padding: "8px 14px", color: T.textSecondary }}>{row.email || "—"}</td>
                      <td style={{ padding: "8px 14px", color: T.textSecondary }}>{row.role || "—"}</td>
                      <td style={{ padding: "8px 14px", color: T.textSecondary }}>{row.department || "—"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 13, color: T.textSecondary, cursor: "pointer" }}>
                <input type="checkbox" checked={sendInvites} onChange={e => setSendInvites(e.target.checked)} />
                Send email invitations to new employees
              </label>
              <button onClick={handleImport} disabled={importLoading}
                style={{ marginTop: 12, width: "100%", padding: "12px 0", borderRadius: 12, border: "none", background: T.successGrad, color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", opacity: importLoading ? 0.6 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
              >{importLoading ? <><Spinner size={14} color="#fff" /> Importing…</> : <><Icon name="rocket_launch" size={18} color="#fff" /> Import All {preview.length}+ Employees</>}</button>
            </div>
          )}
          {preview && preview.length === 0 && <ErrBanner msg="No valid rows found. Check your file has email, first_name, last_name columns." />}
        </Card>
      ) : (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "12px 20px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <p style={{ margin: 0, fontSize: 13, color: T.textMuted }}>Showing <strong style={{ color: T.textPrimary }}>{filtered.length}</strong> of {total} employees</p>
            <span style={{ fontSize: 11, color: T.textMuted, background: T.mutedBg, padding: "3px 10px", borderRadius: 99, border: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 4 }}>
              <Icon name="lock" size={14} color={T.textMuted} /> Company-isolated data
            </span>
          </div>
          {loading ? <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spinner size={28} /></div>
          : err ? <div style={{ padding: 16 }}><ErrBanner msg={err} /></div>
          : filtered.length === 0 ? (
            <div style={{ padding: 48, textAlign: "center", color: T.textMuted, fontSize: 14 }}>{employees.length === 0 ? "No employees yet. Use Import CSV to add your team." : "No employees match your search."}</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead style={{ background: T.mutedBg }}>
                  <tr>{["Employee", "Email", "Department", "Designation", "Location", "Mode"].map(h => (
                    <th key={h} style={{ padding: "11px 16px", textAlign: "left", fontWeight: 600, color: T.textSecondary, fontSize: 12, whiteSpace: "nowrap" }}>{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {filtered.map(emp => {
                    const badge = workModeBadge((emp as any).workMode);
                    return (
                      <tr key={emp.id} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer", transition: "background 0.15s" }}
                        onClick={() => openEdit(emp)}
                        onMouseEnter={e => (e.currentTarget.style.background = "#f8faff")}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <div style={{ width: 34, height: 34, borderRadius: "50%", background: T.primaryGrad, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 13, flexShrink: 0 }}>
                              {(emp.fullName || "?").charAt(0).toUpperCase()}
                            </div>
                            <div>
                              <div style={{ fontWeight: 700, color: T.textPrimary }}>{emp.fullName}</div>
                              {emp.employeeId && <div style={{ fontSize: 11, color: T.textMuted }}>{emp.employeeId}</div>}
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "12px 16px", color: T.textSecondary }}>{emp.email}</td>
                        <td style={{ padding: "12px 16px", color: T.textSecondary }}>{emp.department || "—"}</td>
                        <td style={{ padding: "12px 16px", color: T.textSecondary }}>{(emp as any).jobTitle || "—"}</td>
                        <td style={{ padding: "12px 16px", color: T.textSecondary }}>{(emp as any).officeLocation || "—"}</td>
                        <td style={{ padding: "12px 16px" }}>
                          {(emp as any).workMode
                            ? <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 99, background: badge.bg, color: badge.text }}>{(emp as any).workMode}</span>
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Edit Drawer */}
      {editEmp && (
        <>
          <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.3)", zIndex: 100, backdropFilter: "blur(3px)" }} onClick={() => setEditEmp(null)} />
          <div className="animate-slide-in-right" style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: 400, maxWidth: "90vw", background: "#fff", zIndex: 101, boxShadow: "-6px 0 32px rgba(99,102,241,.12)", display: "flex", flexDirection: "column", borderLeft: "1px solid #e2e8f0" }}>
            <div style={{ padding: "20px 24px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="edit" size={20} color={T.indigo} /> Edit Employee
              </h2>
              <button onClick={() => setEditEmp(null)} style={{ background: "none", border: "none", cursor: "pointer", color: T.textMuted, display: "flex", alignItems: "center" }}><Icon name="close" size={20} /></button>
            </div>
            <div className="light-scrollbar" style={{ padding: 24, flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
              {editSaveErr && <ErrBanner msg={editSaveErr} onClose={() => setEditSaveErr(null)} />}
              {[
                { label: "Full Name", key: "fullName" },
                { label: "Email", key: "email" },
                { label: "Department", key: "department" },
                { label: "Job Title", key: "jobTitle" },
                { label: "Phone", key: "phone" },
                { label: "Manager", key: "managerName" },
                { label: "Location", key: "officeLocation" },
                { label: "Work Mode", key: "workMode" },
                { label: "Status", key: "employmentStatus" },
                { label: "Employee ID", key: "employeeId" },
              ].map(f => (
                <label key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.06em" }}>{f.label}</span>
                  <input value={(editForm as any)[f.key] || ""} onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })} className="light-input" />
                </label>
              ))}
            </div>
            <div style={{ padding: 20, borderTop: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", background: "#fafbff" }}>
              <button onClick={deleteEmp} disabled={editSaving} style={{ padding: "9px 16px", borderRadius: 10, background: "#fff1f2", color: T.rose, border: "1px solid #fecdd3", fontWeight: 700, cursor: "pointer", opacity: editSaving ? 0.5 : 1, fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
                <Icon name="delete" size={16} color={T.rose} /> Delete
              </button>
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => setEditEmp(null)} style={{ padding: "9px 16px", borderRadius: 10, background: "#f8fafc", color: T.textSecondary, border: "1px solid #e2e8f0", fontWeight: 600, cursor: "pointer", fontSize: 13 }}>Cancel</button>
                <button onClick={saveEdit} disabled={editSaving} style={{ padding: "9px 20px", borderRadius: 10, background: T.primaryGrad, color: "#fff", border: "none", fontWeight: 700, cursor: "pointer", opacity: editSaving ? 0.5 : 1, fontSize: 13 }}>{editSaving ? "Saving…" : "Save"}</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── TAB: Documents ───────────────────────────────────────────────────────────
function DocumentsTab({ companyId }: { companyId: string }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploadOk, setUploadOk] = useState<string | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  async function fetchDocs() {
    try { const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/documents`); setDocs(d.documents); setErr(null); }
    catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  useEffect(() => { fetchDocs(); return () => { if (pollingRef.current) clearInterval(pollingRef.current); }; }, [companyId]);
  useEffect(() => {
    const has = docs.some(d => d.status === "processing");
    if (has && !pollingRef.current) pollingRef.current = setInterval(fetchDocs, 3000);
    else if (!has && pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
  }, [docs]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true); setUploadErr(null); setUploadOk(null);
    try {
      const form = new FormData(); form.append("file", file);
      const doc = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/documents`, { method: "POST", body: form });
      setDocs(prev => [doc, ...prev]); setUploadOk(`"${file.name}" uploaded successfully.`); setFile(null);
    } catch (e: any) { setUploadErr(e.message); } finally { setUploading(false); }
  }

  async function handleDelete(docId: string) {
    try { await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/documents/${docId}`, { method: "DELETE" }); setDocs(prev => prev.filter(d => d.id !== docId)); }
    catch (e: any) { setErr(e.message); }
  }

  const fileIconName = (name: string) => name.endsWith(".pdf") ? "picture_as_pdf" : name.endsWith(".docx") ? "article" : "description";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }} className="animate-fade-in">
      <Card style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <p style={{ margin: "0 0 4px", fontWeight: 700, fontSize: 15, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="upload_file" size={20} color={T.indigo} /> Upload Policy Document
          </p>
          <p style={{ margin: 0, fontSize: 12, color: T.textMuted }}>Documents are automatically processed and stored for AI assistant retrieval.</p>
        </div>
        {uploadErr && <ErrBanner msg={uploadErr} onClose={() => setUploadErr(null)} />}
        {uploadOk && <SuccessBanner msg={uploadOk} />}
        <DropZone accept=".pdf,.docx,.txt" label="PDF, DOCX, or TXT — HR policy documents" onFile={setFile} file={file} icon="description" />
        <button onClick={handleUpload} disabled={!file || uploading}
          style={{ padding: "12px 0", borderRadius: 12, border: "none", background: T.primaryGrad, color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", opacity: (!file || uploading) ? 0.5 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
        >{uploading ? <><Spinner size={14} color="#fff" /> Uploading…</> : <><Icon name="cloud_upload" size={18} color="#fff" /> Upload Document</>}</button>
      </Card>

      <Card style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="folder" size={20} color={T.indigo} /> Policy Documents <span style={{ color: T.textMuted, fontWeight: 400, fontSize: 13 }}>({docs.length})</span>
          </p>
        </div>
        {loading ? <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spinner size={28} /></div>
        : err ? <div style={{ padding: 16 }}><ErrBanner msg={err} /></div>
        : docs.length === 0 ? <div style={{ padding: 48, textAlign: "center", color: T.textMuted, fontSize: 14 }}>No documents uploaded yet.</div>
        : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {docs.map((doc, i) => (
              <div key={doc.id} style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 20px", borderTop: i === 0 ? "none" : "1px solid #f1f5f9", transition: "background 0.15s" }}
                onMouseEnter={e => (e.currentTarget.style.background = "#f8faff")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: "#eef2ff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Icon name={fileIconName(doc.filename)} size={20} color={T.indigo} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontWeight: 600, color: T.textPrimary, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</p>
                  <p style={{ margin: "2px 0 0", fontSize: 11, color: T.textMuted }}>{fmtBytes(doc.size_bytes)} · {fmtDate(doc.uploaded_at)}</p>
                </div>
                <StatusBadge status={doc.status} />
                <button onClick={() => handleDelete(doc.id)}
                  style={{ width: 30, height: 30, borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: T.textMuted, flexShrink: 0, transition: "all 0.15s" }}
                  onMouseEnter={e => { e.currentTarget.style.background = "#fff1f2"; e.currentTarget.style.color = T.rose; e.currentTarget.style.borderColor = "#fecdd3"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = "#fff"; e.currentTarget.style.color = T.textMuted; e.currentTarget.style.borderColor = "#e2e8f0"; }}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── TAB: Settings ────────────────────────────────────────────────────────────
function SettingsTab({ companyId }: { companyId: string }) {
  const [profile, setProfile] = useState<{ name: string; logo?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedPk, setCopiedPk] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);
  const [passkey, setPasskey] = useState<string | null>(null);
  const [regenLoading, setRegenLoading] = useState(false);

  useEffect(() => {
    Promise.all([apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}`), apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/passkey`)])
      .then(([prof, pk]) => { setProfile(prof); setCompanyName(prof.name); setPasskey(pk.passkey); })
      .catch(e => setErr(e.message)).finally(() => setLoading(false));
  }, [companyId]);

  async function handleRegenerate() {
    if (!confirm("Are you sure? Old passkey will stop working immediately.")) return;
    setRegenLoading(true);
    try { const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/passkey/regenerate`, { method: "POST" }); setPasskey(d.passkey); }
    catch (e: any) { setErr(e.message); } finally { setRegenLoading(false); }
  }

  async function handleSave() {
    if (!companyName.trim()) return;
    setSaving(true); setSaveErr(null); setSaveOk(false);
    try {
      const form = new FormData(); form.append("companyName", companyName.trim()); if (logoFile) form.append("logo", logoFile);
      await apiFetch(`${BACKEND_URL}/api/hr/companies`, { method: "POST", body: form }); setSaveOk(true); if (logoFile) setLogoFile(null);
    } catch (e: any) { setSaveErr(e.message); } finally { setSaving(false); }
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Spinner size={28} /></div>;
  if (err) return <ErrBanner msg={err} />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }} className="animate-fade-in">
      {/* Company Profile */}
      <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="corporate_fare" size={20} color={T.indigo} /> Company Profile
        </p>
        {saveErr && <ErrBanner msg={saveErr} onClose={() => setSaveErr(null)} />}
        {saveOk && <SuccessBanner msg="Profile updated successfully." />}
        {profile?.logo && (
          <div>
            <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.06em" }}>Current Logo</p>
            <img src={`data:image/png;base64,${profile.logo}`} alt="logo" style={{ height: 52, borderRadius: 10, border: "1px solid #e2e8f0", objectFit: "contain", background: "#f8fafc", padding: 4 }} />
          </div>
        )}
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.06em" }}>Company Name</span>
          <input value={companyName} onChange={e => setCompanyName(e.target.value)} className="light-input" />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: T.textSecondary, textTransform: "uppercase", letterSpacing: "0.06em" }}>Logo {profile?.logo ? "(change)" : "(optional)"}</span>
          <DropZone accept="image/png,image/jpeg,image/svg+xml,image/webp" label="PNG, JPG, SVG — max 2 MB" onFile={setLogoFile} file={logoFile} icon="image" />
        </label>
        <button onClick={handleSave} disabled={saving || !companyName.trim()}
          style={{ padding: "12px 0", borderRadius: 12, border: "none", background: T.primaryGrad, color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", opacity: (saving || !companyName.trim()) ? 0.5 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
        >{saving ? <><Spinner size={14} color="#fff" /> Saving…</> : "Save Changes"}</button>
      </Card>

      {/* Passkey */}
      <Card style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="key" size={20} color={T.indigo} /> Workspace Passkey
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSecondary }}>Share with employees — they use it when signing up to join your workspace.</p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <code style={{ flex: 1, padding: "16px 24px", borderRadius: 14, background: "#eef2ff", border: "2px dashed #c7d2fe", fontSize: 26, color: T.indigo, textAlign: "center", fontWeight: 900, letterSpacing: "0.2em", fontFamily: "monospace" }}>{passkey || "···"}</code>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button onClick={() => { if (passkey) { navigator.clipboard.writeText(passkey); setCopiedPk(true); setTimeout(() => setCopiedPk(false), 2000); } }}
              style={{ padding: "8px 18px", borderRadius: 10, border: `1px solid ${copiedPk ? "#bbf7d0" : "#c7d2fe"}`, background: copiedPk ? "#f0fdf4" : "#fff", color: copiedPk ? T.emerald : T.indigo, fontWeight: 700, fontSize: 13, cursor: "pointer", transition: "all 0.2s", display: "flex", alignItems: "center", gap: 4 }}
            >
              <Icon name={copiedPk ? "check" : "content_copy"} size={16} />
              {copiedPk ? "Copied" : "Copy"}
            </button>
            <button onClick={handleRegenerate} disabled={regenLoading}
              style={{ padding: "8px 18px", borderRadius: 10, border: "1px solid #fecdd3", background: "#fff1f2", color: T.rose, fontWeight: 700, fontSize: 13, cursor: "pointer", opacity: regenLoading ? 0.5 : 1, display: "flex", alignItems: "center", gap: 4 }}
            >
              <Icon name="refresh" size={16} color={T.rose} />
              {regenLoading ? "Regenerating…" : "Regenerate"}
            </button>
          </div>
        </div>
      </Card>

      {/* Company ID */}
      <Card style={{ display: "flex", flexDirection: "column", gap: 12, opacity: 0.75 }}>
        <div>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
            <Icon name="badge" size={20} color={T.indigo} /> Company ID
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSecondary }}>Internal ID used for workspace tenant isolation.</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <code style={{ flex: 1, padding: "10px 14px", borderRadius: 10, background: T.mutedBg, border: "1px solid #e2e8f0", fontSize: 13, color: T.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{companyId}</code>
          <button onClick={() => { navigator.clipboard.writeText(companyId); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            style={{ padding: "10px 16px", borderRadius: 10, border: `1px solid ${copied ? "#bbf7d0" : "#e2e8f0"}`, background: copied ? "#f0fdf4" : "#fff", color: copied ? T.emerald : T.textSecondary, fontWeight: 700, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap", transition: "all 0.2s", display: "flex", alignItems: "center", gap: 4 }}
          >
            <Icon name={copied ? "check" : "content_copy"} size={16} />
            {copied ? "Copied" : "Copy ID"}
          </button>
        </div>
      </Card>
    </div>
  );
}

// ─── TAB: Employee Leave Requests ─────────────────────────────────────────────
interface LeaveRequestItem {
  id: string;
  _id?: string;
  user_id: string;
  employee_name: string;
  employee_email: string;
  employee_id?: string;
  department: string;
  manager_name: string;
  leave_type: string;
  from_date: string;
  to_date: string;
  days: number;
  reason: string;
  status: "pending" | "approved" | "rejected";
  applied_at: string;
  reviewed_by?: string;
  reviewed_at?: string;
}

function LeavesTab({ companyId }: { companyId: string }) {
  const [leaves, setLeaves] = useState<LeaveRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadLeaves = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const data = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/leaves`);
      setLeaves(data || []);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { loadLeaves(); }, [loadLeaves]);

  const handleStatusChange = async (leaveId: string, newStatus: "approved" | "rejected") => {
    setActionLoading(leaveId);
    try {
      await apiFetch(`${BACKEND_URL}/api/hr/leaves/${leaveId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      setLeaves(prev => prev.map(l => (l.id === leaveId || l._id === leaveId) ? { ...l, status: newStatus } : l));
    } catch (e: any) {
      alert(`Error updating leave status: ${e.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const filteredLeaves = leaves.filter(l => filter === "all" ? true : l.status === filter);
  const pendingCount = leaves.filter(l => l.status === "pending").length;
  const approvedCount = leaves.filter(l => l.status === "approved").length;
  const rejectedCount = leaves.filter(l => l.status === "rejected").length;

  const leaveBadge = (st: string) => {
    if (st === "approved") return { bg: "#f0fdf4", text: "#15803d", border: "#bbf7d0", label: "Approved" };
    if (st === "rejected") return { bg: "#fff1f2", text: "#be123c", border: "#fecdd3", label: "Rejected" };
    return { bg: "#fffbeb", text: "#b45309", border: "#fde68a", label: "Pending Approval" };
  };

  const formatLeaveType = (t: string) => {
    if (t === "casual_leave") return "Casual Leave (CL)";
    if (t === "sick_leave") return "Sick Leave (SL)";
    if (t === "privilege_leave") return "Privilege Leave (PL)";
    if (t === "floating_holiday") return "Floating Holiday";
    return t.replace("_", " ").toUpperCase();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }} className="animate-fade-in">
      {err && <ErrBanner msg={err} onClose={() => setErr(null)} />}

      {/* Metrics Header */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(180px,1fr))", gap: 14 }}>
        <StatCard label="Pending Requests" value={pendingCount} icon="pending_actions" color="var(--google-yellow)" colorBg="var(--google-yellow-container)" />
        <StatCard label="Approved Leaves" value={approvedCount} icon="check_circle" color="var(--google-green)" colorBg="var(--google-green-container)" />
        <StatCard label="Rejected Leaves" value={rejectedCount} icon="cancel" color="var(--google-red)" colorBg="var(--google-red-container)" />
        <StatCard label="Total Submissions" value={leaves.length} icon="event_note" color="var(--google-blue)" colorBg="var(--google-blue-container)" />
      </div>

      {/* Main Table Card */}
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {/* Filter bar */}
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.cardBorder}`, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, background: "#fafbff" }}>
          <div>
            <p style={{ margin: 0, fontSize: 15, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="event_available" size={20} color={T.indigo} /> Employee Leave Applications
            </p>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: T.textMuted }}>Review, approve, or reject employee time-off requests for {companyId}.</p>
          </div>
          <div style={{ display: "flex", gap: 6, background: T.mutedBg, padding: 3, borderRadius: 10 }}>
            {(["all", "pending", "approved", "rejected"] as const).map(st => (
              <button key={st} onClick={() => setFilter(st)}
                style={{ padding: "5px 14px", borderRadius: 8, border: "none", fontSize: 12, fontWeight: 700, cursor: "pointer", textTransform: "capitalize", transition: "all 0.15s",
                  background: filter === st ? "#fff" : "transparent",
                  color: filter === st ? T.indigo : T.textSecondary,
                  boxShadow: filter === st ? "0 1px 4px rgba(0,0,0,.08)" : "none"
                }}
              >
                {st} ({st === "all" ? leaves.length : st === "pending" ? pendingCount : st === "approved" ? approvedCount : rejectedCount})
              </button>
            ))}
          </div>
        </div>

        {/* Table Content */}
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, color: T.textMuted }}>
            <Spinner size={20} /><span style={{ fontSize: 13, fontWeight: 600 }}>Loading leave requests…</span>
          </div>
        ) : filteredLeaves.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: T.textMuted }}>
            <Icon name="event_busy" size={36} color={T.textMuted} />
            <p style={{ fontWeight: 700, color: T.textPrimary, fontSize: 14, margin: "8px 0 4px" }}>No leave requests found</p>
            <p style={{ fontSize: 12, margin: 0 }}>No employee leave applications match the selected filter.</p>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead style={{ background: T.mutedBg }}>
                <tr>
                  {["Employee", "Leave Type", "Duration / Dates", "Reason", "Status", "Actions"].map(h => (
                    <th key={h} style={{ padding: "12px 18px", textAlign: "left", fontWeight: 700, color: T.textSecondary, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredLeaves.map((row, idx) => {
                  const b = leaveBadge(row.status);
                  const isBusy = actionLoading === row.id || actionLoading === row._id;
                  return (
                    <tr key={row.id || idx} style={{ borderTop: "1px solid #f1f5f9", transition: "background 0.15s" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "#f8faff")}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "14px 18px" }}>
                        <p style={{ margin: 0, fontWeight: 800, color: T.textPrimary }}>{row.employee_name}</p>
                        <p style={{ margin: "2px 0 0", fontSize: 11, color: T.textMuted }}>{row.department} · {row.employee_email}</p>
                      </td>
                      <td style={{ padding: "14px 18px" }}>
                        <span style={{ padding: "4px 10px", borderRadius: 8, background: "#eef2ff", color: T.indigo, fontWeight: 700, fontSize: 11, border: "1px solid #c7d2fe" }}>
                          {formatLeaveType(row.leave_type)}
                        </span>
                      </td>
                      <td style={{ padding: "14px 18px" }}>
                        <p style={{ margin: 0, fontWeight: 700, color: T.textPrimary }}>{row.from_date} to {row.to_date}</p>
                        <p style={{ margin: "2px 0 0", fontSize: 11, color: T.textMuted }}>{row.days} day(s)</p>
                      </td>
                      <td style={{ padding: "14px 18px", color: T.textSecondary, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {row.reason || "—"}
                      </td>
                      <td style={{ padding: "14px 18px" }}>
                        <span style={{ padding: "4px 12px", borderRadius: 99, fontSize: 11, fontWeight: 700, background: b.bg, color: b.text, border: `1px solid ${b.border}` }}>
                          {b.label}
                        </span>
                      </td>
                      <td style={{ padding: "14px 18px" }}>
                        {row.status === "pending" ? (
                          <div style={{ display: "flex", gap: 8 }}>
                            <button onClick={() => handleStatusChange(row.id || row._id || "", "approved")} disabled={isBusy}
                              style={{ padding: "6px 14px", borderRadius: 8, border: "none", background: T.successGrad, color: "#fff", fontWeight: 700, fontSize: 12, cursor: "pointer", opacity: isBusy ? 0.5 : 1, display: "flex", alignItems: "center", gap: 4 }}
                            >
                              <Icon name="check" size={14} color="#fff" />
                              Approve
                            </button>
                            <button onClick={() => handleStatusChange(row.id || row._id || "", "rejected")} disabled={isBusy}
                              style={{ padding: "6px 14px", borderRadius: 8, border: "1px solid #fecdd3", background: "#fff1f2", color: T.rose, fontWeight: 700, fontSize: 12, cursor: "pointer", opacity: isBusy ? 0.5 : 1, display: "flex", alignItems: "center", gap: 4 }}
                            >
                              <Icon name="close" size={14} color={T.rose} />
                              Reject
                            </button>
                          </div>
                        ) : (
                          <span style={{ fontSize: 11, color: T.textMuted, fontWeight: 500 }}>
                            Reviewed by {row.reviewed_by || "HR"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────────
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview",  label: "Overview",   icon: "analytics" },
  { id: "knowledge", label: "AI Chat",    icon: "auto_awesome" },
  { id: "employees", label: "Employees",  icon: "group" },
  { id: "documents", label: "Documents",  icon: "description" },
  { id: "leaves",    label: "Leaves Category", icon: "event_available" },
  { id: "settings",  label: "Settings",   icon: "settings" },
];

const TAB_DESC: Record<Tab, string> = {
  overview:  "Real-time snapshot of your HR workspace.",
  knowledge: "Test your AI assistant against policy documents.",
  employees: "Import, view and manage your employee directory.",
  documents: "Upload HR policy documents — processed for AI search.",
  leaves:    "Review, approve, or reject employee leave applications.",
  settings:  "Manage company profile and workspace settings.",
};

export default function HrDashboard() {
  const router = useRouter();
  const [companyId, setCompanyId] = useState("");
  const [companyName, setCompanyName] = useState("HR Studio");
  const [hrName, setHrName] = useState("HR Administrator");
  const [hrInitials, setHrInitials] = useState("HR");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("token");
    const role = localStorage.getItem("role");
    const cId = localStorage.getItem("companyId");
    if (!t || role !== "hr_admin" || !cId) { router.push("/login"); return; }
    setCompanyId(cId); setReady(true);
    try {
      const payload = JSON.parse(atob(t.split(".")[1]));
      const name = payload.fullName || payload.name || "HR Administrator";
      setHrName(name);
      const parts = name.split(" ").filter(Boolean);
      setHrInitials(parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : name.slice(0, 2).toUpperCase());
    } catch {}
    apiFetch(`${BACKEND_URL}/api/hr/companies/${cId}`).then(d => { if (d.name) setCompanyName(d.name); }).catch(() => {});
  }, [router]);

  function logout() { ["token","role","companyId"].forEach(k => localStorage.removeItem(k)); router.push("/login"); }

  if (!ready) {
    return (
      <div className="light-page" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, color: T.textSecondary }}>
          <Spinner size={28} /><span style={{ fontSize: 14, fontWeight: 600 }}>Loading Glitch Workspace…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="light-page" style={{ minHeight: "100vh", position: "relative" }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="light-header" style={{ position: "sticky", top: 0, zIndex: 50 }}>
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "0 16px", height: 64, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              className="mobile-menu-btn"
              onClick={() => setMobileNavOpen(v => !v)}
              style={{
                display: "none",
                alignItems: "center",
                justifyContent: "center",
                width: 38,
                height: 38,
                borderRadius: 12,
                border: "1px solid #dadce0",
                background: "#ffffff",
                color: "#3c4043",
                cursor: "pointer",
                marginRight: 4,
              }}
              aria-label="Toggle menu"
            >
              <Icon name={mobileNavOpen ? "close" : "menu"} size={22} />
            </button>
            <div style={{ width: 38, height: 38, borderRadius: 12, background: "var(--grad-gemini)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 14px rgba(26,115,232,.25)", flexShrink: 0 }}>
              <Icon name="auto_awesome" size={20} color="#fff" />
            </div>
            <div>
              <p style={{ margin: 0, fontSize: 10, fontWeight: 900, color: "#1a73e8", textTransform: "uppercase", letterSpacing: "0.12em", lineHeight: 1 }}>Glitch HR</p>
              <p style={{ margin: "2px 0 0", fontSize: 13.5, fontWeight: 800, color: T.textPrimary, lineHeight: 1 }}>{companyName}</p>
            </div>
          </div>

          {/* Right controls — Google Workspace Style */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 12px 4px 4px", borderRadius: 28, background: "#f8fafd", border: "1px solid #dadce0" }}>
              <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--grad-gemini)", color: "#fff", fontWeight: 800, fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" }}>{hrInitials}</div>
              <span className="hide-on-mobile" style={{ fontSize: 12.5, fontWeight: 600, color: "#3c4043" }}>{hrName}</span>
            </div>
            <button onClick={logout}
              style={{ padding: "7px 14px", borderRadius: 28, border: "1px solid #dadce0", background: "#fff", color: "#3c4043", fontWeight: 600, fontSize: 12.5, cursor: "pointer", transition: "all 0.2s", display: "flex", alignItems: "center", gap: 6 }}
              onMouseEnter={e => { e.currentTarget.style.background = "#fce8e6"; e.currentTarget.style.color = "#c5221f"; e.currentTarget.style.borderColor = "#fad2cf"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "#fff"; e.currentTarget.style.color = "#3c4043"; e.currentTarget.style.borderColor = "#dadce0"; }}
            >
              <Icon name="logout" size={16} />
              <span className="hide-on-mobile">Sign out</span>
            </button>
          </div>
        </div>

        {/* Mobile Horizontal Scrollable Tab Pills */}
        <div className="mobile-only" style={{ background: "#ffffff", borderTop: "1px solid #f1f3f4", padding: "6px 12px", overflowX: "auto", scrollbarWidth: "none" }}>
          <div style={{ display: "flex", gap: 6, width: "max-content" }}>
            {TABS.map(tab => {
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "6px 14px",
                    borderRadius: 20,
                    border: active ? "1px solid #c2e7ff" : "1px solid #dadce0",
                    background: active ? "#e8f0fe" : "#ffffff",
                    color: active ? "#1a73e8" : "#5f6368",
                    fontSize: 12,
                    fontWeight: active ? 700 : 500,
                    whiteSpace: "nowrap",
                    cursor: "pointer",
                  }}
                >
                  <Icon name={tab.icon} size={16} color={active ? "#1a73e8" : "#5f6368"} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </header>

      {/* ── Mobile Slide-Over Drawer ────────────────────────────────────────── */}
      {mobileNavOpen && (
        <>
          <div className="mobile-drawer-backdrop" onClick={() => setMobileNavOpen(false)} />
          <div className="mobile-drawer">
            <div style={{ padding: "18px 20px", borderBottom: "1px solid #e0e5ed", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 10, background: "var(--grad-gemini)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Icon name="auto_awesome" size={18} color="#fff" />
                </div>
                <div>
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 900, color: "#1f1f1f" }}>Glitch HR</p>
                  <p style={{ margin: 0, fontSize: 11, color: "#5f6368" }}>{companyName}</p>
                </div>
              </div>
              <button onClick={() => setMobileNavOpen(false)} style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}>
                <Icon name="close" size={22} color="#5f6368" />
              </button>
            </div>
            <nav style={{ padding: "12px 10px", display: "flex", flexDirection: "column", gap: 4, flex: 1, overflowY: "auto" }}>
              {TABS.map(tab => {
                const active = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => { setActiveTab(tab.id); setMobileNavOpen(false); }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "10px 16px",
                      borderRadius: 24,
                      border: "none",
                      background: active ? "#e8f0fe" : "transparent",
                      color: active ? "#1a73e8" : "#3c4043",
                      fontWeight: active ? 700 : 500,
                      fontSize: 13.5,
                      cursor: "pointer",
                      textAlign: "left",
                      width: "100%",
                    }}
                  >
                    <Icon name={tab.icon} size={20} color={active ? "#1a73e8" : "#5f6368"} />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </nav>
            <div style={{ padding: "14px 16px", borderTop: "1px solid #e0e5ed" }}>
              <div style={{ marginBottom: 12, padding: "10px 12px", borderRadius: 12, background: "#f8fafd", border: "1px solid #dadce0" }}>
                <p style={{ margin: 0, fontSize: 10, fontWeight: 700, color: "#5f6368", textTransform: "uppercase" }}>Workspace ID</p>
                <p style={{ margin: "2px 0 0", fontSize: 11, color: "#1a73e8", fontFamily: "monospace", wordBreak: "break-all", fontWeight: 600 }}>{companyId}</p>
              </div>
              <button
                onClick={logout}
                style={{ width: "100%", padding: "10px 16px", borderRadius: 24, border: "1px solid #fad2cf", background: "#fce8e6", color: "#c5221f", fontWeight: 700, fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
              >
                <Icon name="logout" size={18} color="#c5221f" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Main Layout Container ───────────────────────────────────────────── */}
      <div className="mobile-stack" style={{ maxWidth: 1280, margin: "0 auto", padding: "20px 20px 84px", display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* Sidebar — Google Material You 3 Pill Navigation (Hidden on Tablet/Mobile) */}
        <aside className="desktop-sidebar" style={{ width: 210, flexShrink: 0, position: "sticky", top: 84 }}>
          <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {TABS.map(tab => {
              const active = activeTab === tab.id;
              return (
                <button key={tab.id} id={`tab-${tab.id}`} onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 12, padding: "10px 18px", borderRadius: 28,
                    background: active ? "#e8f0fe" : "transparent",
                    color: active ? "#1a73e8" : "#5f6368",
                    border: "none",
                    fontWeight: active ? 700 : 500, fontSize: 13.5, cursor: "pointer", transition: "all 0.2s ease", textAlign: "left", width: "100%",
                  }}
                  onMouseEnter={e => { if (!active) { e.currentTarget.style.background = "#f1f3f4"; e.currentTarget.style.color = "#202124"; } }}
                  onMouseLeave={e => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#5f6368"; } }}
                >
                  <Icon name={tab.icon} size={20} color={active ? "#1a73e8" : "#5f6368"} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Google Cloud Style Workspace Domain Card */}
          <div style={{ marginTop: 24, padding: "14px 16px", borderRadius: 16, background: "#ffffff", border: "1px solid #dadce0", boxShadow: "0 1px 3px rgba(60,64,67,0.08)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "#5f6368", textTransform: "uppercase", letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 4 }}>
                <Icon name="domain" size={14} color="#1a73e8" /> Workspace ID
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 11, color: "#1a73e8", fontFamily: "monospace", wordBreak: "break-all", lineHeight: 1.4, fontWeight: 600 }}>{companyId}</p>
          </div>
        </aside>

        {/* Main Content Area */}
        <main style={{ flex: 1, minWidth: 0, width: "100%" }}>
          <div style={{ marginBottom: 18 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: T.textPrimary, display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name={TABS.find(t => t.id === activeTab)?.icon || "analytics"} size={24} color="#1a73e8" />
              <span>{TABS.find(t => t.id === activeTab)?.label}</span>
            </h1>
            <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textMuted }}>{TAB_DESC[activeTab]}</p>
          </div>

          {activeTab === "overview"  && <OverviewTab  companyId={companyId} />}
          {activeTab === "knowledge" && <KnowledgeTab companyId={companyId} />}
          {activeTab === "employees" && <EmployeesTab companyId={companyId} />}
          {activeTab === "documents" && <DocumentsTab companyId={companyId} />}
          {activeTab === "leaves"    && <LeavesTab    companyId={companyId} />}
          {activeTab === "settings"  && <SettingsTab  companyId={companyId} />}
        </main>
      </div>

      {/* ── Google Material 3 Bottom Navigation Bar (Mobile / Tablet) ────────── */}
      <div className="google-bottom-nav">
        {[
          { id: "overview", label: "Overview", icon: "dashboard" },
          { id: "knowledge", label: "Gemini", icon: "auto_awesome" },
          { id: "employees", label: "Team", icon: "group" },
          { id: "documents", label: "Docs", icon: "description" },
          { id: "leaves", label: "Leaves", icon: "event_available" },
        ].map(item => {
          const active = activeTab === item.id;
          return (
            <button
              key={item.id}
              className={`bottom-nav-item ${active ? "active" : ""}`}
              onClick={() => setActiveTab(item.id as Tab)}
            >
              <div className="nav-icon-pill">
                <Icon name={item.icon} size={20} color={active ? "#1a73e8" : "#5f6368"} />
              </div>
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
