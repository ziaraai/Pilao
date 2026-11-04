"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/logo";
import { Alert, Button, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { AuthContext } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { Me } from "@/lib/types";

const NAV = [
  { href: "/dossiers", label: "Dossiers" },
  { href: "/coffre-fort", label: "Coffre-fort" },
  { href: "/documents", label: "Base documentaire" },
  { href: "/profil", label: "Profil" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useApi<Me>("/auth/me");
  const unauthenticated = me.status === 401;

  useEffect(() => {
    if (unauthenticated)
      router.replace(`/connexion?suite=${encodeURIComponent(pathname)}`);
  }, [unauthenticated, router, pathname]);

  if (!me.data) {
    if (me.error && !unauthenticated) {
      return (
        <div className="mx-auto max-w-md space-y-3 p-8">
          <Alert tone="danger">{me.error}</Alert>
          <Button onClick={me.reload}>Réessayer</Button>
        </div>
      );
    }
    return (
      <div className="p-8">
        <Loading />
      </div>
    );
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    // Full reload on purpose: no data of this session may stay in memory (Cache Components
    // keeps hidden routes alive), which a client-side navigation would not guarantee.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/connexion");
  }

  return (
    <AuthContext.Provider value={{ me: me.data, refresh: me.reload }}>
      <div className="min-h-screen bg-slate-50">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/dossiers" aria-label="Accueil Pilao">
              <Logo className="h-8 w-auto" />
            </Link>
            <nav
              aria-label="Navigation principale"
              className="flex flex-wrap gap-1"
            >
              {NAV.map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium ${active ? "bg-brand-navy text-white" : "text-slate-700 hover:bg-slate-100"}`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="ml-auto flex items-center gap-3 text-sm text-slate-600">
              <span className="hidden sm:inline">{me.data.org.name}</span>
              <Button variant="ghost" onClick={logout}>
                Déconnexion
              </Button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </div>
    </AuthContext.Provider>
  );
}
