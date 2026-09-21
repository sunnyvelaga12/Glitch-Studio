"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // If already logged in, redirect straight to create-account
    const token = sessionStorage.getItem("adminToken");
    if (token) {
      router.replace("/admin/create-account");
    }
  }, [router]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      if (!res.ok) {
        let msg = "Invalid credentials.";
        try {
          const data = await res.json();
          if (data?.detail) msg = data.detail;
          if (res.status === 429) msg = "Too many attempts. Please wait 60 seconds.";
        } catch {}
        throw new Error(msg);
      }

      const data = await res.json();
      sessionStorage.setItem("adminToken", data.accessToken);
      router.push("/admin/create-account");
    } catch (err) {
      if (err instanceof TypeError && err.message === "Failed to fetch") {
        setError("Cannot reach the server. Is the backend running?");
      } else {
        setError(err instanceof Error ? err.message : "Login failed.");
      }
    } finally {
      setLoading(false);
    }
  }

  if (!mounted) return null;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        .admin-login-page {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
          background: #0a0a0f;
          background-image:
            radial-gradient(ellipse 80% 50% at 50% -20%, rgba(124,58,237,0.18) 0%, transparent 60%),
            radial-gradient(ellipse 40% 30% at 80% 80%, rgba(59,130,246,0.08) 0%, transparent 50%);
          font-family: 'Inter', system-ui, sans-serif;
        }

        .login-card {
          width: 100%;
          max-width: 440px;
          background: rgba(255,255,255,0.03);
          backdrop-filter: blur(24px);
          -webkit-backdrop-filter: blur(24px);
          border: 1px solid rgba(255,255,255,0.07);
          border-radius: 20px;
          padding: 48px 40px 40px;
          box-shadow:
            0 0 0 1px rgba(124,58,237,0.1),
            0 32px 64px -16px rgba(0,0,0,0.6),
            inset 0 1px 0 rgba(255,255,255,0.05);
          animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .login-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: rgba(124,58,237,0.15);
          border: 1px solid rgba(124,58,237,0.3);
          border-radius: 999px;
          padding: 4px 12px;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #a78bfa;
          margin-bottom: 24px;
        }
        .badge-dot {
          width: 6px; height: 6px;
          background: #a78bfa;
          border-radius: 50%;
          animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }

        .login-title {
          font-size: 26px;
          font-weight: 700;
          color: #f1f5f9;
          letter-spacing: -0.02em;
          line-height: 1.2;
          margin-bottom: 6px;
        }
        .login-subtitle {
          font-size: 14px;
          color: #64748b;
          margin-bottom: 32px;
          line-height: 1.5;
        }

        .field-group {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-bottom: 24px;
        }

        .field-label {
          display: block;
          font-size: 12px;
          font-weight: 600;
          color: #94a3b8;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          margin-bottom: 8px;
        }

        .field-input {
          width: 100%;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 10px;
          padding: 12px 14px;
          font-size: 14px;
          color: #f1f5f9;
          font-family: inherit;
          transition: border-color 0.2s, box-shadow 0.2s;
          outline: none;
        }
        .field-input::placeholder { color: #475569; }
        .field-input:focus {
          border-color: rgba(124,58,237,0.5);
          box-shadow: 0 0 0 3px rgba(124,58,237,0.1);
        }

        .password-wrap { position: relative; }
        .password-wrap .field-input { padding-right: 44px; }
        .show-btn {
          position: absolute;
          right: 12px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          cursor: pointer;
          color: #64748b;
          font-size: 16px;
          padding: 4px;
          transition: color 0.2s;
          line-height: 1;
        }
        .show-btn:hover { color: #a78bfa; }

        .error-box {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          background: rgba(239,68,68,0.08);
          border: 1px solid rgba(239,68,68,0.2);
          border-radius: 10px;
          padding: 12px 14px;
          margin-bottom: 16px;
          font-size: 13px;
          color: #fca5a5;
          animation: fadeIn 0.2s ease;
        }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

        .submit-btn {
          width: 100%;
          background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
          border: none;
          border-radius: 10px;
          padding: 13px 20px;
          font-size: 15px;
          font-weight: 600;
          color: white;
          cursor: pointer;
          font-family: inherit;
          letter-spacing: 0.01em;
          transition: opacity 0.2s, transform 0.15s, box-shadow 0.2s;
          box-shadow: 0 4px 20px rgba(124,58,237,0.4);
          position: relative;
          overflow: hidden;
        }
        .submit-btn::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(to bottom, rgba(255,255,255,0.1), transparent);
          pointer-events: none;
        }
        .submit-btn:hover:not(:disabled) {
          box-shadow: 0 6px 28px rgba(124,58,237,0.5);
          transform: translateY(-1px);
        }
        .submit-btn:active:not(:disabled) { transform: translateY(0); }
        .submit-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        .spinner-inline {
          display: inline-block;
          width: 16px; height: 16px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 0.7s linear infinite;
          vertical-align: middle;
          margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .security-note {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 24px;
          padding-top: 20px;
          border-top: 1px solid rgba(255,255,255,0.05);
          font-size: 12px;
          color: #475569;
        }
        .lock-icon { font-size: 14px; }
      `}</style>

      <div className="admin-login-page">
        <div className="login-card">
          <div className="login-badge">
            <span className="badge-dot" />
            Super Admin Portal
          </div>

          <h1 className="login-title">Admin Sign In</h1>
          <p className="login-subtitle">
            Restricted access — authorized personnel only.
          </p>

          <form onSubmit={handleLogin} noValidate>
            <div className="field-group">
              <div>
                <label htmlFor="admin-email" className="field-label">Email Address</label>
                <input
                  id="admin-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@example.com"
                  className="field-input"
                />
              </div>

              <div>
                <label htmlFor="admin-password" className="field-label">Password</label>
                <div className="password-wrap">
                  <input
                    id="admin-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="field-input"
                  />
                  <button
                    type="button"
                    className="show-btn"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? "🙈" : "👁️"}
                  </button>
                </div>
              </div>
            </div>

            {error && (
              <div className="error-box" role="alert">
                <span>⚠️</span>
                <span>{error}</span>
              </div>
            )}

            <button type="submit" disabled={loading || !email || !password} className="submit-btn">
              {loading ? (
                <><span className="spinner-inline" />Authenticating…</>
              ) : (
                "Sign In to Admin Panel"
              )}
            </button>
          </form>

          <div className="security-note">
            <span className="lock-icon">🔒</span>
            <span>Session expires in 1 hour. Rate limited to 10 requests/min.</span>
          </div>
        </div>
      </div>
    </>
  );
}
