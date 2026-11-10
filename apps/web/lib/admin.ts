/** The platform administration (super admin): its screens and where a sign-in may go back. */

import type { IconName } from "@/components/icon";

export const ADMIN_NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/admin", label: "Vue d'ensemble", icon: "dashboard" },
  { href: "/admin/entreprises", label: "Entreprises", icon: "profile" },
  { href: "/admin/couts-ia", label: "Coûts de l'IA", icon: "results" },
  { href: "/admin/technique", label: "Technique", icon: "todo" },
  { href: "/admin/avis", label: "Avis des testeurs", icon: "documents" },
];

const ACCESS_PAGES = ["/admin/connexion", "/admin/activation"];

/** After sign-in: only a screen of the administration, never another site or the way in. */
export function safeAdminNext(value: string | null): string {
  if (!value || value.startsWith("//")) return "/admin";
  const path = value.split(/[?#]/)[0];
  const inside = path === "/admin" || path.startsWith("/admin/");
  return inside && !ACCESS_PAGES.includes(path) ? value : "/admin";
}

/** "2026-11" → "novembre 2026". */
export function monthLabel(month: string): string {
  const [year, index] = month.split("-").map(Number);
  return new Intl.DateTimeFormat("fr-FR", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, index - 1, 1)));
}
