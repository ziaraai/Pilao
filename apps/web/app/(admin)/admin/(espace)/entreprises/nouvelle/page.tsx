"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AdminTitle } from "@/components/admin/ui";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { useAdminAction } from "@/lib/admin-auth";
import { api, ApiError } from "@/lib/api";
import type { AdminOrganizationRow } from "@/lib/types";

type Lookup = {
  available: boolean;
  found: boolean;
  company: {
    name: string;
    city: string | null;
    postal_code: string | null;
  } | null;
};

/** Lot 2, spec §2.1: Pilao opens a company's space and invites its first person. */
export default function NewOrganizationPage() {
  const router = useRouter();
  const [siret, setSiret] = useState("");
  const [name, setName] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [found, setFound] = useState<string | null>(null);
  const [existing, setExisting] = useState<AdminOrganizationRow | null>(null);
  const search = useAdminAction();
  const create = useAdminAction();

  async function lookup() {
    setFound(null);
    const res = await search.run(() =>
      api<Lookup>(
        `/admin/companies/lookup?siret=${encodeURIComponent(siret.replace(/\s/g, ""))}`,
      ),
    );
    if (!res) return;
    if (!res.available)
      setFound("Annuaire injoignable : saisissez le nom à la main.");
    else if (!res.found || !res.company)
      setFound(
        "Introuvable dans l'annuaire : vérifiez le SIRET, ou saisissez le nom.",
      );
    else {
      setName(res.company.name);
      setFound(
        `Trouvée : ${res.company.name}${res.company.city ? `, ${[res.company.postal_code, res.company.city].filter(Boolean).join(" ")}` : ""}.`,
      );
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setExisting(null);
    const res = await create.run(async () => {
      try {
        return await api<{ id: string }>("/admin/organizations", {
          json: {
            siret,
            name,
            contact_name: contactName,
            contact_email: contactEmail,
          },
        });
      } catch (err) {
        if (err instanceof ApiError && err.code === "siret_taken") {
          const rows = await api<AdminOrganizationRow[]>(
            "/admin/organizations",
          );
          const clean = siret.replace(/\s/g, "");
          setExisting(rows.find((r) => r.siret === clean) ?? null);
        }
        throw err;
      }
    });
    if (res) router.push(`/admin/entreprises/${res.id}`);
  }

  const ready =
    siret.trim() && name.trim() && contactName.trim() && contactEmail.trim();

  return (
    <div>
      <p className="mb-2 text-sm text-slate-600">
        <Link href="/admin/entreprises" className="underline">
          Entreprises
        </Link>{" "}
        ›
      </p>
      <AdminTitle
        title="Créer une entreprise"
        readOnly={false}
        subtitle="Le responsable reçoit un lien pour choisir son mot de passe (valable 7 jours)."
      />
      <Card title="Entreprise et responsable" color="brand">
        <form onSubmit={onSubmit} className="max-w-xl space-y-4" noValidate>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-1">
              <Field label="SIRET" htmlFor="siret" hint="14 chiffres.">
                <Input
                  id="siret"
                  inputMode="numeric"
                  value={siret}
                  onChange={(e) => setSiret(e.target.value)}
                  required
                />
              </Field>
            </div>
            <Button
              type="button"
              variant="secondary"
              busy={search.busy}
              disabled={siret.replace(/\s/g, "").length < 14}
              onClick={lookup}
              className="mb-6"
            >
              Rechercher
            </Button>
          </div>
          {search.error && <Alert tone="danger">{search.error}</Alert>}
          {found && <Alert tone="info">{found}</Alert>}
          <Field label="Nom de l'entreprise" htmlFor="name">
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </Field>
          <Field label="Nom du responsable" htmlFor="contact-name">
            <Input
              id="contact-name"
              autoComplete="off"
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
              required
            />
          </Field>
          <Field label="E-mail du responsable" htmlFor="contact-email">
            <Input
              id="contact-email"
              type="email"
              autoComplete="off"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              required
            />
          </Field>
          {create.error && (
            <Alert tone="danger">
              {create.error}
              {existing && (
                <>
                  {" "}
                  <Link
                    href={`/admin/entreprises/${existing.id}`}
                    className="font-semibold underline"
                  >
                    Ouvrir sa fiche
                  </Link>
                </>
              )}
            </Alert>
          )}
          <Button type="submit" busy={create.busy} disabled={!ready}>
            Créer et envoyer l&apos;invitation
          </Button>
        </form>
      </Card>
    </div>
  );
}
