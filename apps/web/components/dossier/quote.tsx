"use client";

import { useState } from "react";

import { PaidButton } from "@/components/paid-button";
import { Alert, Button, Card, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { inclusionSource, quoteAction, vatLabel } from "@/lib/consultation";
import type { TabId } from "@/lib/dossier";
import { formatCents, formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Inclusion, Quote, QuoteState } from "@/lib/types";

type DownloadUrl = { url: string; expires_in: number };
const VAT_RATES = [2000, 1000, 550, 0];

const drafting = (s: QuoteState) => s.quote?.status === "drafting";

/**
 * The company's quote for a consultation (ADR-052): its number, « Prestations comprises »
 * read in the CCTP (each with its page), the table of the « Prix » tab, HT / TVA / TTC.
 * Pilao prepares a draft to read: the company sends it itself.
 */
export function QuoteTab({
  bidId,
  onOpen,
}: {
  bidId: string;
  onOpen: (tab: TabId) => void;
}) {
  const state = useApi<QuoteState>(`/bids/${bidId}/quote`, drafting);
  const act = useAction();
  const data = state.data;
  if (!data)
    return state.error ? <Alert tone="danger">{state.error}</Alert> : null;
  const step = quoteAction(data);

  async function prepare(summarize: boolean) {
    const done = await act.run(() =>
      api<Quote>(`/bids/${bidId}/quote`, { json: { summarize } }),
    );
    if (done) state.reload();
  }

  const intro = data.cctp
    ? "Pilao lit le CCTP pour écrire « Prestations comprises » (chaque point avec sa page), reprend votre chiffrage de l'onglet Prix et prépare le devis en Word et en PDF."
    : "Aucun CCTP dans les documents reçus : le devis reprend votre chiffrage de l'onglet Prix, sans « Prestations comprises » lues par Pilao.";

  return (
    <div className="space-y-6">
      {step !== "ready" && (
        <Card title="Votre devis" color="green" icon="documents">
          <div className="space-y-3">
            {step === "blocked" && (
              <>
                <Alert tone="warning">{data.blocking}</Alert>
                <Button variant="secondary" onClick={() => onOpen("prix")}>
                  Ouvrir l&apos;onglet Prix
                </Button>
              </>
            )}
            {(step === "prepare_paid" ||
              step === "prepare_free" ||
              step === "error") && (
              <>
                {step === "error" && data.quote?.error && (
                  <Alert tone="danger">{data.quote.error}</Alert>
                )}
                <p className="text-sm text-slate-700">{intro}</p>
                {data.cctp ? (
                  <PaidButton
                    action="quote_draft"
                    label="Préparer le devis"
                    busy={act.busy}
                    onClick={() => prepare(true)}
                  />
                ) : (
                  <Button busy={act.busy} onClick={() => prepare(true)}>
                    Préparer le devis
                  </Button>
                )}
              </>
            )}
            {step === "drafting" && (
              <p role="status" className="text-sm text-slate-700">
                Préparation du devis {data.quote?.number} en cours…
              </p>
            )}
            {act.error && <Alert tone="danger">{act.error}</Alert>}
          </div>
        </Card>
      )}
      {step === "ready" && data.quote && (
        <ReadyQuote
          key={data.quote.updated_at}
          bidId={bidId}
          quote={data.quote}
          cctp={data.cctp}
          blocking={data.blocking}
          busy={act.busy}
          error={act.error}
          onPrepare={prepare}
          onSaved={state.reload}
        />
      )}
    </div>
  );
}

function ReadyQuote({
  bidId,
  quote,
  cctp,
  blocking,
  busy,
  error,
  onPrepare,
  onSaved,
}: {
  bidId: string;
  quote: Quote;
  cctp: boolean;
  blocking: string | null;
  busy: boolean;
  error: string | null;
  onPrepare: (summarize: boolean) => Promise<void>;
  onSaved: () => void;
}) {
  const [validity, setValidity] = useState(String(quote.validity_days));
  const [vat, setVat] = useState(quote.vat_bp);
  const [items, setItems] = useState<Inclusion[]>(quote.inclusions);
  const [added, setAdded] = useState("");
  const [bad, setBad] = useState<string | null>(null);
  const save = useAction();
  const download = useAction();

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    const days = Number(validity);
    if (!Number.isInteger(days) || days < 1 || days > 365)
      return setBad("Validité : un nombre de jours entre 1 et 365.");
    setBad(null);
    const extra = added.trim()
      ? [{ text: added.trim(), file: null, page: null }]
      : [];
    const done = await save.run(() =>
      api<Quote>(`/bids/${bidId}/quote`, {
        method: "PUT",
        json: {
          validity_days: days,
          vat_bp: vat,
          inclusions: [...items, ...extra],
        },
      }),
    );
    if (done) onSaved();
  }

  async function get(format: "pdf" | "docx" | "zip") {
    const link = await download.run(() =>
      api<DownloadUrl>(`/bids/${bidId}/quote/download`, {
        json: { format },
      }),
    );
    if (link) window.location.assign(link.url);
  }

  return (
    <Card
      title={`Devis n° ${quote.number}`}
      color="green"
      icon="documents"
      actions={
        <span className="text-xs text-slate-600">
          Préparé le {formatDateTime(quote.updated_at)}
        </span>
      }
    >
      <div className="space-y-5">
        {quote.stale && (
          <Alert tone="warning">
            Vos prix ont changé depuis ce devis : mettez-le à jour avant de
            l&apos;envoyer.
          </Alert>
        )}
        {blocking && <Alert tone="warning">{blocking}</Alert>}
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          {quote.total_ht_cents == null ? (
            <>
              <dt className="text-slate-600">Montant</dt>
              <dd>Prix unitaires (selon les quantités commandées)</dd>
            </>
          ) : (
            <>
              <dt className="text-slate-600">Total HT</dt>
              <dd className="font-semibold">
                {formatCents(quote.total_ht_cents)}
              </dd>
              <dt className="text-slate-600">TVA {vatLabel(quote.vat_bp)}</dt>
              <dd>{formatCents(quote.vat_cents)}</dd>
              <dt className="text-slate-600">Total TTC</dt>
              <dd className="font-semibold">
                {formatCents(quote.total_ttc_cents)}
              </dd>
            </>
          )}
          {quote.options_total_cents > 0 && (
            <>
              <dt className="text-slate-600">Options (hors total)</dt>
              <dd>{formatCents(quote.options_total_cents)} HT</dd>
            </>
          )}
        </dl>
        <div className="flex flex-wrap gap-2">
          <Button
            busy={download.busy}
            disabled={!quote.has_pdf}
            onClick={() => get("pdf")}
          >
            Télécharger le PDF
          </Button>
          <Button variant="secondary" onClick={() => get("docx")}>
            Télécharger le Word
          </Button>
          <Button variant="secondary" onClick={() => get("zip")}>
            Devis et fichier du client (ZIP)
          </Button>
        </div>
        {!quote.has_pdf && (
          <p className="text-xs text-amber-800">
            Le PDF n&apos;a pas pu être fait : téléchargez le Word et
            enregistrez-le en PDF.
          </p>
        )}
        {download.error && <Alert tone="danger">{download.error}</Alert>}

        <form onSubmit={onSave} noValidate className="space-y-4">
          <section>
            <h3 className="text-sm font-semibold text-slate-900">
              Prestations comprises
            </h3>
            {items.length === 0 && (
              <p className="text-sm text-slate-600">
                Aucune : le devis renvoie au dossier du client.
              </p>
            )}
            <ul className="mt-2 space-y-2">
              {items.map((item, i) => (
                <li
                  key={`${i}-${item.text}`}
                  className="flex items-start justify-between gap-3 rounded-md bg-slate-50 px-3 py-2 text-sm"
                >
                  <span>
                    {item.text}{" "}
                    <span className="text-xs text-slate-500">
                      ({inclusionSource(item)})
                    </span>
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    aria-label={`Retirer : ${item.text}`}
                    onClick={() => setItems(items.filter((_, j) => j !== i))}
                  >
                    Retirer
                  </Button>
                </li>
              ))}
            </ul>
            <div className="mt-2">
              <Field label="Ajouter une prestation" htmlFor="quote-add">
                <Input
                  id="quote-add"
                  value={added}
                  maxLength={400}
                  placeholder="ex. Évacuation des déchets du nettoyage"
                  onChange={(e) => setAdded(e.target.value)}
                />
              </Field>
            </div>
          </section>
          <div className="grid gap-3 sm:grid-cols-[10rem_10rem]">
            <Field label="Validité (jours)" htmlFor="quote-validity">
              <Input
                id="quote-validity"
                inputMode="numeric"
                value={validity}
                onChange={(e) => setValidity(e.target.value)}
              />
            </Field>
            <Field label="TVA" htmlFor="quote-vat">
              <Select
                id="quote-vat"
                value={vat}
                onChange={(e) => setVat(Number(e.target.value))}
              >
                {[...new Set([...VAT_RATES, quote.vat_bp])].map((bp) => (
                  <option key={bp} value={bp}>
                    {vatLabel(bp)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {bad && <p className="text-xs text-red-700">{bad}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" busy={save.busy} disabled={!!blocking}>
              Enregistrer et refaire le devis
            </Button>
            <Button
              type="button"
              variant="secondary"
              busy={busy}
              disabled={!!blocking}
              onClick={() => onPrepare(false)}
            >
              Mettre à jour avec les prix
            </Button>
            {cctp && (
              <PaidButton
                action="quote_draft"
                label="Relire le CCTP"
                variant="secondary"
                busy={busy}
                disabled={!!blocking}
                onClick={() => onPrepare(true)}
              />
            )}
          </div>
          <p className="text-xs text-slate-500">
            Refaire le devis est gratuit ; seule une nouvelle lecture du CCTP
            coûte des crédits.
          </p>
          {(save.error || error) && (
            <Alert tone="danger">{save.error ?? error}</Alert>
          )}
        </form>
      </div>
    </Card>
  );
}
