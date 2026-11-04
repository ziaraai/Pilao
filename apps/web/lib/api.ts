/**
 * Client for the Pilao API. The browser calls the API directly with the session cookie
 * (httpOnly, SameSite=Lax): the API must live on the same site (e.g. api.pilao.fr next to
 * app.pilao.fr) and allow this origin (CORS). See docs/12-decisions.md, ADR-017.
 */

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type FastApiDetail = { loc?: (string | number)[]; msg?: string }[];

/** French message for a FastAPI/Pydantic validation error (422). */
export function validationMessage(detail: unknown): string {
  if (!Array.isArray(detail) || detail.length === 0)
    return "Certaines informations sont invalides.";
  const parts = (detail as FastApiDetail).map((d) => {
    const msg = d.msg ?? "";
    // Our own validators already speak French: keep their message as written.
    if (msg.startsWith("Value error, "))
      return msg.slice("Value error, ".length);
    const field = d.loc?.filter((x) => x !== "body").join(".") ?? "";
    return translate(msg, field);
  });
  return [...new Set(parts)].join(" ");
}

function translate(msg: string, field: string): string {
  const label = FIELD_LABELS[field.split(".").pop() ?? ""] ?? field;
  const atLeast = msg.match(/at least (\d+) character/);
  if (atLeast) return `${label} : ${atLeast[1]} caractères minimum.`;
  const atMost = msg.match(/at most (\d+) character/);
  if (atMost) return `${label} : ${atMost[1]} caractères maximum.`;
  if (/valid email/i.test(msg)) return "Adresse e-mail invalide.";
  if (/Field required/.test(msg)) return `${label} : champ obligatoire.`;
  if (/greater than or equal/.test(msg))
    return `${label} : valeur trop petite.`;
  if (/less than or equal/.test(msg)) return `${label} : valeur trop grande.`;
  return `${label || "Champ"} : valeur invalide.`; // other Pydantic messages are English
}

const FIELD_LABELS: Record<string, string> = {
  email: "E-mail",
  password: "Mot de passe",
  full_name: "Nom",
  siret: "SIRET",
  org_name: "Raison sociale",
  title: "Intitulé",
  name: "Nom",
  qualification: "Qualification",
  count: "Nombre",
  quantity: "Quantité",
  client_name: "Client",
  departments: "Départements",
  cpv_codes: "Codes CPV",
  valid_until: "Date de fin",
  kind: "Type",
};

type Options = {
  method?: string;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
};

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const {
    method = options.json || options.form ? "POST" : "GET",
    json,
    form,
    signal,
  } = options;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      credentials: "include",
      headers:
        json !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: json !== undefined ? JSON.stringify(json) : form,
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(
      0,
      "network",
      "Le service est injoignable. Vérifiez votre connexion et réessayez.",
    );
  }
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const body = data as {
      error?: { code: string; message: string };
      detail?: unknown;
    } | null;
    if (body?.error)
      throw new ApiError(res.status, body.error.code, body.error.message);
    if (res.status === 422)
      throw new ApiError(422, "validation", validationMessage(body?.detail));
    if (res.status === 413)
      throw new ApiError(413, "too_large", "Fichier trop volumineux.");
    throw new ApiError(
      res.status,
      "unexpected",
      `Erreur inattendue (${res.status}). Réessayez plus tard.`,
    );
  }
  return data as T;
}

export function errorMessage(err: unknown): string {
  return err instanceof ApiError
    ? err.message
    : "Une erreur inattendue s'est produite.";
}
