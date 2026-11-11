"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { FeedbackButton } from "@/components/feedback";
import { Icon } from "@/components/icon";
import { Logo } from "@/components/logo";
import { visibleNav } from "@/lib/modules";

/** The main menu: a column on the left of the screen; on a phone, a top bar that opens it. */
export function Sidebar({
  orgName,
  modules,
  onLogout,
}: {
  orgName: string;
  modules: string[];
  onLogout: () => void;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <>
      <div className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <Link href="/tableau-de-bord" aria-label="Accueil Pilao">
          <Logo className="h-7 w-auto" />
        </Link>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm font-semibold text-brand-navy hover:bg-slate-100"
          aria-expanded={open}
          aria-controls="sidebar"
          onClick={() => setOpen((o) => !o)}
        >
          <Icon name={open ? "close" : "menu"} />
          Menu
        </button>
      </div>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/30 lg:hidden"
          aria-hidden="true"
          onClick={close}
        />
      )}
      <aside
        id="sidebar"
        className={`${open ? "flex" : "hidden"} fixed inset-y-0 left-0 z-40 w-64 flex-col border-r border-sidebar-line bg-sidebar lg:sticky lg:top-0 lg:z-auto lg:flex lg:h-screen lg:w-60 lg:shrink-0`}
      >
        <div className="px-5 pb-4 pt-6">
          <Link
            href="/tableau-de-bord"
            aria-label="Accueil Pilao"
            onClick={close}
          >
            <Logo className="h-8 w-auto" />
          </Link>
        </div>
        <nav
          aria-label="Navigation principale"
          className="flex-1 space-y-1 overflow-y-auto px-3 py-2"
        >
          {visibleNav(modules).map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={close}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ${active ? "bg-brand-green font-bold text-brand-navy" : "text-slate-800 hover:bg-white"}`}
              >
                <Icon name={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="space-y-3 border-t border-sidebar-line p-4">
          <FeedbackButton className="w-full" />
          <p
            className="truncate px-1 text-sm font-medium text-slate-800"
            title={orgName}
          >
            {orgName}
          </p>
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold text-brand-navy hover:bg-white"
          >
            <Icon name="logout" />
            Déconnexion
          </button>
        </div>
      </aside>
    </>
  );
}
