"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // The /admin login page itself is always accessible
    if (pathname === "/admin") {
      setChecked(true);
      return;
    }

    // All other /admin/* routes require a valid admin token in sessionStorage
    const token = sessionStorage.getItem("adminToken");
    if (!token) {
      router.replace("/admin");
    } else {
      setChecked(true);
    }
  }, [pathname, router]);

  if (!checked) {
    return (
      <div className="min-h-screen admin-bg flex items-center justify-center">
        <div className="admin-spinner" />
      </div>
    );
  }

  return (
    <>
      <style>{`
        :root {
          --admin-accent: #7c3aed;
          --admin-accent-light: #a78bfa;
          --admin-bg: #0a0a0f;
          --admin-surface: rgba(255,255,255,0.04);
          --admin-border: rgba(255,255,255,0.08);
          --admin-text: #f1f5f9;
          --admin-muted: #94a3b8;
          --admin-success: #10b981;
          --admin-error: #ef4444;
          --admin-warning: #f59e0b;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        .admin-bg {
          background: var(--admin-bg);
          background-image:
            radial-gradient(ellipse 80% 50% at 50% -20%, rgba(124,58,237,0.15) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 80%, rgba(59,130,246,0.06) 0%, transparent 50%);
          min-height: 100vh;
          font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
          color: var(--admin-text);
        }

        .admin-glass {
          background: var(--admin-surface);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border: 1px solid var(--admin-border);
          border-radius: 16px;
        }

        .admin-spinner {
          width: 36px; height: 36px;
          border: 3px solid rgba(124,58,237,0.2);
          border-top-color: var(--admin-accent);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
      <div className="admin-bg">
        {children}
      </div>
    </>
  );
}
