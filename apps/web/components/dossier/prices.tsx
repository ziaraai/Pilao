"use client";

import { type ReactNode, useState } from "react";

import { PaidButton } from "@/components/paid-button";
import { RatesForm } from "@/components/profile/rates";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { centsToInput, formatCents, parseEuros } from "@/lib/format";
import {
  chosenLabel,
  downloadLabel,
  sectionsOf,
  toggleSection,
} from "@/lib/consultation";
import { useAction, useApi } from "@/lib/hooks";
import { DCE_KINDS } from "@/lib/labels";
import {
  bySection,
  decimalText,
  fileLabel,
  hoursInput,
  hoursPlaceholder,
  hoursWarning,
  lineHint,
  missingText,
  totalLabel,
  quantityText,
  ratesSummary,
  sourceText,
} from "@/lib/prices";
import type {
  DceFile,
  DceVersion,
  PriceFile,
  PriceLine,
  PriceSheet,
  Prices,
  Rates,
} from "@/lib/types";

type DownloadUrl = { url: string; expires_in: number };

const reading = (p: Prices) =>
  p.files.some((f) => f.sheet?.status === "reading");

/**
 * Chiffrage (ADR-049): the buyer's price files (BPU, DPGF, DQE). Pilao reads the lines to
 * price, the company types hours or prices, Pilao computes with its rates and hands back
 * the buyer's own file, filled. Pilao never guesses an hour or a price.
 */
export function PricesTab({
  bidId,
  consultation = false,
}: {
  bidId: string;
  /** A request for a quote (ADR-052): the rubriques not priced are set aside. */
  consultation?: boolean;
}) {
  const prices = useApi<Prices>(`/bids/${bidId}/prices`, reading);
  const [editRates, setEditRates] = useState(false);
  const data = prices.data;
  if (!data)
    return prices.error ? <Alert tone="danger">{prices.error}</Alert> : null;

  function rates() {
    setEditRates(false);
    prices.reload(); // every price computed from the rates changes
  }

  return (
    <div className="space-y-6">
      <Card
        title="Vos taux"
        color="brand"
        actions={
          !editRates && (
            <Button variant="secondary" onClick={() => setEditRates(true)}>
              Modifier les taux
            </Button>
          )
        }
      >
        {editRates ? (
          <RatesForm rates={data.rates} onSaved={rates} />
        ) : (
          <p className="text-sm text-slate-700">{ratesSummary(data.rates)}</p>
        )}
      </Card>
      {data.files.length === 0 ? (
        <Empty>
          {consultation
            ? "Pilao n'a pas trouvé de document avec des quantités à chiffrer. S'il y en a un parmi les documents reçus, indiquez-le ci-dessous."
            : "Aucun fichier de prix (BPU, DPGF, DQE) dans le DCE. S'il y en a un, vérifiez son type dans l'onglet DCE."}
        </Empty>
      ) : (
        <>
          {consultation &&
            data.files.length > 1 &&
            data.files.every((f) => f.sheet === null) && (
              <Alert tone="info">
                Pilao a trouvé {data.files.length} documents avec des quantités
                : lisez celui qui sert à votre devis.
              </Alert>
            )}
          {data.files.map((f) => (
            <PriceFileCard
              key={f.dce_file_id}
              bidId={bidId}
              file={f}
              rates={data.rates}
              consultation={consultation}
              onChanged={(next) => prices.setData(next)}
              reload={prices.reload}
            />
          ))}
        </>
      )}
      {consultation && (
        <OtherDocuments
          bidId={bidId}
          open={data.files.length === 0}
          priced={data.files.map((f) => f.dce_file_id)}
          onChosen={prices.reload}
        />
      )}
    </div>
  );
}

function PriceFileCard({
  bidId,
  file,
  rates,
  consultation,
  onChanged,
  reload,
}: {
  bidId: string;
  file: PriceFile;
  rates: Rates;
  consultation: boolean;
  onChanged: (p: Prices) => void;
  reload: () => void;
}) {
  const act = useAction();
  const sheet = file.sheet;
  const title = `${DCE_KINDS[file.kind] ?? file.kind.toUpperCase()} · ${fileLabel(file.path)}`;

  async function readFile() {
    const next = await act.run(() =>
      api<Prices>(`/bids/${bidId}/prices/${file.dce_file_id}/read`, {
        method: "POST",
      }),
    );
    if (next) {
      onChanged(next);
      reload(); // start following the reading
    }
  }

  const readButton = (label: string) => (
    <PaidButton
      action="price_read"
      label={label}
      variant={sheet?.status === "ready" ? "secondary" : "primary"}
      busy={act.busy}
      onClick={readFile}
    />
  );

  return (
    <Card title={title} color="amber" flush id={`prix-${file.dce_file_id}`}>
      {!(sheet?.status === "ready" && !act.error) && (
        <div className="space-y-3 p-5">
          {!file.fillable && file.readable === false ? (
            <Alert tone="warning">
              Pilao n&apos;a pas pu lire le texte de ce document : demandez la
              version Excel du bordereau{" "}
              {consultation ? "au client" : "à l'acheteur"}, ou une version PDF
              où le texte se sélectionne.
            </Alert>
          ) : sheet === null ? (
            <div className="space-y-2">
              <p className="text-sm text-slate-700">
                {file.fillable
                  ? `Pilao repère les lignes à chiffrer et les cases à remplir, et y met les prix de votre liste quand une ligne correspond. Vous complétez vos heures ou vos prix ; Pilao calcule et remplit le fichier ${consultation ? "du client" : "de l'acheteur"}.`
                  : "Ce document ne se remplit pas : Pilao en lit les lignes et les quantités page par page (le texte en image compris), y met les prix de votre liste quand une ligne correspond, puis écrit un DPGF Excel avec vos prix et les totaux."}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                {readButton(
                  file.fillable ? "Lire le fichier" : "Lire le document",
                )}
                {consultation && (
                  <NotAPriceFile fileId={file.dce_file_id} onDone={reload} />
                )}
              </div>
            </div>
          ) : sheet.status === "reading" ? (
            <p role="status" className="text-sm text-slate-700">
              Lecture du fichier en cours…
            </p>
          ) : sheet.status === "error" ? (
            <div className="space-y-2">
              <Alert tone="danger">{sheet.error}</Alert>
              {readButton("Relancer la lecture")}
            </div>
          ) : null}
          {act.error && <Alert tone="danger">{act.error}</Alert>}
        </div>
      )}
      {sheet?.status === "ready" && (
        <SheetEditor
          // a new reading or new rates: start again from the server's figures
          key={`${sheet.id}:${sheet.lines.map((l) => l.id).join()}:${ratesSummary(rates)}`}
          sheet={sheet}
          rates={rates}
          consultation={consultation}
          readAgain={readButton(
            file.fillable ? "Relire le fichier" : "Relire le document",
          )}
          onSaved={reload} // the same lines of the other price files follow
        />
      )}
    </Card>
  );
}

function SheetEditor({
  sheet,
  rates,
  consultation,
  readAgain,
  onSaved,
}: {
  sheet: PriceSheet;
  rates: Rates;
  consultation: boolean;
  readAgain: ReactNode;
  onSaved: () => void;
}) {
  const [current, setCurrent] = useState(sheet);
  const [seen, setSeen] = useState(sheet);
  if (sheet !== seen) {
    // read again by the page (a twin file was typed in): the server's figures win
    setSeen(sheet);
    setCurrent(sheet);
  }
  const save = useAction();
  const download = useAction();
  const rate = current.rate_cents ?? rates.hourly_rate_cents;

  async function send(body: Record<string, unknown>) {
    const next = await save.run(() =>
      api<PriceSheet>(`/price-sheets/${current.id}`, {
        method: "PUT",
        json: body,
      }),
    );
    if (next) {
      setCurrent(next);
      onSaved();
    }
  }

  return (
    <div className="space-y-4 p-5">
      {current.notes.length > 0 && (
        <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
          <p className="font-semibold">Consignes du fichier</p>
          <ul className="ml-5 list-disc">
            {current.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      {current.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      {consultation && (
        <RubriquePicker
          all={sectionsOf(current.lines)}
          excluded={current.excluded_sections}
          onChange={(excluded) => send({ excluded_sections: excluded })}
        />
      )}
      <DossierRate
        sheet={current}
        companyRate={rates.hourly_rate_cents}
        onSave={(cents) => send({ set_rate: true, rate_cents: cents })}
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[44rem] text-sm">
          <thead>
            <tr className={tableHead}>
              <th className="px-2 py-2 text-left">Désignation</th>
              <th className="px-2 py-2 text-right">Quantité</th>
              <th className="px-2 py-2 text-right">Heures par unité</th>
              <th className="px-2 py-2 text-right">Prix unitaire HT</th>
              <th className="px-2 py-2 text-right">Total HT</th>
            </tr>
          </thead>
          <tbody>
            {bySection(current.lines)
              // a consultation shows only the rubriques chosen in the list above
              .filter(
                (group) =>
                  !consultation ||
                  !current.excluded_sections.includes(group.section),
              )
              .map((group) => (
                <SectionRows
                  key={`${group.section}-${group.lines[0].id}`}
                  section={group.section}
                  lines={group.lines}
                  excluded={current.excluded_sections.includes(group.section)}
                  rates={rates}
                  rateCents={current.rate_cents}
                  rate={rate}
                  onEntry={(id, entry) => send({ entries: { [id]: entry } })}
                />
              ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-slate-300 font-bold">
              <td className="px-2 py-2" colSpan={4}>
                {totalLabel(current.lines)}
                <span className="ml-3 text-xs font-normal text-amber-800">
                  {current.missing_count > 0
                    ? missingText(current.missing_count)
                    : ""}
                </span>
              </td>
              <td className="px-2 py-2 text-right">
                {formatCents(current.total_cents)}
              </td>
            </tr>
            {current.lines.some((l) => l.option) && (
              <tr className="text-slate-700">
                <td className="px-2 py-1" colSpan={4}>
                  Options, chiffrées à part (hors total)
                </td>
                <td className="px-2 py-1 text-right">
                  {formatCents(current.options_total_cents)}
                </td>
              </tr>
            )}
          </tfoot>
        </table>
      </div>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          busy={download.busy}
          onClick={async () => {
            const link = await download.run(() =>
              api<DownloadUrl>(`/price-sheets/${current.id}/export`, {
                method: "POST",
              }),
            );
            if (link) window.location.assign(link.url);
          }}
        >
          {downloadLabel(current.mode)}
        </Button>
        {readAgain}
        <span className="text-xs text-slate-600">
          {missingText(current.missing_count)}.{" "}
          {current.mode === "document"
            ? "Les prix manquants restent en cases jaunes dans le DPGF ; les montants et les totaux s'y calculent seuls."
            : "Les prix manquants restent tels que l'acheteur les a laissés."}
        </span>
      </div>
      {download.error && <Alert tone="danger">{download.error}</Alert>}
    </div>
  );
}

function DossierRate({
  sheet,
  companyRate,
  onSave,
}: {
  sheet: PriceSheet;
  companyRate: number | null;
  onSave: (cents: number | null) => void;
}) {
  const [value, setValue] = useState(centsToInput(sheet.rate_cents));
  const [bad, setBad] = useState(false);
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm text-slate-800" htmlFor={`rate-${sheet.id}`}>
        Taux horaire pour ce dossier (€ HT)
        <Input
          id={`rate-${sheet.id}`}
          inputMode="decimal"
          className="mt-1 w-40"
          placeholder={
            companyRate == null ? "à saisir" : centsToInput(companyRate)
          }
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => {
            const cents = value.trim() === "" ? null : parseEuros(value);
            setBad(cents === null && value.trim() !== "");
            if (cents !== null || value.trim() === "") {
              if (cents !== sheet.rate_cents) onSave(cents);
            }
          }}
        />
      </label>
      <span className="pb-2 text-xs text-slate-600">
        {bad ? "Taux invalide (ex. : 24,50)." : "Vide : votre taux habituel."}
      </span>
    </div>
  );
}

function SectionRows({
  section,
  lines,
  excluded,
  rates,
  rateCents,
  rate,
  onEntry,
}: {
  section: string;
  lines: PriceLine[];
  excluded: boolean;
  rates: Rates;
  rateCents: number | null;
  rate: number | null;
  onEntry: (
    id: string,
    entry: { hours: string | null; price_cents: number | null },
  ) => void;
}) {
  return (
    <>
      {section && (
        <tr>
          <th
            colSpan={5}
            scope="colgroup"
            className={`px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide ${excluded ? "bg-slate-100 text-slate-500" : "bg-amber-50 text-amber-900"}`}
          >
            {section}
          </th>
        </tr>
      )}
      {lines.map((line) =>
        line.excluded ? (
          <tr key={line.id} className={`${tableRow} text-slate-400`}>
            <td className="px-2 py-2">{line.label}</td>
            <td className="whitespace-nowrap px-2 py-2 text-right">
              {quantityText(line.quantity, line.unit)}
            </td>
            <td className="px-2 py-2 text-right text-xs" colSpan={3}>
              mise de côté
            </td>
          </tr>
        ) : (
          <LineRow
            // a line changed from elsewhere (its twin in another file) shows its new figures
            key={`${line.id}:${line.hours}:${line.source === "price" ? line.price_cents : ""}`}
            line={line}
            rates={rates}
            rateCents={rateCents}
            rate={rate}
            onEntry={onEntry}
          />
        ),
      )}
    </>
  );
}

function LineRow({
  line,
  rates,
  rateCents,
  rate,
  onEntry,
}: {
  line: PriceLine;
  rates: Rates;
  rateCents: number | null;
  rate: number | null;
  onEntry: (
    id: string,
    entry: { hours: string | null; price_cents: number | null },
  ) => void;
}) {
  const [hours, setHours] = useState(decimalText(line.hours));
  const [price, setPrice] = useState(
    line.source === "price" ? centsToInput(line.price_cents) : "",
  );
  const [bad, setBad] = useState<string | null>(null);
  const hint = lineHint(line, rates, rateCents) ?? hoursWarning(line);

  function saveHours() {
    const parsed = hoursInput(hours);
    if (parsed === "invalid") return setBad("Nombre d'heures invalide.");
    setBad(null);
    if (parsed === line.hours && line.source !== "price") return;
    setPrice("");
    onEntry(line.id, { hours: parsed, price_cents: null });
  }

  function savePrice() {
    const cents = price.trim() === "" ? null : parseEuros(price);
    if (cents === null && price.trim() !== "")
      return setBad("Prix invalide (ex. : 62,50).");
    setBad(null);
    if (cents === (line.source === "price" ? line.price_cents : null)) return;
    if (cents !== null) setHours("");
    onEntry(line.id, {
      hours: cents === null ? (hoursInput(hours) as string | null) : null,
      price_cents: cents,
    });
  }

  return (
    <tr className={tableRow}>
      <td className="px-2 py-2 align-top">
        <span className="font-medium text-slate-900">{line.label}</span>
        {line.option && (
          <span
            className="ml-2 rounded bg-sky-100 px-1.5 py-0.5 text-xs font-medium text-sky-800"
            title="Chiffrée, mais hors du total de l'offre de base"
          >
            Option
          </span>
        )}
        {(bad || hint) && (
          <span
            className={`block text-xs ${bad ? "text-red-700" : "text-amber-800"}`}
          >
            {bad ?? hint}
          </span>
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-2 text-right align-top text-slate-700">
        {quantityText(line.quantity, line.unit)}
      </td>
      <td className="px-2 py-2 text-right align-top">
        {line.hourly ? (
          <span className="text-xs text-slate-500">prix à l&apos;heure</span>
        ) : (
          <Input
            aria-label={`Heures : ${line.label}`}
            inputMode="decimal"
            className="ml-auto w-20 text-right"
            placeholder={hoursPlaceholder(line.unit)}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            onBlur={saveHours}
          />
        )}
      </td>
      <td className="px-2 py-2 text-right align-top">
        <Input
          aria-label={`Prix unitaire HT : ${line.label}`}
          inputMode="decimal"
          className="ml-auto w-28 text-right"
          placeholder={
            line.price_cents != null && line.source !== "price"
              ? centsToInput(line.price_cents)
              : "€"
          }
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          onBlur={savePrice}
        />
        <span className="block text-xs text-slate-500">
          {line.price_cents != null && line.source !== "price"
            ? `${formatCents(line.price_cents)} · ${sourceText(line, rate)}`
            : sourceText(line, rate)}
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-2 text-right align-top font-medium">
        {formatCents(line.total_cents)}
      </td>
    </tr>
  );
}

/**
 * Consultations (ADR-052): the rubriques the company prices, chosen in one list. Only those
 * are shown and counted; the others are set aside (neither filled nor counted).
 */
function RubriquePicker({
  all,
  excluded,
  onChange,
}: {
  all: string[];
  excluded: string[];
  onChange: (excluded: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  // a click shows at once; the server's answer then becomes the truth again
  const [draft, setDraft] = useState(excluded);
  const [seen, setSeen] = useState(excluded);
  if (excluded !== seen) {
    setSeen(excluded);
    setDraft(excluded);
  }
  const change = (next: string[]) => {
    setDraft(next);
    onChange(next);
  };
  const hidden = draft.filter((s) => all.includes(s)).length;
  return (
    <div className="relative">
      <p className="text-sm font-medium text-slate-800">
        Rubriques que vous chiffrez
      </p>
      <button
        type="button"
        aria-expanded={open}
        aria-controls="rubriques-list"
        onClick={() => setOpen(!open)}
        className="mt-1 inline-flex min-w-64 items-center justify-between gap-3 rounded-md border border-slate-300 bg-white px-3 py-2 text-left text-sm text-slate-900 hover:border-slate-400"
      >
        {chosenLabel(all, draft)}
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div
          id="rubriques-list"
          role="group"
          aria-label="Rubriques que vous chiffrez"
          className="absolute z-10 mt-1 w-full max-w-lg rounded-md border border-slate-200 bg-white p-2 shadow-lg"
        >
          <div className="flex flex-wrap gap-2 border-b border-slate-100 pb-2">
            <Button variant="secondary" onClick={() => change([])}>
              Tout cocher
            </Button>
            <Button variant="secondary" onClick={() => change(all)}>
              Tout décocher
            </Button>
          </div>
          <ul className="max-h-72 overflow-y-auto py-1">
            {all.map((section) => (
              <li key={section}>
                <label className="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={!draft.includes(section)}
                    onChange={(e) =>
                      change(toggleSection(draft, section, e.target.checked))
                    }
                  />
                  <span>{section}</span>
                </label>
              </li>
            ))}
          </ul>
          <div className="border-t border-slate-100 pt-2 text-right">
            <Button onClick={() => setOpen(false)}>Fermer</Button>
          </div>
        </div>
      )}
      <p className="mt-1 text-xs text-slate-600">
        {hidden === 1
          ? "1 rubrique mise de côté n'est pas affichée : elle n'est ni remplie ni comptée dans votre total."
          : hidden > 1
            ? `${hidden} rubriques mises de côté ne sont pas affichées : elles ne sont ni remplies ni comptées dans votre total.`
            : "Toutes les rubriques sont chiffrées."}
      </p>
    </div>
  );
}

/** A document Pilao took for a price file by mistake (consultations, 25/11). */
function NotAPriceFile({
  fileId,
  onDone,
}: {
  fileId: string;
  onDone: () => void;
}) {
  const act = useAction();
  return (
    <span className="inline-flex flex-col gap-1">
      <Button
        variant="secondary"
        busy={act.busy}
        onClick={async () => {
          const done = await act.run(() =>
            api<DceFile>(`/dce-files/${fileId}`, {
              method: "PATCH",
              json: { kind: "other" },
            }),
          );
          if (done) onDone();
        }}
      >
        Ce n&apos;est pas le fichier de prix
      </Button>
      {act.error && <span className="text-xs text-red-700">{act.error}</span>}
    </span>
  );
}

/**
 * The other documents received (consultations, 25/11): the company points at the one with
 * the quantities when Pilao did not find it (« C'est le fichier de prix »).
 */
function OtherDocuments({
  bidId,
  open,
  priced,
  onChosen,
}: {
  bidId: string;
  open: boolean;
  priced: string[];
  onChosen: () => void;
}) {
  const versions = useApi<DceVersion[]>(`/bids/${bidId}/dce`);
  const act = useAction();
  const latest = versions.data?.find((v) => v.status === "ready");
  const others = (latest?.files ?? []).filter((f) => !priced.includes(f.id));
  if (!others.length) return null;

  async function choose(file: DceFile) {
    const done = await act.run(() =>
      api<DceFile>(`/dce-files/${file.id}`, {
        method: "PATCH",
        json: { kind: "dpgf" },
      }),
    );
    if (done) {
      versions.reload();
      onChosen();
    }
  }

  return (
    <details
      open={open}
      className="rounded-lg bg-white p-4 ring-1 ring-slate-200"
    >
      <summary className="cursor-pointer text-sm font-semibold text-slate-800">
        Le fichier de prix est un autre document ?
      </summary>
      <ul className="mt-3 divide-y divide-slate-100">
        {others.map((f) => (
          <li
            key={f.id}
            className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
          >
            <span className="min-w-0 break-all">
              {fileLabel(f.path)}{" "}
              <span className="text-xs text-slate-500">
                ({DCE_KINDS[f.detected_kind] ?? f.detected_kind})
              </span>
            </span>
            <Button
              variant="secondary"
              busy={act.busy}
              onClick={() => choose(f)}
            >
              C&apos;est le fichier de prix
            </Button>
          </li>
        ))}
      </ul>
      {act.error && (
        <div className="mt-2">
          <Alert tone="danger">{act.error}</Alert>
        </div>
      )}
    </details>
  );
}
