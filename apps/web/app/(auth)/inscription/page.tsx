"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { CompanyLookup } from "@/lib/types";

export default function SignUpPage() {
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    siret: "",
    org_name: "",
  });
  const [accepted, setAccepted] = useState(false);
  const [lookup, setLookup] = useState<CompanyLookup | null>(null);
  // null: not signed up yet; false: account created but the e-mail did not leave
  const [emailSent, setEmailSent] = useState<boolean | null>(null);
  const submit = useAction();
  const search = useAction();
  const set =
    (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));
  const siret = form.siret.replace(/\s/g, "");

  async function findCompany(value: string) {
    const digits = value.replace(/\s/g, "");
    if (!/^\d{14}$/.test(digits)) return;
    const result = await search.run(() =>
      api<CompanyLookup>(`/companies/lookup?siret=${digits}`),
    );
    if (!result) return;
    setLookup(result);
    if (result.company)
      setForm((f) => ({ ...f, org_name: f.org_name || result.company!.name }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const res = await submit.run(() =>
      api<{ message: string; email_sent?: boolean }>("/auth/register", {
        json: { ...form, siret, accept_terms: accepted },
      }),
    );
    if (res) setEmailSent(res.email_sent !== false);
  }

  if (emailSent === false) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-brand-navy">Compte créé</h1>
        <Alert tone="warning">
          L&apos;e-mail de confirmation n&apos;a pas pu partir. Inutile de
          recréer le compte : sur la page de connexion, entrez{" "}
          <strong>{form.email}</strong> et votre mot de passe, puis cliquez sur
          « Renvoyer l&apos;e-mail de confirmation ».
        </Alert>
        <Link
          href="/connexion"
          className="text-sm font-semibold text-brand-navy underline"
        >
          Aller à la connexion
        </Link>
      </div>
    );
  }

  if (emailSent) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-brand-navy">
          Vérifiez votre boîte e-mail
        </h1>
        <p className="text-sm text-slate-700">
          Un lien de confirmation vient d&apos;être envoyé à{" "}
          <strong>{form.email}</strong>. Ouvrez-le pour activer votre compte (il
          est valable 48 heures).
        </p>
        <Link
          href="/connexion"
          className="text-sm font-semibold text-brand-navy underline"
        >
          Aller à la connexion
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <h1 className="text-xl font-bold text-brand-navy">Créer votre compte</h1>
      <Field
        label="SIRET de votre entreprise"
        htmlFor="siret"
        hint="14 chiffres : nous retrouvons votre entreprise dans le registre public."
      >
        <Input
          id="siret"
          inputMode="numeric"
          autoComplete="off"
          value={form.siret}
          onChange={set("siret")}
          onBlur={(e) => findCompany(e.target.value)}
          required
        />
      </Field>
      {search.busy && (
        <p className="text-xs text-slate-500">
          Recherche de l&apos;entreprise…
        </p>
      )}
      {lookup && !lookup.available && (
        <Alert tone="warning">
          L&apos;annuaire des entreprises ne répond pas : saisissez la raison
          sociale vous-même.
        </Alert>
      )}
      {lookup?.available && !lookup.found && (
        <Alert tone="warning">
          Aucune entreprise trouvée pour ce SIRET : vérifiez-le ou saisissez la
          raison sociale.
        </Alert>
      )}
      {lookup?.company && (
        <Alert tone="ok">
          {lookup.company.name}
          {lookup.company.city
            ? ` — ${lookup.company.postal_code ?? ""} ${lookup.company.city}`
            : ""}
        </Alert>
      )}
      <Field label="Raison sociale" htmlFor="org_name">
        <Input
          id="org_name"
          value={form.org_name}
          onChange={set("org_name")}
          required
        />
      </Field>
      <Field label="Votre nom" htmlFor="full_name">
        <Input
          id="full_name"
          autoComplete="name"
          value={form.full_name}
          onChange={set("full_name")}
          required
        />
      </Field>
      <Field label="E-mail professionnel" htmlFor="email">
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={set("email")}
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
          value={form.password}
          onChange={set("password")}
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
          J&apos;accepte, au nom de mon entreprise, les{" "}
          <TermsLink href="/conditions-utilisation">
            conditions d&apos;utilisation
          </TermsLink>
          , l&apos;
          <TermsLink href="/accord-de-traitement">
            accord de traitement des données
          </TermsLink>{" "}
          et la{" "}
          <TermsLink href="/confidentialite">
            politique de confidentialité
          </TermsLink>
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
        Créer mon compte
      </Button>
      <p className="text-center text-sm text-slate-600">
        Déjà inscrit ?{" "}
        <Link
          href="/connexion"
          className="font-semibold text-brand-navy underline"
        >
          Se connecter
        </Link>
      </p>
    </form>
  );
}

function TermsLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      target="_blank"
      className="font-semibold text-brand-navy underline"
    >
      {children}
    </Link>
  );
}
