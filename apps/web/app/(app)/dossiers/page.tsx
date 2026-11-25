"use client";

import Link from "next/link";
import { MailInbox } from "@/components/dce-mail";
import { UploadButton } from "@/components/upload";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  Alert,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Loading,
  PageTitle,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTimeShort, fromParisInput } from "@/lib/format";
import { KIND_LABELS } from "@/lib/consultation";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Bid, BidKind } from "@/lib/types";

const GRID = "md:grid-cols-[minmax(0,1fr)_9.5rem_7rem_6rem]";
const STATUS_COLOR: Record<string, string> = {
  to_review: "bg-slate-100 text-slate-700 ring-slate-300",
  in_progress: "bg-blue-100 text-blue-800 ring-blue-300",
  submitted: "bg-violet-100 text-violet-800 ring-violet-300",
  won: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  lost: "bg-red-50 text-red-800 ring-red-200",
  dropped: "bg-slate-100 text-slate-500 ring-slate-200",
};

export default function BidsPage() {
  const router = useRouter();
  const bids = useApi<Bid[]>("/bids");
  const [kind, setKind] = useState<BidKind>("tender");
  const [form, setForm] = useState({ title: "", buyer_name: "", deadline: "" });
  const create = useAction();
  const upload = useAction();
  const consultation = kind === "consultation";

  /** « Nouvelle consultation » (25/11): the documents first; Pilao reads them and fills the
   * card (client, addresses, contact, reference) and finds the price file. */
  async function onDocuments(files: File[]) {
    const bid = await create.run(() =>
      api<Bid>("/bids", { json: { kind: "consultation" } }),
    );
    if (!bid) return;
    if (files.length) {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      // refused (too big, a virus…): the dossier's « Documents reçus » step takes them again
      await upload.run(() =>
        api(`/bids/${bid.id}/dce?mode=new&analyse=true`, { form }),
      );
    }
    router.push(`/dossiers/${bid.id}${files.length ? "?onglet=dce" : ""}`);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const bid = await create.run(() =>
      api<Bid>("/bids", {
        json: {
          kind,
          title: form.title,
          buyer_name: form.buyer_name || null,
          deadline_at: fromParisInput(form.deadline),
        },
      }),
    );
    if (bid) router.push(`/dossiers/${bid.id}`);
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Dossiers de réponse"
        subtitle="Un dossier par appel d'offres ou par consultation d'une entreprise : déposez les documents, chiffrez, préparez votre réponse ou votre devis."
        icon="bids"
        color="blue"
      />
      <MailInbox
        bids={bids.data ?? []}
        onFiled={(id) => router.push(`/dossiers/${id}`)}
      />
      <Card title="Nouveau dossier" color="blue">
        <fieldset className="mb-4">
          <legend className="text-sm font-medium text-slate-800">
            Type de dossier
          </legend>
          <div className="mt-1 flex flex-wrap gap-x-6 gap-y-2">
            {(
              [
                ["tender", "Appel d'offres public"],
                ["consultation", "Consultation d'une entreprise (devis)"],
              ] as [BidKind, string][]
            ).map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="bid-kind"
                  value={value}
                  checked={kind === value}
                  onChange={() => setKind(value)}
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        {consultation ? (
          <div className="space-y-3">
            <UploadButton
              id="consultation-upload"
              label="Créer et lire les documents"
              title="Glissez ici les documents reçus du client"
              hint="Fiche d'intervention, DPGF, bordereau, CCTP, plans… en PDF, Word, Excel, images ou ZIP. Pilao remplit la fiche (client, adresses, contact, référence) et trouve le fichier de prix."
              accept=".zip,.pdf,.docx,.doc,.odt,.xlsx,.xls,.ods,.png,.jpg,.jpeg"
              multiple
              busy={create.busy || upload.busy}
              onFiles={onDocuments}
            />
            <p className="text-xs text-slate-500">
              La lecture des documents coûte le prix de la lecture d&apos;un
              fichier de prix, et la comprend. Rien n&apos;est inventé : ce que
              les documents ne disent pas reste à compléter.{" "}
              <button
                type="button"
                className="text-brand-navy underline"
                disabled={create.busy || upload.busy}
                onClick={() => onDocuments([])}
              >
                Créer sans documents
              </button>
            </p>
          </div>
        ) : (
          <>
            <form
              onSubmit={onCreate}
              className="grid items-end gap-3 sm:grid-cols-[2fr_1.5fr_1fr_auto]"
              noValidate
            >
              <Field label="Intitulé" htmlFor="bid-title">
                <Input
                  id="bid-title"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="ex. Nettoyage des écoles de Lyon"
                />
              </Field>
              <Field label="Acheteur" htmlFor="bid-buyer">
                <Input
                  id="bid-buyer"
                  value={form.buyer_name}
                  onChange={(e) =>
                    setForm({ ...form, buyer_name: e.target.value })
                  }
                />
              </Field>
              <Field
                label="Date limite (heure de Paris)"
                htmlFor="bid-deadline"
              >
                <Input
                  id="bid-deadline"
                  type="datetime-local"
                  value={form.deadline}
                  onChange={(e) =>
                    setForm({ ...form, deadline: e.target.value })
                  }
                />
              </Field>
              <Button type="submit" busy={create.busy}>
                Créer
              </Button>
            </form>
            <p className="mt-2 text-xs text-slate-500">
              L&apos;acheteur et la date limite seront repris du DCE s&apos;ils
              sont laissés vides.
            </p>
          </>
        )}
        {create.error && (
          <div className="mt-3">
            <Alert tone="danger">{create.error}</Alert>
          </div>
        )}
      </Card>
      {bids.error && <Alert tone="danger">{bids.error}</Alert>}
      {!bids.data ? (
        <Loading />
      ) : bids.data.length === 0 ? (
        <Empty>
          Aucun dossier : créez-en un pour déposer votre premier DCE.
        </Empty>
      ) : (
        <Card
          title={`Mes dossiers (${bids.data.length})`}
          color="blue"
          icon="bids"
          flush
        >
          <div
            aria-hidden="true"
            className={`hidden gap-x-4 px-5 py-2 md:grid ${GRID} ${tableHead}`}
          >
            <span>Dossier</span>
            <span>Date limite</span>
            <span>Statut</span>
            <span />
          </div>
          <ul>
            {bids.data.map((b) => (
              <li
                key={b.id}
                className={`grid items-center gap-x-4 gap-y-1 px-5 py-3 md:grid ${GRID} ${tableRow}`}
              >
                <div className="min-w-0">
                  <Link
                    href={`/dossiers/${b.id}`}
                    className="font-semibold text-brand-navy underline"
                  >
                    {b.title}
                  </Link>
                  <p className="text-sm text-slate-600">
                    {b.kind === "consultation" && (
                      <span className="mr-2 inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-inset ring-emerald-300">
                        {KIND_LABELS.consultation}
                      </span>
                    )}
                    {b.buyer_name ??
                      (b.kind === "consultation"
                        ? "Client non renseigné"
                        : "Acheteur non renseigné")}
                  </p>
                </div>
                <p className="text-sm text-slate-800">
                  <span className="md:hidden">Date limite : </span>
                  {formatDateTimeShort(b.deadline_at)}
                </p>
                <div>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${STATUS_COLOR[b.status] ?? STATUS_COLOR.to_review}`}
                  >
                    {BID_STATUS[b.status] ?? b.status}
                  </span>
                </div>
                <div className="md:text-right">
                  <Link
                    href={`/dossiers/${b.id}`}
                    aria-label={`Ouvrir le dossier ${b.title}`}
                    className="inline-flex rounded-md bg-brand-navy px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-[#0a2a63]"
                  >
                    Ouvrir
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
