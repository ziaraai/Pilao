/** The platform administration (super admin): its screens and where a sign-in may go back. */

import type { IconName } from "@/components/icon";
import { ROLES, label } from "@/lib/labels";
import type { AdminOrgUser } from "@/lib/types";

export const ADMIN_NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/admin", label: "Vue d'ensemble", icon: "dashboard" },
  { href: "/admin/entreprises", label: "Entreprises", icon: "profile" },
  { href: "/admin/couts-ia", label: "Coûts de l'IA", icon: "results" },
  { href: "/admin/technique", label: "Technique", icon: "todo" },
  { href: "/admin/avis", label: "Avis des testeurs", icon: "documents" },
  { href: "/admin/journal", label: "Journal", icon: "vault" },
  { href: "/admin/modules", label: "Modules", icon: "start" },
  { href: "/admin/formules", label: "Formules", icon: "bids" },
];

const ACCESS_PAGES = ["/admin/connexion", "/admin/activation"];

/** After sign-in: only a screen of the administration, never another site or the way in. */
export function safeAdminNext(value: string | null): string {
  if (!value || value.startsWith("//")) return "/admin";
  const path = value.split(/[?#]/)[0];
  const inside = path === "/admin" || path.startsWith("/admin/");
  return inside && !ACCESS_PAGES.includes(path) ? value : "/admin";
}

/** The sign-in page, coming back to ``pathname`` + ``search`` afterwards. */
export function adminSignInPath(pathname: string, search: string): string {
  return `/admin/connexion?suite=${encodeURIComponent(pathname + search)}`;
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

/** The platform journal's actions (``platform_audit_logs.action``), in French. */
export const AUDIT_LABELS: Record<string, string> = {
  access_reset: "Accès créé ou réinitialisé (serveur)",
  disabled: "Accès fermé (serveur)",
  setup_completed: "Accès activé",
  login: "Connexion",
  login_failed: "Connexion refusée",
  logout: "Déconnexion",
  recovery_code_used: "Code de secours utilisé",
  organization_viewed: "Fiche consultée",
  organization_created: "Entreprise créée",
  organization_suspended: "Entreprise suspendue",
  organization_reactivated: "Entreprise réactivée",
  organization_deleted: "Entreprise supprimée",
  deletion_cancelled: "Suppression annulée",
  user_invited: "Utilisateur invité",
  invitation_resent: "Invitation renvoyée",
  verification_resent: "E-mail de confirmation renvoyé",
  password_reset_sent: "Lien de mot de passe envoyé",
  role_changed: "Rôle changé",
  user_logged_out: "Utilisateur déconnecté partout",
  user_removed: "Utilisateur retiré",
  step_up_failed: "Code refusé",
  module_enabled: "Module activé",
  module_disabled: "Module désactivé",
  plan_created: "Formule créée",
  plan_updated: "Formule modifiée",
  plan_archived: "Formule archivée",
  plan_unarchived: "Formule désarchivée",
  plan_default_set: "Formule par défaut changée",
  plan_changed: "Formule de l'entreprise changée",
  credits_added: "Crédits ajoutés",
  credit_price_changed: "Prix d'une action changé",
};

export function auditLabel(action: string): string {
  return AUDIT_LABELS[action] ?? action;
}

/** A module's short name, for the pills of the companies list (lot 3). */
const MODULE_SHORT: Record<string, string> = {
  veille: "Veille",
  reponse: "Réponse",
};

export function moduleShort(key: string): string {
  return MODULE_SHORT[key] ?? key;
}

export type UserAction =
  | "invitation"
  | "verification"
  | "password-reset"
  | "role"
  | "logout"
  | "remove";

/** What the administration may do for a company's user (spec §2.4). Nothing is e-mailed
 * for a suspended company. */
export function userActions(u: AdminOrgUser, suspended: boolean): UserAction[] {
  const sends: UserAction[] =
    u.status === "invited" || u.status === "invitation_expired"
      ? ["invitation"]
      : u.status === "unverified"
        ? ["verification", "password-reset"]
        : ["password-reset"];
  return [
    ...(suspended ? [] : sends),
    "role",
    ...(u.has_sessions ? (["logout"] as const) : []),
    "remove",
  ];
}

/** One line's details in the journal: who was concerned, a reason, a mode. Never content. */
export function auditDetail(meta: Record<string, unknown>): string {
  const parts: string[] = [];
  const text = (key: string) =>
    typeof meta[key] === "string" ? (meta[key] as string) : null;
  const who = text("email") ?? text("name");
  if (who) parts.push(who);
  if (text("role"))
    parts.push(`rôle : ${label(ROLES, text("role") as string)}`);
  if (typeof meta.from === "number" && typeof meta.to === "number")
    parts.push(`${meta.from} → ${meta.to} crédits`); // an action's price
  else if (text("from") && text("to"))
    parts.push(`${text("from")} → ${text("to")}`); // a company's plan
  if (typeof meta.amount === "number")
    parts.push(`${meta.amount} crédit${meta.amount > 1 ? "s" : ""}`);
  if (typeof meta.organizations === "number")
    parts.push(
      `${meta.organizations} entreprise${meta.organizations > 1 ? "s" : ""}`,
    );
  if (text("reason")) parts.push(`Raison : ${text("reason")}`);
  if (meta.mode === "immediate") parts.push("effacée tout de suite");
  if (meta.mode === "scheduled") parts.push("effacement dans 30 jours");
  if (typeof meta.left === "number")
    parts.push(`${meta.left} codes de secours restants`);
  return parts.join(" · ") || "—";
}
