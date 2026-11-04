const PARIS = "Europe/Paris";

const euros = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
});

/** "12 500,00 €" from cents (amounts are stored in cents, CLAUDE.md §4). */
export function formatCents(cents: number | null | undefined): string {
  return cents == null ? "—" : euros.format(cents / 100).replace(/ | /g, " ");
}

/** Cents from what a French user types: "12 500,50", "12500.5 €"... null if empty/invalid. */
export function parseEuros(text: string): number | null {
  const cleaned = text.replace(/[\s  €]/g, "").replace(",", ".");
  if (cleaned === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  return Math.round(parseFloat(cleaned) * 100);
}

export function centsToInput(cents: number | null | undefined): string {
  return cents == null
    ? ""
    : (cents / 100).toFixed(2).replace(".", ",").replace(/,00$/, "");
}

/** Dates are stored in UTC and shown in Paris time (CLAUDE.md §4). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: PARIS,
  }).format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  // A plain date ("2027-04-15") is a calendar day: never shift it through a time zone.
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "long",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(y, m - 1, d)));
  }
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "long",
    timeZone: PARIS,
  }).format(new Date(iso));
}

/** Value for <input type="datetime-local"> in Paris time, and back to an ISO instant. */
export function toParisInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: PARIS,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
  return parts.replace(" ", "T");
}

export function fromParisInput(local: string): string | null {
  if (!local) return null;
  // Find the UTC instant whose Paris wall-clock time is `local` (handles summer time).
  const [date, time] = local.split("T");
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  let guess = Date.UTC(y, m - 1, d, hh, mm);
  for (let i = 0; i < 2; i++) {
    const shown = toParisInput(new Date(guess).toISOString());
    const [sd, st] = shown.split("T");
    const [sy, sm, sdd] = sd.split("-").map(Number);
    const [sh, smin] = st.split(":").map(Number);
    guess -=
      Date.UTC(sy, sm - 1, sdd, sh, smin) - Date.UTC(y, m - 1, d, hh, mm);
  }
  return new Date(guess).toISOString();
}

export function splitList(text: string): string[] {
  return [
    ...new Set(
      text
        .split(/[,;\n]/)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
}
