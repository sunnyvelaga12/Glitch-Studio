"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:9000";

function GlitchLogo({ size = 36 }: { size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.28,
        background: "linear-gradient(135deg, #2563eb 0%, #4f46e5 50%, #7c3aed 100%)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 4px 14px -2px rgba(79,70,229,0.35)",
        flexShrink: 0,
      }}
    >
      <svg
        width={size * 0.56}
        height={size * 0.56}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M12 2L14.4 8.6L21 11L14.4 13.4L12 20L9.6 13.4L3 11L9.6 8.6L12 2Z"
          fill="white"
          opacity="0.95"
        />
        <circle cx="19" cy="5" r="2" fill="white" opacity="0.8" />
      </svg>
    </div>
  );
}

export default function LogoutPage() {
  const router = useRouter();

  useEffect(() => {
    async function run() {
      try {
        const token = localStorage.getItem("token");
        await fetch(`${BACKEND_URL}/api/auth/logout`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
      } catch {
        // ignore
      } finally {
        localStorage.removeItem("token");
        localStorage.removeItem("role");
        localStorage.removeItem("companyId");
        setTimeout(() => {
          router.push("/login");
        }, 500);
      }
    }
    run();
  }, [router]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f0f4f9",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 16px",
        fontFamily: "'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 440,
          background: "#ffffff",
          borderRadius: 28,
          border: "1px solid #e0e2ec",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 6px 20px -4px rgba(0,0,0,0.06)",
          padding: "40px 36px",
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <div style={{ marginBottom: 20 }}>
          <GlitchLogo size={48} />
        </div>

        <h1
          style={{
            fontSize: 22,
            fontWeight: 500,
            color: "#1f1f1f",
            marginBottom: 8,
            letterSpacing: "-0.2px",
          }}
        >
          Signing out…
        </h1>

        <p
          style={{
            fontSize: 14,
            color: "#444746",
            marginBottom: 28,
            lineHeight: "1.5",
          }}
        >
          Clearing your session and securing your workspace.
        </p>

        {/* M3 Sapphire-to-Indigo Indeterminate Progress Bar */}
        <div
          style={{
            width: "100%",
            height: 4,
            background: "#e8edf5",
            borderRadius: 2,
            overflow: "hidden",
            position: "relative",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              bottom: 0,
              width: "40%",
              background: "linear-gradient(90deg, #2563eb, #4f46e5)",
              borderRadius: 2,
              animation: "glitchM3Indeterminate 1.2s infinite ease-in-out",
            }}
          />
        </div>

        <style>{`
          @keyframes glitchM3Indeterminate {
            0% { left: -40%; width: 30%; }
            50% { left: 30%; width: 50%; }
            100% { left: 100%; width: 30%; }
          }
        `}</style>
      </div>
    </div>
  );
}
