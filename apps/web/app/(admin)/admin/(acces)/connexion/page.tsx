"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { safeAdminNext } from "@/lib/admin";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";

function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const login = useAction();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const ok = await login.run(() =>
      api("/admin/auth/login", { json: { email, password, code } }),
    );
    // Full page load: the shell must start from a clean slate (Cache Components keeps the
    // state of hidden routes).
    if (ok) window.location.assign(safeAdminNext(params.get("suite")));
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-xl font-bold text-brand-navy">
        Connexion à l&apos;administration
      </h1>
      <Field label="E-mail" htmlFor="email">
        <Input
          id="email"
          type="email"
          autoComplete="username"
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
      <Field
        label="Code"
        htmlFor="code"
        hint="Le code à 6 chiffres de votre application, ou un code de secours."
      >
        <Input
          id="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
        />
      </Field>
      {login.error && <Alert tone="danger">{login.error}</Alert>}
      <Button type="submit" busy={login.busy} className="w-full">
        Se connecter
      </Button>
    </form>
  );
}

export default function AdminLoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
