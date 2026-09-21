"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

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

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const role = typeof window !== "undefined" ? localStorage.getItem("role") : null;
    const timer = setTimeout(() => {
      if (role === "hr_admin") router.replace("/hr");
      else if (role === "employee") router.replace("/employees");
      else router.replace("/login");
    }, 800);
    return () => clearTimeout(timer);
  }, [router]);

  return (
    <div className="light-page" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 24, padding: 24 }}>
      <style>{`
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
      `}</style>

      {/* Logo */}
      <div style={{ animation: "float 2.8s ease-in-out infinite" }}>
        <div style={{ width: 68, height: 68, borderRadius: 24, background: "var(--grad-gemini)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 10px 30px rgba(26,115,232,.3)" }}>
          <Icon name="auto_awesome" size={34} color="#fff" />
        </div>
      </div>

      <div style={{ textAlign: "center", animation: "fadeIn .5s ease-out .15s both" }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 900, color: "var(--text-900)", letterSpacing: "-0.02em" }}>Glitch</h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-500)", fontWeight: 500 }}>AI-Powered HR & Policy Intelligence</p>
      </div>

      {/* Glitch Workspace Spinner */}
      <div style={{ animation: "fadeIn .5s ease-out .3s both", display: "flex", alignItems: "center", gap: 10, padding: "8px 18px", borderRadius: 28, background: "#fff", border: "1px solid #dadce0", boxShadow: "0 1px 3px rgba(60,64,67,0.1)" }}>
        <div style={{ width: 18, height: 18, border: "2.5px solid #d3e3fd", borderTopColor: "#0b57d0", borderRadius: "50%", animation: "spin .8s linear infinite" }} />
        <span style={{ fontSize: 12.5, color: "var(--text-500)", fontWeight: 600 }}>Loading workspace…</span>
      </div>
    </div>
  );
}