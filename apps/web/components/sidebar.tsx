"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { FeedbackButton } from "@/components/feedback";
import { Logo } from "@/components/logo";

type IconName =
  | "dashboard"
  | "tenders"
  | "bids"
  | "vault"
  | "documents"
  | "profile"
  | "logout"
  | "menu"
  | "close";

const PATHS: Record<IconName, React.ReactNode> = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  tenders: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  bids: (
    <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-10Z" />
  ),
  vault: (
    <>
      <path d="M12 3.5 5 6.2v5.3c0 4.3 3 7.6 7 9 4-1.4 7-4.7 7-9V6.2L12 3.5Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  documents: (
    <>
      <path d="M7 3.5h7l5 5v10.5a1.5 1.5 0 0 1-1.5 1.5h-10.5a1.5 1.5 0 0 1-1.5-1.5v-14a1.5 1.5 0 0 1 1.5-1.5Z" />
      <path d="M14 3.5v5h5M9 13h6M9 16.5h6" />
    </>
  ),
  profile: (
    <>
      <path d="M4.5 20.5v-15a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v15" />
      <path d="M15.5 9.5h2a2 2 0 0 1 2 2v9M3 20.5h18M8.5 7.5h3M8.5 11h3M8.5 14.5h3" />
    </>
  ),
  logout: (
    <>
      <path d="M14.5 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="m10 16.5-4.5-4.5L10 7.5M5.5 12h10" />
    </>
  ),
  menu: <path d="M4 6.5h16M4 12h16M4 17.5h16" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
};

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-5 w-5 shrink-0"
    >
      {PATHS[name]}
    </svg>
  );
}

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/tableau-de-bord", label: "Tableau de bord", icon: "dashboard" },
  { href: "/annonces", label: "Annonces", icon: "tenders" },
  { href: "/dossiers", label: "Dossiers", icon: "bids" },
  { href: "/coffre-fort", label: "Coffre-fort", icon: "vault" },
  { href: "/documents", label: "Base documentaire", icon: "documents" },
  { href: "/profil", label: "Profil", icon: "profile" },
];

/** The main menu: a column on the left of the screen; on a phone, a top bar that opens it. */
export function Sidebar({
  orgName,
  onLogout,
}: {
  orgName: string;
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
        className={`${open ? "flex" : "hidden"} fixed inset-y-0 left-0 z-40 w-64 flex-col border-r border-slate-200 bg-white lg:sticky lg:top-0 lg:z-auto lg:flex lg:h-screen lg:w-60 lg:shrink-0`}
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
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={close}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ${active ? "bg-brand-navy text-white" : "text-slate-700 hover:bg-slate-100"}`}
              >
                <Icon name={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="space-y-3 border-t border-slate-200 p-4">
          <FeedbackButton className="w-full" />
          <p
            className="truncate px-1 text-sm font-medium text-slate-700"
            title={orgName}
          >
            {orgName}
          </p>
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold text-brand-navy hover:bg-slate-100"
          >
            <Icon name="logout" />
            Déconnexion
          </button>
        </div>
      </aside>
    </>
  );
}
