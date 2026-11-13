import type { DceSource, DceVersion, DceWatch } from "./types";

const PARIS = "Europe/Paris";
const day = new Intl.DateTimeFormat("fr-FR", {
  timeZone: PARIS,
  day: "2-digit",
  month: "2-digit",
});
const time = new Intl.DateTimeFormat("fr-FR", {
  timeZone: PARIS,
  hour: "2-digit",
  minute: "2-digit",
});
const dateKey = new Intl.DateTimeFormat("en-CA", { timeZone: PARIS }); // 2026-11-16

/** Which card the dossier shows (spec « Récupération des DCE », § 4.1). */
export function sourceCase(s: DceSource | null): "robot" | "guided" | "link" {
  if (!s || !s.url || s.home_only) return "link";
  return s.automatic && s.robot_enabled ? "robot" : "guided";
}

/** « Récupéré sur PLACE le 13/11 à 15:25 », « Mise à jour trouvée par Pilao le 16/11 »… */
export function originLabel(v: DceVersion, site: string | null): string {
  const at = new Date(v.created_at);
  if (v.origin === "retrieval")
    return `Récupéré sur ${site ?? "la plateforme"} le ${day.format(at)} à ${time.format(at)}`;
  if (v.origin === "update")
    return `Mise à jour trouvée par Pilao le ${day.format(at)}`;
  return v.uploaded_by_name
    ? `Déposé par ${v.uploaded_by_name} le ${day.format(at)}`
    : `Déposé le ${day.format(at)}`;
}

/** The latest version when it is an update found by Pilao that is not analysed yet. */
export function updateBanner(
  versions: DceVersion[],
  analysedVersion: number | null,
): DceVersion | null {
  if (versions.length === 0) return null;
  const latest = versions.reduce((a, b) => (b.version > a.version ? b : a));
  if (latest.origin !== "update" || latest.status !== "ready") return null;
  return (analysedVersion ?? 0) < latest.version ? latest : null;
}

/** « Surveillé par Pilao — dernière vérification : aujourd'hui 06:45 ». */
export function watchLine(w: DceWatch | null, now: Date): string | null {
  if (!w) return null;
  if (w.stopped)
    return "Surveillance interrompue : la page de la consultation ne répond plus";
  if (!w.checked_at) return null;
  const at = new Date(w.checked_at);
  const yesterday = new Date(now.getTime() - 24 * 3600 * 1000);
  const when =
    dateKey.format(at) === dateKey.format(now)
      ? `aujourd'hui ${time.format(at)}`
      : dateKey.format(at) === dateKey.format(yesterday)
        ? `hier ${time.format(at)}`
        : `le ${day.format(at)} à ${time.format(at)}`;
  return `Surveillé par Pilao — dernière vérification : ${when}`;
}
