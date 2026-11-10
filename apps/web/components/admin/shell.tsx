"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icon";
import { Logo } from "@/components/logo";
import { Alert, Button, Loading } from "@/components/ui";
import { ADMIN_NAV, adminSignInPath } from "@/lib/admin";
import { AdminAuthContext } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { AdminMe } from "@/lib/types";

/**
 * The frame of the administration: a navy menu, so that it is never mistaken for a company's
 * space. It needs a super admin session; without one, the sign-in page.
 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useApi<AdminMe>("/admin/auth/me");
  const [open, setOpen] = useState(false);
  const unauthenticated = me.status === 401;

  useEffect(() => {
    if (unauthenticated)
      router.replace(
        adminSignInPath(window.location.pathname, window.location.search),
      );
  }, [unauthenticated, router]);

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
    await api("/admin/auth/logout", { method: "POST" }).catch(() => undefined);
    // Full reload on purpose: nothing of this session may stay in memory.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/admin/connexion");
  }

  const close = () => setOpen(false);
  const isActive = (href: string) =>
    href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);

  return (
    <AdminAuthContext.Provider value={{ me: me.data }}>
      <div className="min-h-screen bg-slate-100 lg:flex">
        <div className="sticky top-0 z-20 flex items-center justify-between bg-brand-navy px-4 py-3 text-white lg:hidden">
          <span className="text-sm font-bold uppercase tracking-wider text-brand-green">
            Administration Pilao
          </span>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm font-semibold hover:bg-white/10"
            aria-expanded={open}
            aria-controls="admin-menu"
            onClick={() => setOpen((o) => !o)}
          >
            <Icon name={open ? "close" : "menu"} />
            Menu
          </button>
        </div>
        {open && (
          <div
            className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
            aria-hidden="true"
            onClick={close}
          />
        )}
        <aside
          id="admin-menu"
          className={`${open ? "flex" : "hidden"} fixed inset-y-0 left-0 z-40 w-64 flex-col bg-brand-navy text-slate-200 lg:sticky lg:top-0 lg:z-auto lg:flex lg:h-screen lg:w-60 lg:shrink-0`}
        >
          <div className="px-4 pb-2 pt-5">
            <Link
              href="/admin"
              aria-label="Accueil de l'administration"
              onClick={close}
              className="inline-block rounded-lg bg-white px-3 py-2"
            >
              <Logo className="h-7 w-auto" />
            </Link>
            <p className="mt-3 px-1 text-xs font-bold uppercase tracking-widest text-brand-green">
              Administration
            </p>
          </div>
          <nav
            aria-label="Administration"
            className="flex-1 space-y-1 overflow-y-auto px-3 py-2"
          >
            {ADMIN_NAV.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={close}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ${active ? "bg-brand-green font-bold text-brand-navy" : "text-slate-200 hover:bg-white/10"}`}
                >
                  <Icon name={item.icon} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="space-y-2 border-t border-white/15 p-4">
            <p className="truncate px-1 text-sm font-semibold text-white">
              {me.data.full_name || me.data.email}
            </p>
            <p className="px-1 text-xs text-slate-400">Super admin</p>
            <button
              type="button"
              onClick={logout}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold text-white hover:bg-white/10"
            >
              <Icon name="logout" />
              Déconnexion
            </button>
          </div>
        </aside>
        <main className="mx-auto w-full max-w-6xl min-w-0 flex-1 px-4 py-8 lg:px-8">
          {children}
        </main>
      </div>
    </AdminAuthContext.Provider>
  );
}
