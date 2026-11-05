"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/logo";
import { Alert, Button, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { AuthContext } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { Me, VaultSummary } from "@/lib/types";

const NAV = [
  { href: "/tableau-de-bord", label: "Tableau de bord" },
  { href: "/annonces", label: "Annonces" },
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
            <Link href="/tableau-de-bord" aria-label="Accueil Pilao">
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
        <VaultBanner />
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </div>
    </AuthContext.Provider>
  );
}

/** US-5.2: attestations to renew, on every page until they are replaced. */
function VaultBanner() {
  const summary = useApi<VaultSummary>("/vault/summary");
  const counts = summary.data?.counts;
  if (!counts) return null;
  const expiring = counts.expiring ?? 0;
  const expired = (counts.expired ?? 0) + (counts.mismatch ?? 0);
  if (!expiring && !expired) return null;
  const parts = [
    expired
      ? `${expired} attestation${expired > 1 ? "s" : ""} expirée${expired > 1 ? "s" : ""} ou au nom d'un autre SIREN (exclue${expired > 1 ? "s" : ""} des exports)`
      : null,
    expiring
      ? `${expiring} attestation${expiring > 1 ? "s" : ""} à renouveler dans les 30 jours`
      : null,
  ].filter(Boolean);
  return (
    <div
      role="status"
      className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900"
    >
      {parts.join(" · ")}.{" "}
      <Link href="/coffre-fort" className="font-semibold underline">
        Voir le coffre-fort
      </Link>
    </div>
  );
}
