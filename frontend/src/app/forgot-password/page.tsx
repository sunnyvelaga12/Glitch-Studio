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

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<"request" | "reset" | "success">("request");
  const [email, setEmail] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  // Pre-warm backend on page mount
  useEffect(() => {
    fetch(`${BACKEND_URL}/health/liveness`, { cache: "no-store" }).catch(() => {});
  }, []);

  async function handleRequestToken(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to process password reset request.");

      setInfoMessage(data.message || "Reset token issued successfully.");
      if (data.resetToken) {
        setResetToken(data.resetToken);
      }
      setStep("reset");
    } catch (err: any) {
      setError(err.message || "Request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!resetToken.trim()) { setError("Please enter your password reset token."); return; }
    if (newPassword.length < 6) { setError("Password must be at least 6 characters."); return; }
    if (newPassword !== confirmPassword) { setError("Passwords do not match."); return; }

    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: resetToken.trim(), newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed to reset password.");

      setStep("success");
    } catch (err: any) {
      setError(err.message || "Reset failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f9", display: "flex", flexDirection: "column", justifyContent: "space-between", alignItems: "center", padding: "24px 16px", fontFamily: "var(--font-sans)" }}>
      <style>{`
        .anim-spin{animation:spin .8s linear infinite}
        @keyframes spin{to{transform:rotate(360deg)}}
      `}</style>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* ── Google Account Recovery Card ────────────────────────────────────── */}
      <div style={{ width: "100%", maxWidth: 450, background: "#ffffff", borderRadius: 28, border: "1px solid #dadce0", padding: "40px", boxSizing: "border-box", margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
            <GlitchLogo size={36} />
            <span style={{ fontSize: 22, fontWeight: 700, color: "#1f1f1f", letterSpacing: "-0.02em" }}>Glitch</span>
          </div>

          <h1 style={{ margin: "0 0 8px", fontSize: 28, fontWeight: 400, color: "#1f1f1f", letterSpacing: "-0.02em" }}>
            {step === "request" && "Account recovery"}
            {step === "reset" && "Reset your password"}
            {step === "success" && "Password reset complete"}
          </h1>
          <p style={{ margin: 0, fontSize: 14, color: "#444746", lineHeight: 1.45 }}>
            {step === "request" && "Recover your Glitch workspace account by entering your work email address"}
            {step === "reset" && "Enter the verification token and choose a new password"}
            {step === "success" && "Your password has been updated. You can now sign in with your new credentials."}
          </p>
        </div>

        {error && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "#fce8e6", border: "1px solid #fad2cf", color: "#b3261e", fontSize: 13, display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
            <Icon name="error" size={18} color="#b3261e" />
            <span>{error}</span>
          </div>
        )}

        {infoMessage && step === "reset" && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "#e8f0fe", border: "1px solid #d2e3fc", color: "#174ea6", fontSize: 12.5, fontWeight: 600, display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
            <Icon name="info" size={18} color="#0b57d0" />
            <span>{infoMessage}</span>
          </div>
        )}

        {/* ── STEP 1: Request ──────────────────────────────────────────────── */}
        {step === "request" && (
          <form onSubmit={handleRequestToken} id="recovery-form" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 6 }}>
                Work email address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="name@company.com"
                style={{
                  width: "100%", height: 52, padding: "0 16px", borderRadius: 8, border: "1px solid #747775",
                  background: "#ffffff", color: "#1f1f1f", fontSize: 15, outline: "none", boxSizing: "border-box"
                }}
                onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
              <Link
                href="/login"
                style={{ color: "#0b57d0", fontSize: 14, fontWeight: 600, textDecoration: "none", padding: "8px 12px", borderRadius: 20 }}
              >
                Back to sign in
              </Link>
              <button
                type="submit"
                disabled={loading}
                style={{
                  height: 44, padding: "0 28px", borderRadius: 22, background: "#0b57d0", color: "#ffffff",
                  border: "none", fontSize: 14, fontWeight: 600, cursor: "pointer", display: "flex",
                  alignItems: "center", justifyContent: "center", gap: 8, opacity: loading ? 0.7 : 1
                }}
              >
                {loading ? "Sending…" : "Next"}
              </button>
            </div>
          </form>
        )}

        {/* ── STEP 2: Reset Form ───────────────────────────────────────────── */}
        {step === "reset" && (
          <form onSubmit={handleResetPassword} id="reset-form" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                Verification token
              </label>
              <input
                type="text"
                required
                value={resetToken}
                onChange={e => setResetToken(e.target.value.toUpperCase())}
                placeholder="Enter token (e.g. A3F8B9C2)"
                style={{
                  width: "100%", height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                  background: "#ffffff", color: "#0b57d0", fontSize: 14, outline: "none", boxSizing: "border-box",
                  fontFamily: "monospace", letterSpacing: "0.08em", fontWeight: 700
                }}
                onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                New password
              </label>
              <div style={{ position: "relative" }}>
                <input
                  type={showPw ? "text" : "password"}
                  required
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  placeholder="••••••••••••"
                  style={{
                    width: "100%", height: 48, padding: "0 40px 0 14px", borderRadius: 8, border: "1px solid #747775",
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

            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444746", marginBottom: 4 }}>
                Confirm new password
              </label>
              <input
                type={showPw ? "text" : "password"}
                required
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="••••••••••••"
                style={{
                  width: "100%", height: 48, padding: "0 14px", borderRadius: 8, border: "1px solid #747775",
                  background: "#ffffff", color: "#1f1f1f", fontSize: 14, outline: "none", boxSizing: "border-box"
                }}
                onFocus={e => { e.currentTarget.style.borderColor = "#0b57d0"; e.currentTarget.style.boxShadow = "0 0 0 1px #0b57d0"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "#747775"; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
              <button
                type="button"
                onClick={() => setStep("request")}
                style={{ background: "none", border: "none", color: "#0b57d0", fontSize: 14, fontWeight: 600, cursor: "pointer", padding: "8px 12px" }}
              >
                Back
              </button>
              <button
                type="submit"
                disabled={loading}
                style={{
                  height: 44, padding: "0 28px", borderRadius: 22, background: "#0b57d0", color: "#ffffff",
                  border: "none", fontSize: 14, fontWeight: 600, cursor: "pointer", display: "flex",
                  alignItems: "center", justifyContent: "center", gap: 8, opacity: loading ? 0.7 : 1
                }}
              >
                {loading ? "Updating…" : "Update Password"}
              </button>
            </div>
          </form>
        )}

        {/* ── STEP 3: Success ─────────────────────────────────────────────── */}
        {step === "success" && (
          <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
            <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#e6f4ea", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid #ceead6" }}>
              <Icon name="check_circle" size={32} color="#1e8e3e" />
            </div>
            <p style={{ margin: 0, fontSize: 14, color: "#1f1f1f", lineHeight: 1.5 }}>
              Your password has been successfully reset. You can now use your new password to sign in.
            </p>
            <button
              onClick={() => router.push("/login")}
              style={{
                width: "100%", height: 44, borderRadius: 22, background: "#0b57d0", color: "#ffffff",
                border: "none", fontSize: 14, fontWeight: 600, cursor: "pointer", marginTop: 8
              }}
            >
              Sign in to Glitch
            </button>
          </div>
        )}
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Footer */}
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
