"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:9000";

type Role = "hr_admin" | "employee";

interface PasswordStrength {
  score: number; // 0–4
  label: string;
  color: string;
  checks: { label: string; passed: boolean }[];
}

function checkPasswordStrength(pwd: string): PasswordStrength {
  const checks = [
    { label: "8+ characters", passed: pwd.length >= 8 },
    { label: "Uppercase letter", passed: /[A-Z]/.test(pwd) },
    { label: "Number (0–9)", passed: /[0-9]/.test(pwd) },
    { label: "Special character", passed: /[^a-zA-Z0-9]/.test(pwd) },
  ];
  const score = checks.filter((c) => c.passed).length;
  const labels = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"];
  const colors = ["#ef4444", "#f59e0b", "#eab308", "#22c55e", "#10b981"];
  return { score, label: labels[score], color: colors[score], checks };
}

interface Toast {
  id: string;
  type: "success" | "error";
  title: string;
  message: string;
}

export default function CreateAccountPage() {
  const router = useRouter();

  // Form state
  const [role, setRole] = useState<Role>("hr_admin");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [passkey, setPasskey] = useState("");
  const [resolvedCompany, setResolvedCompany] = useState<string | null>(null);
  const [resolvingPasskey, setResolvingPasskey] = useState(false);

  // UI state
  const [loading, setLoading] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [lastCreated, setLastCreated] = useState<{
    email: string; role: string; company: string;
  } | null>(null);

  const pwdStrength = checkPasswordStrength(password);

  function addToast(type: Toast["type"], title: string, message: string) {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, type, title, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }

  function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return sessionStorage.getItem("adminToken");
  }

  function handleLogout() {
    sessionStorage.removeItem("adminToken");
    router.push("/admin");
  }

  async function resolvePasskey() {
    if (!passkey.trim()) return;
    setResolvingPasskey(true);
    setResolvedCompany(null);
    try {
      const r = await fetch(`${BACKEND_URL}/api/auth/workspace/${passkey.trim()}`);
      if (!r.ok) throw new Error("Invalid passkey");
      const data = await r.json();
      setResolvedCompany(data.companyName);
    } catch {
      addToast("error", "Invalid Passkey", "No workspace found with this passkey.");
      setResolvedCompany(null);
    } finally {
      setResolvingPasskey(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Client-side validation
    if (password !== confirmPassword) {
      addToast("error", "Password Mismatch", "Passwords do not match.");
      return;
    }
    if (pwdStrength.score < 4) {
      addToast("error", "Weak Password", "Please meet all password requirements.");
      return;
    }

    const token = getToken();
    if (!token) {
      addToast("error", "Session Expired", "Your admin session expired. Please log in again.");
      router.push("/admin");
      return;
    }

    setLoading(true);
    try {
      const payload: Record<string, string> = {
        email: email.trim(),
        password,
        role,
        fullName: fullName.trim(),
      };

      if (role === "hr_admin") {
        if (companyName.trim()) payload.companyName = companyName.trim();
        if (companyId.trim()) payload.companyId = companyId.trim();
      } else {
        if (passkey.trim()) payload.passkey = passkey.trim();
        else if (companyId.trim()) payload.companyId = companyId.trim();
      }

      const res = await fetch(`${BACKEND_URL}/api/admin/create-account`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let msg = "Account creation failed.";
        try {
          const data = await res.json();
          if (data?.detail) msg = data.detail;
          if (res.status === 401) {
            sessionStorage.removeItem("adminToken");
            router.push("/admin");
            return;
          }
          if (res.status === 429) msg = "Rate limit exceeded. Please wait 60 seconds.";
        } catch {}
        throw new Error(msg);
      }

      const data = await res.json();
      setLastCreated({
        email: data.email,
        role: data.role,
        company: data.companyName || "N/A",
      });

      addToast(
        "success",
        "Account Created! 🎉",
        `${data.email} (${data.role}) added to ${data.companyName || "system"}`
      );

      // Reset form
      setFullName("");
      setEmail("");
      setPassword("");
      setConfirmPassword("");
      setCompanyName("");
      setCompanyId("");
      setPasskey("");
      setResolvedCompany(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      addToast("error", "Creation Failed", msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        * { box-sizing: border-box; }

        .ca-page {
          min-height: 100vh;
          background: #0a0a0f;
          background-image:
            radial-gradient(ellipse 80% 50% at 50% -20%, rgba(124,58,237,0.15) 0%, transparent 60%),
            radial-gradient(ellipse 50% 40% at 90% 90%, rgba(59,130,246,0.06) 0%, transparent 50%);
          font-family: 'Inter', system-ui, sans-serif;
          color: #f1f5f9;
        }

        /* ── Topbar ── */
        .ca-topbar {
          position: sticky; top: 0; z-index: 50;
          display: flex; align-items: center; justify-content: space-between;
          padding: 0 32px;
          height: 64px;
          background: rgba(10,10,15,0.8);
          backdrop-filter: blur(16px);
          border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .topbar-brand {
          display: flex; align-items: center; gap: 10px;
          font-size: 16px; font-weight: 700; color: #f1f5f9;
          letter-spacing: -0.01em;
        }
        .brand-icon {
          width: 32px; height: 32px;
          background: linear-gradient(135deg, #7c3aed, #6d28d9);
          border-radius: 8px;
          display: flex; align-items: center; justify-content: center;
          font-size: 16px;
        }
        .topbar-right { display: flex; align-items: center; gap: 16px; }
        .topbar-badge {
          background: rgba(124,58,237,0.15);
          border: 1px solid rgba(124,58,237,0.25);
          border-radius: 6px;
          padding: 4px 10px;
          font-size: 12px; font-weight: 600;
          color: #a78bfa;
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }
        .logout-btn {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 8px;
          padding: 6px 14px;
          font-size: 13px; font-weight: 500;
          color: #94a3b8;
          cursor: pointer;
          font-family: inherit;
          transition: all 0.2s;
        }
        .logout-btn:hover { background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.2); color: #fca5a5; }

        /* ── Main layout ── */
        .ca-main {
          max-width: 680px;
          margin: 0 auto;
          padding: 48px 24px 80px;
        }

        .ca-header { margin-bottom: 40px; }
        .ca-header h1 {
          font-size: 30px; font-weight: 700;
          letter-spacing: -0.03em;
          color: #f1f5f9;
          margin-bottom: 8px;
        }
        .ca-header p { font-size: 15px; color: #64748b; line-height: 1.6; }

        /* ── Last created banner ── */
        .last-created {
          background: rgba(16,185,129,0.08);
          border: 1px solid rgba(16,185,129,0.2);
          border-radius: 12px;
          padding: 14px 18px;
          display: flex; align-items: center; gap: 12px;
          margin-bottom: 28px;
          font-size: 14px; color: #6ee7b7;
          animation: fadeSlideIn 0.3s ease;
        }
        .last-created strong { color: #a7f3d0; }

        /* ── Card ── */
        .ca-card {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 20px;
          padding: 36px;
          box-shadow: 0 24px 64px -16px rgba(0,0,0,0.5);
        }

        /* ── Role selector ── */
        .role-tabs {
          display: grid; grid-template-columns: 1fr 1fr;
          gap: 8px; margin-bottom: 32px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          padding: 6px;
        }
        .role-tab {
          border: none; border-radius: 8px;
          padding: 12px 16px;
          font-size: 14px; font-weight: 500;
          cursor: pointer; font-family: inherit;
          transition: all 0.2s;
          display: flex; align-items: center; justify-content: center; gap: 8px;
          color: #64748b;
          background: transparent;
        }
        .role-tab.active {
          background: linear-gradient(135deg, #7c3aed, #6d28d9);
          color: white;
          box-shadow: 0 4px 16px rgba(124,58,237,0.35);
        }
        .role-tab:not(.active):hover { color: #94a3b8; background: rgba(255,255,255,0.04); }

        /* ── Field styles ── */
        .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        @media (max-width: 520px) { .field-row { grid-template-columns: 1fr; } }

        .field {
          display: flex; flex-direction: column; gap: 6px;
          margin-bottom: 16px;
        }
        .field-label {
          font-size: 12px; font-weight: 600;
          color: #64748b;
          letter-spacing: 0.05em; text-transform: uppercase;
        }
        .field-input, .field-select {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 10px;
          padding: 11px 14px;
          font-size: 14px; color: #f1f5f9;
          font-family: inherit;
          outline: none;
          transition: border-color 0.2s, box-shadow 0.2s;
          width: 100%;
        }
        .field-input::placeholder { color: #334155; }
        .field-input:focus, .field-select:focus {
          border-color: rgba(124,58,237,0.5);
          box-shadow: 0 0 0 3px rgba(124,58,237,0.1);
        }
        .field-select { cursor: pointer; }
        .field-select option { background: #1e1b4b; }

        .pw-wrap { position: relative; }
        .pw-wrap .field-input { padding-right: 44px; }
        .pw-toggle {
          position: absolute; right: 12px; top: 50%;
          transform: translateY(-50%);
          background: none; border: none; cursor: pointer;
          color: #475569; font-size: 15px; padding: 4px;
          transition: color 0.2s;
        }
        .pw-toggle:hover { color: #a78bfa; }

        /* ── Password strength ── */
        .strength-bar-wrap {
          height: 4px; border-radius: 99px;
          background: rgba(255,255,255,0.06);
          overflow: hidden; margin-top: 8px;
        }
        .strength-bar {
          height: 100%; border-radius: 99px;
          transition: width 0.3s ease, background-color 0.3s ease;
        }
        .strength-info {
          display: flex; justify-content: space-between; align-items: center;
          margin-top: 6px;
        }
        .strength-label { font-size: 12px; font-weight: 500; }
        .strength-checks { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
        .strength-check {
          font-size: 11px; display: flex; align-items: center; gap: 4px;
          transition: color 0.2s;
        }
        .check-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }

        /* ── Passkey section ── */
        .passkey-row { display: flex; gap: 8px; }
        .passkey-row .field-input { flex: 1; text-transform: uppercase; letter-spacing: 0.08em; }
        .verify-btn {
          background: rgba(124,58,237,0.12);
          border: 1px solid rgba(124,58,237,0.25);
          border-radius: 10px;
          padding: 11px 16px;
          font-size: 13px; font-weight: 600;
          color: #a78bfa;
          cursor: pointer; font-family: inherit;
          transition: all 0.2s; white-space: nowrap;
        }
        .verify-btn:hover:not(:disabled) {
          background: rgba(124,58,237,0.2);
          border-color: rgba(124,58,237,0.4);
        }
        .verify-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .resolved-company {
          display: flex; align-items: center; gap: 8px;
          font-size: 13px; color: #6ee7b7; margin-top: 8px;
          padding: 8px 12px;
          background: rgba(16,185,129,0.07);
          border-radius: 8px;
          border: 1px solid rgba(16,185,129,0.15);
        }

        /* ── Divider ── */
        .section-divider {
          display: flex; align-items: center; gap: 12px;
          margin: 28px 0 24px;
          font-size: 12px; color: #334155; font-weight: 500;
          letter-spacing: 0.05em; text-transform: uppercase;
        }
        .divider-line {
          flex: 1; height: 1px; background: rgba(255,255,255,0.05);
        }

        /* ── Submit ── */
        .submit-btn {
          width: 100%; margin-top: 8px;
          background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
          border: none; border-radius: 12px;
          padding: 14px 20px;
          font-size: 15px; font-weight: 600;
          color: white; cursor: pointer; font-family: inherit;
          transition: all 0.2s;
          box-shadow: 0 4px 24px rgba(124,58,237,0.4);
          position: relative; overflow: hidden;
        }
        .submit-btn::after {
          content: '';
          position: absolute; inset: 0;
          background: linear-gradient(to bottom, rgba(255,255,255,0.08), transparent);
          pointer-events: none;
        }
        .submit-btn:hover:not(:disabled) {
          box-shadow: 0 6px 32px rgba(124,58,237,0.55);
          transform: translateY(-1px);
        }
        .submit-btn:active:not(:disabled) { transform: translateY(0); }
        .submit-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        .spinner-inline {
          display: inline-block; width: 16px; height: 16px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 0.7s linear infinite;
          vertical-align: middle; margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* ── Toast stack ── */
        .toast-stack {
          position: fixed; bottom: 24px; right: 24px;
          display: flex; flex-direction: column; gap: 10px;
          z-index: 9999; pointer-events: none;
        }
        .toast {
          pointer-events: all;
          min-width: 300px; max-width: 380px;
          border-radius: 12px; padding: 14px 16px;
          display: flex; gap: 12px; align-items: flex-start;
          box-shadow: 0 16px 40px rgba(0,0,0,0.5);
          animation: toastIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
          backdrop-filter: blur(12px);
        }
        .toast.success {
          background: rgba(16,185,129,0.12);
          border: 1px solid rgba(16,185,129,0.25);
        }
        .toast.error {
          background: rgba(239,68,68,0.12);
          border: 1px solid rgba(239,68,68,0.25);
        }
        @keyframes toastIn {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
        .toast-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
        .toast-title { font-size: 14px; font-weight: 600; color: #f1f5f9; margin-bottom: 2px; }
        .toast-msg { font-size: 13px; color: #94a3b8; line-height: 1.4; }

        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      {/* Topbar */}
      <header className="ca-topbar">
        <div className="topbar-brand">
          <div className="brand-icon">🛡️</div>
          Glitch Admin
        </div>
        <div className="topbar-right">
          <span className="topbar-badge">Super Admin</span>
          <button className="logout-btn" onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </header>

      <main className="ca-main">
        <div className="ca-header">
          <h1>Create Account</h1>
          <p>
            Provision new HR admin or employee accounts. All data is securely stored
            with bcrypt-hashed passwords and full audit trails.
          </p>
        </div>

        {lastCreated && (
          <div className="last-created">
            <span>✅</span>
            <span>
              Last created: <strong>{lastCreated.email}</strong> as{" "}
              <strong>{lastCreated.role}</strong> in{" "}
              <strong>{lastCreated.company}</strong>
            </span>
          </div>
        )}

        <div className="ca-card">
          <form onSubmit={handleSubmit} noValidate>
            {/* Role selector */}
            <div className="role-tabs">
              <button
                type="button"
                className={`role-tab${role === "hr_admin" ? " active" : ""}`}
                onClick={() => { setRole("hr_admin"); setResolvedCompany(null); }}
                id="role-hr-admin"
              >
                👔 HR Admin
              </button>
              <button
                type="button"
                className={`role-tab${role === "employee" ? " active" : ""}`}
                onClick={() => { setRole("employee"); setResolvedCompany(null); }}
                id="role-employee"
              >
                👤 Employee
              </button>
            </div>

            {/* Personal Info */}
            <div className="field-row">
              <div className="field">
                <label htmlFor="ca-fullname" className="field-label">Full Name</label>
                <input
                  id="ca-fullname"
                  type="text"
                  placeholder="Jane Smith"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="field-input"
                />
              </div>
              <div className="field">
                <label htmlFor="ca-email" className="field-label">Email Address *</label>
                <input
                  id="ca-email"
                  type="email"
                  required
                  placeholder="jane@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="field-input"
                  autoComplete="off"
                />
              </div>
            </div>

            {/* Password */}
            <div className="field">
              <label htmlFor="ca-password" className="field-label">Password *</label>
              <div className="pw-wrap">
                <input
                  id="ca-password"
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="Min 8 chars, upper, number, symbol"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="field-input"
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  className="pw-toggle"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "🙈" : "👁️"}
                </button>
              </div>

              {password && (
                <>
                  <div className="strength-bar-wrap">
                    <div
                      className="strength-bar"
                      style={{
                        width: `${(pwdStrength.score / 4) * 100}%`,
                        background: pwdStrength.color,
                      }}
                    />
                  </div>
                  <div className="strength-info">
                    <span className="strength-label" style={{ color: pwdStrength.color }}>
                      {pwdStrength.label}
                    </span>
                  </div>
                  <div className="strength-checks">
                    {pwdStrength.checks.map((c) => (
                      <span
                        key={c.label}
                        className="strength-check"
                        style={{ color: c.passed ? "#6ee7b7" : "#475569" }}
                      >
                        <span
                          className="check-dot"
                          style={{ background: c.passed ? "#10b981" : "#334155" }}
                        />
                        {c.label}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="field">
              <label htmlFor="ca-confirm" className="field-label">Confirm Password *</label>
              <input
                id="ca-confirm"
                type="password"
                required
                placeholder="Re-enter password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="field-input"
                autoComplete="new-password"
                style={{
                  borderColor:
                    confirmPassword && confirmPassword !== password
                      ? "rgba(239,68,68,0.4)"
                      : undefined,
                }}
              />
              {confirmPassword && confirmPassword !== password && (
                <span style={{ fontSize: 12, color: "#fca5a5", marginTop: 4 }}>
                  Passwords do not match
                </span>
              )}
            </div>

            {/* Company section */}
            <div className="section-divider">
              <span className="divider-line" />
              <span>Company Info</span>
              <span className="divider-line" />
            </div>

            {role === "hr_admin" && (
              <>
                <div className="field">
                  <label htmlFor="ca-company-name" className="field-label">
                    Company Name{" "}
                    <span style={{ color: "#475569", fontSize: 10 }}>(creates new workspace)</span>
                  </label>
                  <input
                    id="ca-company-name"
                    type="text"
                    placeholder="Acme Corp"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    className="field-input"
                  />
                </div>
                <div className="field">
                  <label htmlFor="ca-company-id" className="field-label">
                    Company ID{" "}
                    <span style={{ color: "#475569", fontSize: 10 }}>(join existing — optional)</span>
                  </label>
                  <input
                    id="ca-company-id"
                    type="text"
                    placeholder="Leave blank to auto-create"
                    value={companyId}
                    onChange={(e) => setCompanyId(e.target.value)}
                    className="field-input"
                    style={{ fontFamily: "monospace", fontSize: 13 }}
                  />
                </div>
              </>
            )}

            {role === "employee" && (
              <>
                <div className="field">
                  <label htmlFor="ca-passkey" className="field-label">
                    Workspace Passkey{" "}
                    <span style={{ color: "#475569", fontSize: 10 }}>(or use Company ID below)</span>
                  </label>
                  <div className="passkey-row">
                    <input
                      id="ca-passkey"
                      type="text"
                      placeholder="e.g. ABCD-EFGH"
                      value={passkey}
                      onChange={(e) => { setPasskey(e.target.value); setResolvedCompany(null); }}
                      className="field-input"
                    />
                    <button
                      type="button"
                      className="verify-btn"
                      disabled={resolvingPasskey || !passkey.trim()}
                      onClick={resolvePasskey}
                    >
                      {resolvingPasskey ? "Checking…" : "Verify"}
                    </button>
                  </div>
                  {resolvedCompany && (
                    <div className="resolved-company">
                      <span>✓</span>
                      <span>Joining <strong>{resolvedCompany}</strong></span>
                    </div>
                  )}
                </div>
                <div className="field">
                  <label htmlFor="ca-emp-company-id" className="field-label">
                    Company ID <span style={{ color: "#475569", fontSize: 10 }}>(alternative to passkey)</span>
                  </label>
                  <input
                    id="ca-emp-company-id"
                    type="text"
                    placeholder="Paste company UUID"
                    value={companyId}
                    onChange={(e) => setCompanyId(e.target.value)}
                    className="field-input"
                    style={{ fontFamily: "monospace", fontSize: 13 }}
                  />
                </div>
              </>
            )}

            <button
              type="submit"
              id="create-account-submit"
              disabled={loading || !email || !password || pwdStrength.score < 4 || password !== confirmPassword}
              className="submit-btn"
            >
              {loading ? (
                <><span className="spinner-inline" />Creating Account…</>
              ) : (
                `Create ${role === "hr_admin" ? "HR Admin" : "Employee"} Account`
              )}
            </button>
          </form>
        </div>
      </main>

      {/* Toast notifications */}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            <span className="toast-icon">{t.type === "success" ? "✅" : "❌"}</span>
            <div>
              <div className="toast-title">{t.title}</div>
              <div className="toast-msg">{t.message}</div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
