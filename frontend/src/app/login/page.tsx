"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:9000";

function GlitchLogo({ size = 36 }: { size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.28),
        background: "linear-gradient(135deg, #0b57d0 0%, #1a73e8 60%, #4f46e5 100%)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 4px 14px rgba(11, 87, 208, 0.28)",
        flexShrink: 0,
      }}
    >
      <Icon name="auto_awesome" size={Math.round(size * 0.58)} color="#ffffff" />
    </div>
  );
}

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

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passkey, setPasskey] = useState("");
  const [resolvedCompany, setResolvedCompany] = useState<string | null>(null);
  const [showPw, setShowPw] = useState(false);
  const [role, setRole] = useState<"hr_admin" | "employee">("hr_admin");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  // Pre-warm the backend immediately upon page load to spin up cloud instance if asleep
  useEffect(() => {
    fetch(`${BACKEND_URL}/health/liveness`, { cache: "no-store" }).catch(() => {});
    if (typeof window !== "undefined" && window.location.search.includes("expired=1")) {
      setError("Your session has expired. Please sign in again.");
    }
  }, []);

  const isAdmin = role === "hr_admin";

  async function onSubmit(e: React.FormEvent) {
    if (!isAdmin && !passkey.trim()) {
      setError("Please enter your company's workspace passkey to log in.");
      return;
    }
    setLoading(true); setStatusNotice(null);

    // If server takes longer than 2.5s, inform the user that the cloud service is waking up
    const warmNoticeTimer = setTimeout(() => {
      setStatusNotice("Waking up cloud server (free tier instance spins up on first request, ~25-40s). Hang tight...");
    }, 2500);

    const controller = new AbortController();
    const abortTimeout = setTimeout(() => controller.abort(), 55000);

    try {
      const payload: any = { email: email.trim(), password, role };
      if (!isAdmin && passkey.trim()) {
        payload.passkey = passkey.trim();
      }

      let res: Response;
      try {
        res = await fetch(`${BACKEND_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
      } catch (fetchErr: any) {
        if (fetchErr?.name === "AbortError") {
          throw new Error("Server took too long to wake up. Please click 'Sign in' again to retry.");
        }
        throw new Error("Unable to reach cloud backend. The service may still be booting up — please wait a moment and click 'Sign in' again.");
      }

      if (res.status === 502 || res.status === 503 || res.status === 504) {
        throw new Error("Cloud server is currently starting up (HTTP " + res.status + "). Please try again in 10-15 seconds.");
      }

      let data: any = {};
      if ((res.headers.get("content-type") ?? "").includes("application/json")) {
        data = await res.json();
      }

      if (!res.ok) {
        const m = res.status >= 500
          ? (data?.detail ?? "Server error. Please try again.")
          : res.status === 401
          ? (typeof data?.detail === "string" ? data.detail : "Invalid email or password.")
          : Array.isArray(data?.detail)
          ? data.detail.map((e: any) => e.msg).join("; ")
          : (data?.detail ?? "Login failed.");
        throw new Error(m);
      }
      if (!data.accessToken || !data.role) throw new Error("Unexpected response — missing access token.");
      localStorage.setItem("token", data.accessToken);
      localStorage.setItem("role", data.role);
      localStorage.setItem("companyId", data.companyId ?? "");
      router.push(data.role === "hr_admin" ? "/hr" : "/employees");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      clearTimeout(warmNoticeTimer);
      clearTimeout(abortTimeout);
      setStatusNotice(null);
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f9", display: "flex", flexDirection: "column", justifyContent: "space-between", alignItems: "center", padding: "24px 16px", fontFamily: "var(--font-sans)" }}>
      <style>{`
        .anim-spin{animation:spin .8s linear infinite}
        @keyframes spin{to{transform:rotate(360deg)}}
        @media (max-width: 820px) {
          .google-auth-card { flex-direction: column !important; max-width: 460px !important; min-height: auto !important; padding: 32px 24px !important; }
          .google-auth-left { width: 100% !important; padding: 0 0 24px 0 !important; }
          .google-auth-right { width: 100% !important; padding: 0 !important; }
          .google-auth-actions { flex-direction: column-reverse !important; gap: 16px !important; align-items: stretch !important; }
          .google-auth-actions button { width: 100% !important; }
        }
      `}</style>

      {/* Spacer to center card vertically */}
      <div style={{ flex: 1 }} />

      {/* ── Google Material 3 Unified Auth Card ─────────────────────────────── */}
      <div className="google-auth-card" style={{ width: "100%", maxWidth: 1040, minHeight: 440, background: "#ffffff", borderRadius: 28, border: "1px solid #dadce0", display: "flex", padding: "40px", boxSizing: "border-box", margin: "0 auto" }}>
        
        {/* ── Left Half: Brand & Context ────────────────────────────────────── */}
        <div className="google-auth-left" style={{ width: "50%", paddingRight: 40, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
              <GlitchLogo size={36} />
              <span style={{ fontSize: 22, fontWeight: 700, color: "#1f1f1f", letterSpacing: "-0.02em" }}>Glitch</span>
            </div>

            <h1 style={{ margin: "0 0 10px", fontSize: 36, fontWeight: 400, color: "#1f1f1f", letterSpacing: "-0.02em", lineHeight: 1.15 }}>
              Sign in
            </h1>
            <p style={{ margin: 0, fontSize: 16, color: "#1f1f1f", fontWeight: 400 }}>
              to continue to Glitch HR Workspace
            </p>
          </div>

          <div style={{ marginTop: 32 }}>
            <div style={{ padding: "12px 16px", borderRadius: 16, background: isAdmin ? "#e8f0fe" : "#e6f4ea", border: `1px solid ${isAdmin ? "#d2e3fc" : "#ceead6"}`, display: "flex", alignItems: "center", gap: 12 }}>
              <Icon name={isAdmin ? "admin_panel_settings" : "badge"} size={22} color={isAdmin ? "#1a73e8" : "#1e8e3e"} />
              <div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: isAdmin ? "#174ea6" : "#137333" }}>
                  {isAdmin ? "HR Administrator Mode" : "Employee Portal Mode"}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 12, color: isAdmin ? "#174ea6" : "#137333", opacity: 0.85 }}>
                  {isAdmin ? "Manage policy documents, employees & queries" : "Access your AI policy assistant, attendance & leaves"}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right Half: Google M3 Form Controls ───────────────────────────── */}
        <div className="google-auth-right" style={{ width: "50%", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          
          {/* Role Segmented Buttons */}
          <div>
            <div style={{ display: "flex", background: "#f1f3f4", padding: 4, borderRadius: 28, marginBottom: 24, border: "1px solid #dadce0" }}>
              {[
                { val: "hr_admin", icon: "corporate_fare", label: "HR Admin" },
                { val: "employee", icon: "person", label: "Employee" }
              ].map(r => (
                <button
                  key={r.val}
                  type="button"
                  onClick={() => { setRole(r.val as any); setError(null); }}
                  style={{
                    flex: 1, padding: "8px 14px", borderRadius: 24, border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer",
                    transition: "all 0.2s cubic-bezier(0.2,0,0,1)", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                    background: role === r.val ? "#ffffff" : "transparent",
                    color: role === r.val ? "#0b57d0" : "#5f6368",
                    boxShadow: role === r.val ? "0 1px 3px rgba(60,64,67,0.15), 0 1px 2px rgba(60,64,67,0.1)" : "none",
                  }}
                >
                  <Icon name={r.icon} size={18} color={role === r.val ? "#0b57d0" : "#5f6368"} />
                  <span>{r.label}</span>
                </button>
              ))}
            </div>

            {/* Form */}
            <form onSubmit={onSubmit} id="login-form" style={{ display: "flex", flexDirection: "column", gap: 20 }} noValidate>
              
              {/* Email Outlined Input */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 6 }}>
                  Email or work address
                </label>
                <div style={{ position: "relative" }}>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder={isAdmin ? "hr.admin@company.com" : "employee@company.com"}
                    style={{
                      width: "100%", height: 52, padding: "0 16px", borderRadius: 8, border: "1px solid #747775",
                      background: "#ffffff", color: "#1f1f1f", fontSize: 15, outline: "none", boxSizing: "border-box",
                      transition: "border-color 0.2s, box-shadow 0.2s"
                    }}
                    onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                    onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                  />
                </div>
              </div>

              {/* Password Outlined Input */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#444746" }}>
                    Password
                  </label>
                  <Link href="/forgot-password" style={{ fontSize: 12.5, color: "#0b57d0", fontWeight: 600, textDecoration: "none" }}>
                    Forgot password?
                  </Link>
                </div>
                <div style={{ position: "relative" }}>
                  <input
                    type={showPw ? "text" : "password"}
                    required
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    style={{
                      width: "100%", height: 52, padding: "0 46px 0 16px", borderRadius: 8, border: "1px solid #747775",
                      background: "#ffffff", color: "#1f1f1f", fontSize: 15, outline: "none", boxSizing: "border-box",
                      transition: "border-color 0.2s, box-shadow 0.2s"
                    }}
                    onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                    onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(v => !v)}
                    style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#5f6368", display: "flex", padding: 4 }}
                  >
                    <Icon name={showPw ? "visibility_off" : "visibility"} size={20} />
                  </button>
                </div>
              </div>

              {/* Workspace Passkey for Employee Mode */}
              {!isAdmin && (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#444746", display: "flex", alignItems: "center", gap: 5 }}>
                      <Icon name="key" size={16} color="#0b57d0" />
                      Workspace Passkey
                    </label>
                    {resolvedCompany && (
                      <span style={{ fontSize: 12, color: "#137333", fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>
                        <Icon name="check_circle" size={14} color="#1e8e3e" />
                        {resolvedCompany}
                      </span>
                    )}
                  </div>
                  <div style={{ position: "relative" }}>
                    <input
                      type="text"
                      required
                      value={passkey}
                      onChange={e => {
                        const val = e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, "");
                        setPasskey(val);
                        setResolvedCompany(null);
                        const norm = val.replace(/-/g, "");
                        if (norm.length >= 6) {
                          fetch(`${BACKEND_URL}/api/auth/workspace/${norm}`)
                            .then(r => r.ok ? r.json() : null)
                            .then(d => { if (d?.companyName) setResolvedCompany(d.companyName); })
                            .catch(() => {});
                        }
                      }}
                      placeholder="e.g. 2SATLLD3"
                      style={{
                        width: "100%", height: 52, padding: "0 16px", borderRadius: 8, border: "1px solid #747775",
                        background: "#ffffff", color: "#1f1f1f", fontSize: 15, fontWeight: 600, letterSpacing: "0.08em",
                        textTransform: "uppercase", outline: "none", boxSizing: "border-box",
                        transition: "border-color 0.2s, box-shadow 0.2s"
                      }}
                      onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                      onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                    />
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 11.5, color: "#5f6368" }}>
                    Provided by your HR Administrator to authenticate with your company workspace.
                  </p>
                </div>
              )}

              {statusNotice && (
                <div style={{ padding: "10px 14px", borderRadius: 8, background: "#e8f0fe", border: "1px solid #d2e3fc", color: "#174ea6", fontSize: 13, display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="anim-spin" style={{ width: 16, height: 16, border: "2px solid #1a73e8", borderTopColor: "transparent", borderRadius: "50%", display: "inline-block", flexShrink: 0 }} />
                  <span>{statusNotice}</span>
                </div>
              )}

              {error && (
                <div style={{ padding: "10px 14px", borderRadius: 8, background: "#fce8e6", border: "1px solid #fad2cf", color: "#b3261e", fontSize: 13, display: "flex", alignItems: "flex-start", gap: 8 }}>
                  <Icon name="error" size={18} color="#b3261e" style={{ marginTop: 2, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <span>{error}</span>
                  </div>
                </div>
              )}
            </form>
          </div>

          {/* Bottom Actions Row (Create Account / Next Button) */}
          <div className="google-auth-actions" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 32, paddingTop: 16 }}>
            <Link
              href="/signup"
              style={{ color: "#0b57d0", fontSize: 14, fontWeight: 600, textDecoration: "none", padding: "8px 12px", borderRadius: 20, transition: "background 0.15s" }}
              onMouseEnter={e => (e.currentTarget.style.background = "#f0f4f9")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              Create account
            </Link>

            <button
              type="submit"
              form="login-form"
              disabled={loading}
              style={{
                height: 44, padding: "0 28px", borderRadius: 22, background: "#0b57d0", color: "#ffffff",
                border: "none", fontSize: 14, fontWeight: 600, cursor: "pointer", display: "flex",
                alignItems: "center", justifyContent: "center", gap: 8, transition: "background 0.2s, box-shadow 0.2s",
                boxShadow: "0 1px 3px rgba(60,64,67,0.3)", opacity: loading ? 0.7 : 1
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "#1557d0")}
              onMouseLeave={e => (e.currentTarget.style.background = "#0b57d0")}
            >
              {loading ? (
                <>
                  <span className="anim-spin" style={{ width: 16, height: 16, border: "2px solid rgba(255,255,255,0.4)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block" }} />
                  <span>Signing in…</span>
                </>
              ) : (
                <span>Next</span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* ── Google Style Footer ──────────────────────────────────────────────── */}
      <footer style={{ width: "100%", maxWidth: 1040, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: "#5f6368", marginTop: 24, flexWrap: "wrap", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>English (United States)</span>
          <Icon name="arrow_drop_down" size={18} color="#5f6368" />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <a href="#" style={{ color: "#5f6368", textDecoration: "none" }}>Help</a>
          <a href="#" style={{ color: "#5f6368", textDecoration: "none" }}>Privacy</a>
          <a href="#" style={{ color: "#5f6368", textDecoration: "none" }}>Terms</a>
        </div>
      </footer>
    </div>
  );
}