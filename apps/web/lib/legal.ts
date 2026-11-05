/**
 * Who publishes Pilao, who hosts it, and the facts the legal pages state (ADR-029).
 *
 * `null` = not decided yet: the pages then show « [À COMPLÉTER : …] », so they cannot go
 * live unfinished without it being seen. To fill before opening to clients (docs/14).
 * Changing the texts of the pages means a new `TERMS_VERSION`, the same as the API's
 * (`apps/api/app/core/legal.py`, checked by a test).
 */

export const TERMS_VERSION = "2026-11-05";

export type LegalFacts = {
  publisher: {
    name: string | null; // raison sociale (Q5)
    legalForm: string | null; // SAS, SARL…
    capital: string | null; // capital social
    address: string | null; // siège social
    rcs: string | null; // RCS + ville, ou SIREN
    vat: string | null; // TVA intracommunautaire
    director: string | null; // directeur de la publication
    email: string | null; // contact, et exercice des droits RGPD
    phone: string | null;
  };
  host: { name: string | null; address: string | null; phone: string | null }; // Q7
  emailProvider: string | null; // e-mails transactionnels (Q11)
  backupRetention: string | null; // durée de conservation des sauvegardes (Q15)
  court: string | null; // tribunal de commerce compétent
  pricing: string | null; // formules et prix (Q3)
  liabilityCap: string | null; // plafond de responsabilité
};

export const LEGAL: LegalFacts = {
  publisher: {
    name: null,
    legalForm: null,
    capital: null,
    address: null,
    rcs: null,
    vat: null,
    director: null,
    email: null,
    phone: null,
  },
  host: { name: null, address: null, phone: null },
  emailProvider: null,
  backupRetention: null,
  court: null,
  pricing: null,
  liabilityCap: null,
};

/** Facts the texts rely on, set by the code itself (keep them in line with the API). */
export const RETENTION = {
  deletionGraceDays: 30, // DELETION_GRACE_DAYS
  sessionDays: 14, // SESSION_TTL_HOURS
  verifyLinkHours: 48, // EMAIL_VERIFY_TTL_HOURS
  loginAttemptsDays: 30, // LOGIN_ATTEMPTS_RETENTION_DAYS
};

/** The value, or the placeholder the product uses everywhere for a missing fact. */
export function fact(value: string | null, what: string): string {
  return value?.trim() ? value : `[À COMPLÉTER : ${what}]`;
}

/** What is still to fill in, for the deployment checklist. */
export function missingFacts(facts: LegalFacts = LEGAL): string[] {
  const out: string[] = [];
  const walk = (obj: Record<string, unknown>, path: string) => {
    for (const [key, value] of Object.entries(obj)) {
      const name = path ? `${path}.${key}` : key;
      if (value && typeof value === "object")
        walk(value as Record<string, unknown>, name);
      else if (!(typeof value === "string" && value.trim())) out.push(name);
    }
  };
  walk(facts as unknown as Record<string, unknown>, "");
  return out;
}

/** "5 novembre 2026", for the version shown on each page. */
export function versionDate(version: string = TERMS_VERSION): string {
  const [y, m, d] = version.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
