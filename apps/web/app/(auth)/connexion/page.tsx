"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAction } from "@/lib/hooks";

function safeNext(value: string | null): string {
  // Only same-site paths: never redirect to another origin after login.
  return value && value.startsWith("/") && !value.startsWith("//")
    ? value
    : "/tableau-de-bord";
}

function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [unverified, setUnverified] = useState(false);
  const [resent, setResent] = useState(false);
  const login = useAction();
  const resend = useAction();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setUnverified(false);
    const ok = await login.run(async () => {
      try {
        return await api("/auth/login", { json: { email, password } });
      } catch (err) {
        if (err instanceof ApiError && err.code === "email_not_verified")
          setUnverified(true);
        throw err;
      }
    });
    // Full page load: with Cache Components, Next keeps the state of hidden routes (Activity),
    // so the app shell would still remember "not logged in". Start from a clean slate.
    if (ok) window.location.assign(safeNext(params.get("suite")));
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-xl font-bold text-brand-navy">Connexion</h1>
      <Field label="E-mail" htmlFor="email">
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </Field>
      <Field label="Mot de passe" htmlFor="password">
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>
      {login.error && <Alert tone="danger">{login.error}</Alert>}
      {unverified && !resent && (
        <Button
          type="button"
          variant="secondary"
          busy={resend.busy}
          onClick={async () => {
            if (
              await resend.run(() =>
                api("/auth/resend-verification", { json: { email } }),
              )
            )
              setResent(true);
          }}
        >
          Renvoyer l&apos;e-mail de confirmation
        </Button>
      )}
      {resent && (
        <Alert tone="ok">
          Si un compte non confirmé existe pour cette adresse, un nouvel e-mail
          vient d&apos;être envoyé.
        </Alert>
      )}
      <Button type="submit" busy={login.busy} className="w-full">
        Se connecter
      </Button>
      <p className="text-center text-sm text-slate-600">
        Pas encore de compte ?{" "}
        <Link
          href="/inscription"
          className="font-semibold text-brand-navy underline"
        >
          Créer un compte
        </Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
