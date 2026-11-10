"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { Alert, Button, Field, Input, Loading } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { AdminSetupDone, AdminSetupSecret } from "@/lib/types";

const MIN_PASSWORD = 12;

/** Step 1: the password of the super admin account. */
function PasswordStep({
  token,
  email,
  onDone,
}: {
  token: string;
  email: string;
  onDone: (secret: AdminSetupSecret) => void;
}) {
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const save = useAction();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD)
      return setProblem(`${MIN_PASSWORD} caractères au moins.`);
    if (password !== again)
      return setProblem("Les deux saisies ne sont pas identiques.");
    setProblem(null);
    const secret = await save.run(() =>
      api<AdminSetupSecret>("/admin/auth/setup/password", {
        json: { token, password },
      }),
    );
    if (secret) onDone(secret);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <p className="text-sm text-slate-600">
        Étape 1 sur 3 · compte <strong>{email}</strong>
      </p>
      <Field
        label="Choisissez un mot de passe"
        htmlFor="password"
        hint={`${MIN_PASSWORD} caractères au moins.`}
        error={problem}
      >
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>
      <Field label="Saisissez-le une seconde fois" htmlFor="again">
        <Input
          id="again"
          type="password"
          autoComplete="new-password"
          value={again}
          onChange={(e) => setAgain(e.target.value)}
          required
        />
      </Field>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
      <Button type="submit" busy={save.busy} className="w-full">
        Continuer
      </Button>
    </form>
  );
}

/** Step 2: link the authenticator application, prove it with a first code. */
function AuthenticatorStep({
  token,
  secret,
  onDone,
}: {
  token: string;
  secret: AdminSetupSecret;
  onDone: (done: AdminSetupDone) => void;
}) {
  const [code, setCode] = useState("");
  const confirm = useAction();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const done = await confirm.run(() =>
      api<AdminSetupDone>("/admin/auth/setup/confirm", {
        json: { token, code },
      }),
    );
    if (done) onDone(done);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <p className="text-sm text-slate-600">
        Étape 2 sur 3 · scannez ce QR code avec votre application
        d&apos;authentification (Google Authenticator ou équivalent).
      </p>
      {/* The server's SVG as an image: never injected as HTML. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        alt="QR code"
        className="mx-auto h-48 w-48 rounded-md ring-1 ring-slate-300"
        src={`data:image/svg+xml;utf8,${encodeURIComponent(secret.qr_svg)}`}
      />
      <p className="text-center text-xs text-slate-600">
        Ou saisissez cette clé à la main :
        <br />
        <code
          data-testid="totp-secret"
          className="select-all break-all font-mono text-sm font-semibold text-brand-navy"
        >
          {secret.secret}
        </code>
      </p>
      <Field
        label="Code affiché par l'application"
        htmlFor="code"
        hint="6 chiffres, renouvelés toutes les 30 secondes."
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
      {confirm.error && <Alert tone="danger">{confirm.error}</Alert>}
      <Button type="submit" busy={confirm.busy} className="w-full">
        Activer mon accès
      </Button>
    </form>
  );
}

/** Step 3: the recovery codes, shown once. */
function RecoveryStep({ codes }: { codes: string[] }) {
  const [noted, setNoted] = useState(false);
  const [copied, setCopied] = useState(false);

  function open() {
    // Full page load: the shell starts from the session the activation just opened.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/admin");
  }

  async function copy() {
    await navigator.clipboard
      .writeText(codes.join("\n"))
      .catch(() => undefined);
    setCopied(true);
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Étape 3 sur 3 · votre accès est activé. Gardez ces{" "}
        <strong>{codes.length} codes de secours</strong> en lieu sûr : chacun
        remplace une fois le code de votre téléphone, le jour où vous
        l&apos;aurez changé ou perdu. Ils ne seront plus jamais affichés.
      </p>
      <ul
        aria-label="Codes de secours"
        className="grid grid-cols-2 gap-2 rounded-md bg-slate-100 p-3 font-mono text-sm font-semibold text-brand-navy"
      >
        {codes.map((c) => (
          <li key={c} className="select-all text-center">
            {c}
          </li>
        ))}
      </ul>
      <Button type="button" variant="secondary" onClick={copy}>
        {copied ? "Codes copiés" : "Copier"}
      </Button>
      <label className="flex items-start gap-2 text-sm text-slate-800">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4"
          checked={noted}
          onChange={(e) => setNoted(e.target.checked)}
        />
        J&apos;ai noté mes codes
      </label>
      <Button type="button" className="w-full" disabled={!noted} onClick={open}>
        Ouvrir l&apos;administration
      </Button>
    </div>
  );
}

const BAD_LINK =
  "Lien invalide ou expiré. Relancez la commande sur le serveur.";

function Activation() {
  const token = useSearchParams().get("jeton");
  // The account the link belongs to, or why the link cannot be used.
  const [link, setLink] = useState<{ email?: string; problem?: string } | null>(
    null,
  );
  const [secret, setSecret] = useState<AdminSetupSecret | null>(null);
  const [done, setDone] = useState<AdminSetupDone | null>(null);
  const asked = useRef(false); // once, even under React strict mode

  useEffect(() => {
    if (!token || asked.current) return;
    asked.current = true;
    api<{ email: string }>("/admin/auth/setup/lookup", { json: { token } })
      .then((found) => setLink({ email: found.email }))
      .catch((err) => setLink({ problem: errorMessage(err) }));
  }, [token]);

  const problem = token ? link?.problem : BAD_LINK;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-brand-navy">Activer votre accès</h1>
      {problem ? (
        <Alert tone="danger">{problem}</Alert>
      ) : done ? (
        <RecoveryStep codes={done.recovery_codes} />
      ) : secret && token ? (
        <AuthenticatorStep token={token} secret={secret} onDone={setDone} />
      ) : link?.email && token ? (
        <PasswordStep token={token} email={link.email} onDone={setSecret} />
      ) : (
        <Loading />
      )}
    </div>
  );
}

export default function AdminActivationPage() {
  return (
    <Suspense>
      <Activation />
    </Suspense>
  );
}
