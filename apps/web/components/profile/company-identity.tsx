"use client";

import { useEffect, useState } from "react";

import { UploadButton } from "@/components/upload";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { fileUrl, uploadFile } from "@/lib/files";
import { useAction, useApi } from "@/lib/hooks";
import type { Company } from "@/lib/types";

type Form = Omit<
  Company,
  "siret" | "siren" | "naf_code" | "headcount_range" | "vat_number"
>;

const FIELDS: {
  key: keyof Form;
  label: string;
  type?: string;
  hint?: string;
}[] = [
  { key: "name", label: "Dénomination sociale" },
  { key: "legal_form", label: "Forme juridique", hint: "Ex. : SAS, SARL" },
  { key: "address_line", label: "Adresse du siège" },
  { key: "postal_code", label: "Code postal" },
  { key: "city", label: "Ville" },
  { key: "phone", label: "Téléphone", type: "tel" },
  { key: "contact_email", label: "E-mail de contact", type: "email" },
  {
    key: "signatory_name",
    label: "Signataire (nom et prénom)",
    hint: "Personne habilitée à engager l'entreprise",
  },
  {
    key: "signatory_role",
    label: "Qualité du signataire",
    hint: "Ex. : Gérant",
  },
];

const DEFAULT_COLOR = "#011844";

/** Identity used by DC1/DC2, and the logo and colour of the Word documents. */
export function CompanyIdentity() {
  const company = useApi<Company>("/profile/company");
  if (company.error) return <Alert tone="danger">{company.error}</Alert>;
  if (!company.data) return null;
  return <IdentityForm key={company.data.siret} company={company.data} />;
}

function IdentityForm({ company }: { company: Company }) {
  const [form, setForm] = useState<Form>(() => ({
    name: company.name,
    legal_form: company.legal_form,
    address_line: company.address_line,
    postal_code: company.postal_code,
    city: company.city,
    phone: company.phone,
    contact_email: company.contact_email,
    signatory_name: company.signatory_name,
    signatory_role: company.signatory_role,
    logo_file_id: company.logo_file_id,
    brand_color: company.brand_color,
  }));
  const [saved, setSaved] = useState(false);
  const [logo, setLogo] = useState<string | null>(null);
  const save = useAction();
  const upload = useAction();

  useEffect(() => {
    let cancelled = false;
    if (form.logo_file_id)
      fileUrl(form.logo_file_id)
        .then((url) => !cancelled && setLogo(url))
        .catch(() => !cancelled && setLogo(null));
    return () => {
      cancelled = true;
    };
  }, [form.logo_file_id]);

  const set = (key: keyof Form, value: string | null) => {
    setSaved(false);
    setForm((f) => ({ ...f, [key]: value }));
  };

  return (
    <Card title="Identité et mise en page" color="brand" icon="profile">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const ok = await save.run(() =>
            api<Company>("/profile/company", { method: "PUT", json: form }),
          );
          if (ok) setSaved(true);
        }}
      >
        <p className="text-sm text-slate-600">
          Ces informations pré-remplissent le DC1 et le DC2 ; le logo et la
          couleur habillent vos documents Word. SIRET {company.siret} · TVA{" "}
          {company.vat_number} (calculée depuis le SIREN)
          {company.naf_code ? ` · NAF ${company.naf_code}` : ""}.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <Field
              key={f.key}
              label={f.label}
              htmlFor={`company-${f.key}`}
              hint={f.hint}
            >
              <Input
                id={`company-${f.key}`}
                type={f.type ?? "text"}
                required={f.key === "name"}
                value={(form[f.key] as string | null) ?? ""}
                onChange={(e) => set(f.key, e.target.value || null)}
              />
            </Field>
          ))}
          <Field label="Couleur des titres" htmlFor="company-color">
            <div className="flex items-center gap-2">
              <input
                id="company-color"
                type="color"
                value={form.brand_color ?? DEFAULT_COLOR}
                onChange={(e) => set("brand_color", e.target.value)}
                className="h-9 w-14 cursor-pointer rounded border border-slate-300"
              />
              <span className="font-mono text-xs text-slate-600">
                {form.brand_color ?? "par défaut"}
              </span>
            </div>
          </Field>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-800">Logo</p>
          {logo && (
            // eslint-disable-next-line @next/next/no-img-element -- signed storage URL
            <img
              src={logo}
              alt="Logo de l'entreprise"
              className="h-14 w-auto rounded ring-1 ring-slate-200"
            />
          )}
          <UploadButton
            id="company-logo"
            label="Utiliser ce logo"
            accept="image/png,image/jpeg"
            busy={upload.busy}
            onFiles={async ([file]) => {
              const record = await upload.run(() => uploadFile(file));
              if (record) set("logo_file_id", record.id);
            }}
          />
          {form.logo_file_id && (
            <Button variant="ghost" onClick={() => set("logo_file_id", null)}>
              Retirer le logo
            </Button>
          )}
          {upload.error && <Alert tone="danger">{upload.error}</Alert>}
        </div>
        <div className="flex items-center gap-3">
          <Button type="submit" busy={save.busy}>
            Enregistrer l&apos;identité
          </Button>
          {saved && (
            <span className="text-sm text-emerald-700" role="status">
              Enregistré.
            </span>
          )}
        </div>
        {save.error && <Alert tone="danger">{save.error}</Alert>}
      </form>
    </Card>
  );
}
