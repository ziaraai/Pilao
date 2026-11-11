/** Messages of the sign-in page that come from the address (why the user is back there). */

export type SignInNotice = { tone: "danger" | "ok"; text: string };

export function signInNotice(params: URLSearchParams): SignInNotice | null {
  if (params.get("suspendu") === "1")
    return {
      tone: "danger",
      text: "L'accès de votre entreprise à Pilao est suspendu.",
    };
  return null;
}
