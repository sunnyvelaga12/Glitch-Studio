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

function getPasswordStrength(pw: string): { score: number; label: string; color: string } {
  if (!pw) return { score: 0, label: "", color: "#dadce0" };
  let score = 0;
  if (pw.length >= 6) score += 1;
  if (pw.length >= 10) score += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score += 1;
  if (/[0-9]/.test(pw) || /[^A-Za-z0-9]/.test(pw)) score += 1;

  if (score <= 1) return { score: 1, label: "Weak", color: "#d93025" };
  if (score <= 3) return { score: 2, label: "Medium", color: "#f9ab00" };
  return { score: 3, label: "Strong", color: "#1e8e3e" };
}

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [role, setRole] = useState<"hr_admin" | "employee">("hr_admin");
  const [companyName, setCompanyName] = useState("");
  const [passkey, setPasskey] = useState("");
  const [resolvedCompany, setResolvedCompany] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  // Pre-warm the backend immediately upon page load
  useEffect(() => {
    fetch(`${BACKEND_URL}/health/liveness`, { cache: "no-store" }).catch(() => {});
  }, []);

  const isAdmin = role === "hr_admin";
  const pwStrength = getPasswordStrength(password);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }
    if (password.length < 6) { setError("Password must be at least 6 characters."); return; }
    setLoading(true); setStatusNotice(null);

    const warmNoticeTimer = setTimeout(() => {
      setStatusNotice("Waking up cloud server (free tier instance spins up on first request, ~25-40s). Hang tight...");
    }, 2500);

    const controller = new AbortController();
    const abortTimeout = setTimeout(() => controller.abort(), 55000);

    try {
      const payload: any = { fullName: fullName.trim(), email: email.trim(), password, role };
      if (isAdmin && companyName.trim()) payload.companyName = companyName.trim();
      else if (!isAdmin && passkey.trim()) payload.passkey = passkey.trim();

      let res: Response;
      try {
        res = await fetch(`${BACKEND_URL}/api/auth/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });
      } catch (fetchErr: any) {
        if (fetchErr?.name === "AbortError") {
          throw new Error("Server took too long to wake up. Please click 'Create account' again to retry.");
        }
        throw new Error("Unable to reach cloud backend. The service may still be booting up — please wait a moment and try again.");
      }

      if (res.status === 502 || res.status === 503 || res.status === 504) {
        throw new Error("Cloud server is currently starting up (HTTP " + res.status + "). Please try again in 10-15 seconds.");
      }

      if (!res.ok) {
        let msg = "Signup failed.";
        try {
          const d = await res.json();
          if (d?.detail) msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
          else if (res.status >= 500) msg = "Server error. Please try again.";
        } catch {}
        throw new Error(msg);
      }
      router.push("/login?signup=success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      clearTimeout(warmNoticeTimer);
      clearTimeout(abortTimeout);
      setStatusNotice(null);
      setLoading(false);
    }
  }

  async function verifyPasskey() {
    if (!passkey.trim()) return;
    setResolving(true); setError(null);
    try {
      const r = await fetch(`${BACKEND_URL}/api/auth/workspace/${passkey.trim()}`);
      if (!r.ok) throw new Error("Invalid passkey");
      const d = await r.json(); setResolvedCompany(d.companyName);
    } catch {
      setError("Invalid or expired workspace passkey."); setResolvedCompany(null);
    } finally {
      setResolving(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f9", display: "flex", flexDirection: "column", justifyContent: "space-between", alignItems: "center", padding: "24px 16px", fontFamily: "var(--font-sans)" }}>
      <style>{`
        .anim-spin{animation:spin .8s linear infinite}
        @keyframes spin{to{transform:rotate(360deg)}}
        @media (max-width: 820px) {
          .google-auth-card { flex-direction: column !important; max-width: 480px !important; padding: 32px 24px !important; }
          .google-auth-left { width: 100% !important; padding: 0 0 24px 0 !important; }
          .google-auth-right { width: 100% !important; padding: 0 !important; }
          .google-auth-actions { flex-direction: column-reverse !important; gap: 16px !important; align-items: stretch !important; }
          .google-auth-actions button { width: 100% !important; }
        }
      `}</style>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* ── Google Material 3 Unified Registration Card ──────────────────────── */}
      <div className="google-auth-card" style={{ width: "100%", maxWidth: 1040, minHeight: 480, background: "#ffffff", borderRadius: 28, border: "1px solid #dadce0", display: "flex", padding: "40px", boxSizing: "border-box", margin: "0 auto" }}>
        
        {/* ── Left Half: Brand & Description ───────────────────────────────── */}
        <div className="google-auth-left" style={{ width: "48%", paddingRight: 40, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
              <GlitchLogo size={36} />
              <span style={{ fontSize: 22, fontWeight: 700, color: "#1f1f1f", letterSpacing: "-0.02em" }}>Glitch</span>
            </div>

            <h1 style={{ margin: "0 0 10px", fontSize: 32, fontWeight: 500, color: "#1f1f1f", letterSpacing: "-0.02em", lineHeight: 1.2 }}>
              {isAdmin ? "Create an HR Workspace" : "Set Employee Password"}
            </h1>
            <p style={{ margin: 0, fontSize: 15, color: "#444746", fontWeight: 400 }}>
              {isAdmin ? "Register your organization to start with smart HR" : "Activate your employee account and create your password using your company passkey"}
            </p>
          </div>

          <div style={{ marginTop: 32 }}>
            <div style={{ padding: "14px 16px", borderRadius: 16, background: isAdmin ? "#e8f0fe" : "#e6f4ea", border: `1px solid ${isAdmin ? "#d2e3fc" : "#ceead6"}`, display: "flex", alignItems: "center", gap: 12 }}>
              <Icon name={isAdmin ? "corporate_fare" : "badge"} size={24} color={isAdmin ? "#1a73e8" : "#1e8e3e"} />
              <div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: isAdmin ? "#174ea6" : "#137333" }}>
                  {isAdmin ? "Organization Admin Workspace" : "Employee Password Setup & Activation"}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: 12, color: isAdmin ? "#174ea6" : "#137333", opacity: 0.85 }}>
                  {isAdmin
                    ? "Generates an isolated tenant workspace with AI policy indexing and unique passkey."
                    : "Employees on the company roster can set their password and activate portal access using their workspace passkey."}
                </p>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16 }}>
              <Icon name="verified_user" size={16} color="#5f6368" />
              <span style={{ fontSize: 12, color: "#5f6368" }}>Enterprise encryption & multi-tenant isolation</span>
            </div>
          </div>
        </div>

        {/* ── Right Half: Google M3 Registration Form ───────────────────────── */}
        <div className="google-auth-right" style={{ width: "52%", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          
          <div>
            {/* Role Switcher */}
            <div style={{ display: "flex", background: "#f1f3f4", padding: 4, borderRadius: 28, marginBottom: 20, border: "1px solid #dadce0" }}>
              {[
                { val: "hr_admin", icon: "corporate_fare", label: "HR Administrator" },
                { val: "employee", icon: "badge", label: "Employee (Set Password)" }
              ].map(r => (
                <button
                  key={r.val}
                  type="button"
                  onClick={() => { setRole(r.val as any); setError(null); setResolvedCompany(null); }}
                  style={{
                    flex: 1, padding: "8px 12px", borderRadius: 24, border: "none", fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                    transition: "all 0.2s cubic-bezier(0.2,0,0,1)", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                    background: role === r.val ? "#ffffff" : "transparent",
                    color: role === r.val ? "#0b57d0" : "#5f6368",
                    boxShadow: role === r.val ? "0 1px 3px rgba(60,64,67,0.15), 0 1px 2px rgba(60,64,67,0.1)" : "none",
                  }}
                >
                  <Icon name={r.icon} size={16} color={role === r.val ? "#0b57d0" : "#5f6368"} />
                  <span>{r.label}</span>
                </button>
              ))}
            </div>

            {/* Form */}
            <form onSubmit={onSubmit} id="signup-form" style={{ display: "flex", flexDirection: "column", gap: 14 }} noValidate>
              
              {/* Full Name */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                  Full name
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={e => setFullName(e.target.value)}
                  placeholder="e.g. Alex Morgan"
                  style={{
                    width: "100%", height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                    background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box",
                    transition: "border-color 0.2s, box-shadow 0.2s"
                  }}
                  onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                  onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                />
              </div>

              {/* Company Name (Admin) */}
              {isAdmin && (
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                    Company / Organization name
                  </label>
                  <input
                    type="text"
                    required
                    value={companyName}
                    onChange={e => setCompanyName(e.target.value)}
                    placeholder="e.g. Acme Corporation"
                    style={{
                      width: "100%", height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                      background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box",
                      transition: "border-color 0.2s, box-shadow 0.2s"
                    }}
                    onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                    onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                  />
                </div>
              )}

              {/* Passkey (Employee) */}
              {!isAdmin && (
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                    Workspace passkey
                  </label>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      type="text"
                      required
                      value={passkey}
                      onChange={e => { setPasskey(e.target.value); setResolvedCompany(null); }}
                      placeholder="e.g. GLITCH-X4Z"
                      style={{
                        flex: 1, height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                        background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box",
                        textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700
                      }}
                      onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                      onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                    />
                    <button
                      type="button"
                      onClick={verifyPasskey}
                      disabled={resolving || !passkey.trim()}
                      style={{
                        padding: "0 18px", height: 48, borderRadius: 8, border: "1px solid #dadce0", background: "#e8f0fe",
                        color: "#0b57d0", fontWeight: 600, fontSize: 13, cursor: "pointer", flexShrink: 0,
                        opacity: resolving || !passkey.trim() ? 0.5 : 1
                      }}
                    >
                      {resolving ? "…" : "Verify"}
                    </button>
                  </div>
                  {resolvedCompany && (
                    <div style={{ marginTop: 6, padding: "6px 12px", borderRadius: 8, background: "#e6f4ea", border: "1px solid #ceead6", color: "#137333", fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
                      <Icon name="check_circle" size={16} color="#137333" />
                      <span>Workspace Verified: <strong>{resolvedCompany}</strong></span>
                    </div>
                  )}
                </div>
              )}

              {/* Work Email */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                  Work email address
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  style={{
                    width: "100%", height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                    background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box",
                    transition: "border-color 0.2s, box-shadow 0.2s"
                  }}
                  onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                  onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                />
              </div>

              {/* Passwords */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                    Password
                  </label>
                  <div style={{ position: "relative" }}>
                    <input
                      type={showPw ? "text" : "password"}
                      required
                      minLength={6}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="••••••••"
                      style={{
                        width: "100%", height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                        background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box"
                      }}
                      onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                      onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                    Confirm
                  </label>
                  <div style={{ position: "relative" }}>
                    <input
                      type={showPw ? "text" : "password"}
                      required
                      minLength={6}
                      value={confirmPassword}
                      onChange={e => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      style={{
                        width: "100%", height: 48, padding: "0 38px 0 14px", borderRadius: 8, border: "1px solid #747775",
                        background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box"
                      }}
                      onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                      onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPw(v => !v)}
                      style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#5f6368", display: "flex", padding: 4 }}
                    >
                      <Icon name={showPw ? "visibility_off" : "visibility"} size={18} />
                    </button>
                  </div>
                </div>
              </div>

              {/* Password strength bar */}
              {password && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                    <span style={{ color: "#5f6368" }}>Password strength:</span>
                    <span style={{ color: pwStrength.color, fontWeight: 700 }}>{pwStrength.label}</span>
                  </div>
                  <div style={{ display: "flex", gap: 4, height: 3 }}>
                    {[1, 2, 3].map(lvl => (
                      <div key={lvl} style={{ flex: 1, borderRadius: 2, background: pwStrength.score >= lvl ? pwStrength.color : "#dadce0" }} />
                    ))}
                  </div>
                </div>
              )}

              {statusNotice && (
                <div style={{ padding: "10px 14px", borderRadius: 8, background: "#e8f0fe", border: "1px solid #d2e3fc", color: "#174ea6", fontSize: 13, display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="anim-spin" style={{ width: 16, height: 16, border: "2px solid #1a73e8", borderTopColor: "transparent", borderRadius: "50%", display: "inline-block", flexShrink: 0 }} />
                  <span>{statusNotice}</span>
                </div>
              )}

              {error && (
                <div style={{ padding: "8px 12px", borderRadius: 8, background: "#fce8e6", border: "1px solid #fad2cf", color: "#b3261e", fontSize: 12.5, display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <Icon name="error" size={16} color="#b3261e" style={{ marginTop: 2, flexShrink: 0 }} />
                  <span>{error}</span>
                </div>
              )}
            </form>
          </div>

          {/* Bottom actions */}
          <div className="google-auth-actions" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 24, paddingTop: 12 }}>
            <Link
              href="/login"
              style={{ color: "#0b57d0", fontSize: 14, fontWeight: 600, textDecoration: "none", padding: "8px 12px", borderRadius: 20, transition: "background 0.15s" }}
              onMouseEnter={e => (e.currentTarget.style.background = "#f0f4f9")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              Sign in instead
            </Link>

            <button
              type="submit"
              form="signup-form"
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
                  <span>{isAdmin ? "Creating Workspace…" : "Setting Password…"}</span>
                </>
              ) : (
                <span>{isAdmin ? "Create Workspace" : "Set Password & Activate"}</span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* ── Footer ──────────────────────────────────────────────────────────── */}
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
