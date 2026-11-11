"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";

/** « Mot de passe oublié ? » (US-1.6): always the same answer, a one-hour link by e-mail. */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const send = useAction();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const res = await send.run(() =>
      api<{ message: string }>("/auth/password/forgot", { json: { email } }),
    );
    if (res) setAnswer(res.message);
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-brand-navy">Mot de passe oublié</h1>
      {answer ? (
        <Alert tone="ok">{answer}</Alert>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <p className="text-sm text-slate-600">
            Saisissez l&apos;adresse de votre compte : vous recevrez un lien
            pour choisir un nouveau mot de passe.
          </p>
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
          {send.error && <Alert tone="danger">{send.error}</Alert>}
          <Button type="submit" busy={send.busy} className="w-full">
            Recevoir un lien
          </Button>
        </form>
      )}
      <p className="text-center text-sm">
        <Link
          href="/connexion"
          className="font-semibold text-brand-navy underline"
        >
          Retour à la connexion
        </Link>
      </p>
    </div>
  );
}
