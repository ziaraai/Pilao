/**
 * The modules of Pilao (lot 3, ADR-041), as the company space sees them: which menu entries
 * belong to which module. The API is the authority (`me.modules`, `module_disabled`); this
 * file only decides what to show.
 */
import type { IconName } from "@/components/icon";

export type ModuleKey = "veille" | "reponse";

export type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  module: ModuleKey | null; // null: common to every company
};

export const NAV: NavItem[] = [
  {
    href: "/tableau-de-bord",
    label: "Tableau de bord",
    icon: "dashboard",
    module: null,
  },
  { href: "/annonces", label: "Annonces", icon: "tenders", module: "veille" },
  { href: "/dossiers", label: "Dossiers", icon: "bids", module: "reponse" },
  {
    href: "/coffre-fort",
    label: "Coffre-fort",
    icon: "vault",
    module: "reponse",
  },
  {
    href: "/documents",
    label: "Base documentaire",
    icon: "documents",
    module: "reponse",
  },
  { href: "/profil", label: "Profil", icon: "profile", module: null },
];

/** What a company has when nothing says otherwise (the API's default, too). */
export const DEFAULT_MODULES: string[] = ["veille", "reponse"];

/** The modules of the registry, in its order (lot 4: plan form). */
export const MODULE_KEYS: string[] = ["veille", "reponse"];

const MODULE_NAMES: Record<string, string> = {
  veille: "Veille des annonces",
  reponse: "Réponse aux appels d'offres",
};

export function moduleName(key: string): string {
  return MODULE_NAMES[key] ?? key;
}

export function hasModule(modules: string[], key: ModuleKey): boolean {
  return modules.includes(key);
}

/** The menu of a company: the common entries and those of its active modules, in order. */
export function visibleNav(modules: string[]): NavItem[] {
  return NAV.filter(
    (item) => item.module === null || hasModule(modules, item.module),
  );
}
