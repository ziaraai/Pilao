"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, Button, Field, Input, Loading } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAction } from "@/lib/hooks";

const MIN_LENGTH = 12;

function ChooseNewPassword() {
  const params = useSearchParams();
  // Read once, then taken out of the address bar (history, screen sharing, a forwarded link).
  const [token] = useState(() => params.get("token"));
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [mistake, setMistake] = useState<string | null>(null);
  const save = useAction();

  useEffect(() => {
    if (!token) return;
    window.history.replaceState(null, "", "/nouveau-mot-de-passe");
    api<{ email: string }>("/auth/password/reset/lookup", { json: { token } })
      .then((found) => setEmail(found.email))
      .catch((err) => setInvalid(errorMessage(err)));
  }, [token]);

  if (!token || invalid)
    return (
      <div className="space-y-4">
        <Alert tone="danger">
          {invalid ?? "Lien incomplet : ouvrez le lien reçu par e-mail."}
        </Alert>
        <Link
          href="/mot-de-passe-oublie"
          className="text-sm font-semibold text-brand-navy underline"
        >
          Demander un nouveau lien
        </Link>
      </div>
    );
  if (!email) return <Loading />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN_LENGTH)
      return setMistake(`${MIN_LENGTH} caractères au moins.`);
    if (password !== again)
      return setMistake("Les deux saisies sont différentes.");
    setMistake(null);
    const ok = await save.run(() =>
      api("/auth/password/reset", { json: { token, password } }),
    );
    // Full page load, as after a sign-in: the app shell starts from a clean slate.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (ok) window.location.assign("/tableau-de-bord");
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-xl font-bold text-brand-navy">
        Nouveau mot de passe
      </h1>
      <p className="text-sm text-slate-600">
        Pour le compte <strong>{email}</strong>. Vos autres connexions seront
        fermées.
      </p>
      <Field
        label="Nouveau mot de passe"
        htmlFor="new-password"
        hint={`${MIN_LENGTH} caractères au moins.`}
      >
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>
      <Field
        label="Le même, une seconde fois"
        htmlFor="new-password-again"
        error={mistake}
      >
        <Input
          id="new-password-again"
          type="password"
          autoComplete="new-password"
          value={again}
          onChange={(e) => setAgain(e.target.value)}
          required
        />
      </Field>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
      <Button type="submit" busy={save.busy} className="w-full">
        Enregistrer
      </Button>
    </form>
  );
}

export default function NewPasswordPage() {
  return (
    <Suspense>
      <ChooseNewPassword />
    </Suspense>
  );
}
