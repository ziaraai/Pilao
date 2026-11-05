"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, Button, Field, Input, Loading } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { ROLES } from "@/lib/labels";
import type { Invitation, Me } from "@/lib/types";

function Join() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const submit = useAction();

  useEffect(() => {
    if (!token) return;
    api<Invitation>("/auth/invitations/lookup", { json: { token } })
      .then((found) => {
        setInvitation(found);
        setFullName(found.full_name ?? "");
      })
      .catch((err) => setInvalid(errorMessage(err)));
  }, [token]);

  if (!token)
    return (
      <Alert tone="danger">
        Lien incomplet : ouvrez le lien reçu par e-mail.
      </Alert>
    );
  if (invalid)
    return (
      <div className="space-y-4">
        <Alert tone="danger">{invalid}</Alert>
        <Link
          href="/connexion"
          className="text-sm font-semibold text-brand-navy underline"
        >
          Aller à la connexion
        </Link>
      </div>
    );
  if (!invitation) return <Loading />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const me = await submit.run(() =>
      api<Me>("/auth/invitations/accept", {
        json: { token, full_name: fullName, password, accept_terms: accepted },
      }),
    );
    if (me) router.replace("/tableau-de-bord");
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-xl font-bold text-brand-navy">
        Rejoindre {invitation.org_name}
      </h1>
      <p className="text-sm text-slate-700">
        Vous êtes invité comme{" "}
        <strong>
          {(ROLES[invitation.role] ?? "collaborateur").toLowerCase()}
        </strong>{" "}
        avec l&apos;adresse <strong>{invitation.email}</strong>. Choisissez
        votre mot de passe pour créer votre accès.
      </p>
      <Field label="Votre nom" htmlFor="full_name">
        <Input
          id="full_name"
          autoComplete="name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />
      </Field>
      <Field
        label="Mot de passe"
        htmlFor="password"
        hint="12 caractères minimum."
      >
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={12}
        />
      </Field>
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          className="mt-1"
          checked={accepted}
          onChange={(e) => setAccepted(e.target.checked)}
          required
        />
        <span>
          J&apos;accepte les{" "}
          <Link
            href="/conditions-utilisation"
            target="_blank"
            className="font-semibold text-brand-navy underline"
          >
            conditions d&apos;utilisation
          </Link>{" "}
          et la{" "}
          <Link
            href="/confidentialite"
            target="_blank"
            className="font-semibold text-brand-navy underline"
          >
            politique de confidentialité
          </Link>
          .
        </span>
      </label>
      {submit.error && <Alert tone="danger">{submit.error}</Alert>}
      <Button
        type="submit"
        busy={submit.busy}
        disabled={!accepted}
        className="w-full"
      >
        Créer mon accès
      </Button>
    </form>
  );
}

export default function InvitationPage() {
  return (
    <Suspense>
      <Join />
    </Suspense>
  );
}
