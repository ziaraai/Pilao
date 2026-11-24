"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { bidChoices, piecesLine, receivedLine } from "@/lib/dce-mail";
import { useAction, useApi } from "@/lib/hooks";
import type { Bid, DceMail, DceNotice, InboundMail } from "@/lib/types";

/** The address in a box, with « Copier » (ADR-055). */
function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false); // no clipboard (old browser): the address stays selectable
    }
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <code className="rounded bg-slate-100 px-2 py-1 font-mono text-sm break-all text-brand-navy select-all">
        {address}
      </code>
      <Button type="button" variant="secondary" onClick={copy}>
        {copied ? "Copiée" : "Copier"}
      </Button>
    </span>
  );
}

/** Profil: the company's DCE address and its three uses. */
export function DceMailCard() {
  const mail = useApi<DceMail>("/dce-mail");
  if (!mail.data?.active) return null; // the mailbox is not switched on yet
  return (
    <Card
      title="Adresse e-mail des DCE"
      color="blue"
      icon="bids"
      id="adresse-dce"
    >
      <div className="space-y-3 text-sm text-slate-700">
        <p>
          Votre adresse personnelle pour recevoir les DCE dans Pilao :{" "}
          <CopyAddress address={mail.data.address} />
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <b>Transférez</b> l&apos;e-mail de la plateforme ou de
            l&apos;acheteur avec ses pièces jointes : Pilao les range dans le
            bon dossier.
          </li>
          <li>
            <b>Donnez-la aux plateformes</b> comme adresse de contact : les avis
            de modification du DCE arrivent dans le dossier.
          </li>
          <li>
            Pilao ne reconnaît pas le dossier ? Le message vous attend dans{" "}
            <b>« À classer »</b> sur la page Dossiers.
          </li>
        </ul>
        <p className="text-xs text-slate-500">
          Rien n&apos;est analysé sans votre feu vert. Les fichiers sont passés
          à l&apos;antivirus ; les messages sont effacés de la boîte une fois
          lus.
        </p>
      </div>
    </Card>
  );
}

/** The DCE step: « Ou transférez l'e-mail à … ». */
export function DceMailHint() {
  const mail = useApi<DceMail>("/dce-mail");
  if (!mail.data?.active) return null;
  return (
    <p className="mt-3 text-sm text-slate-700">
      Ou transférez l&apos;e-mail avec ses pièces jointes à{" "}
      <CopyAddress address={mail.data.address} /> : Pilao les range ici.
    </p>
  );
}

/** The DCE step: an e-mail of the platform about this dossier (a change, a link). */
export function DceNotices({ bidId }: { bidId: string }) {
  const notices = useApi<DceNotice[]>(`/bids/${bidId}/dce-notices`);
  const dismiss = useAction();
  if (!notices.data?.length) return null;
  async function done(id: string) {
    // an empty reply (204): success is said by the call ending without error
    const ok = await dismiss.run(async () => {
      await api(`/dce-mail/notices/${id}`, { method: "DELETE" });
      return true;
    });
    if (ok) notices.reload();
  }
  return (
    <div className="mb-4 space-y-2">
      {notices.data.map((n) => (
        <Alert key={n.id} tone="warning">
          <span className="block font-semibold">
            E-mail reçu de la plateforme : « {n.subject} »
          </span>
          <span className="block text-xs">{receivedLine(n)}</span>
          {n.links.length > 0 && (
            <span className="mt-1 block">
              Le DCE a peut-être changé : récupérez-le à nouveau (
              {n.links.slice(0, 2).map((link, i) => (
                <span key={link}>
                  {i > 0 && ", "}
                  <a
                    href={link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold underline"
                  >
                    ouvrir le lien{n.links.length > 1 ? ` ${i + 1}` : ""}
                  </a>
                </span>
              ))}
              ), puis déposez la nouvelle version ci-dessous.
            </span>
          )}
          <span className="mt-2 block">
            <Button
              type="button"
              variant="secondary"
              busy={dismiss.busy}
              onClick={() => done(n.id)}
            >
              C&apos;est noté
            </Button>
          </span>
        </Alert>
      ))}
      {dismiss.error && <Alert tone="danger">{dismiss.error}</Alert>}
    </div>
  );
}

/** Dossiers: the e-mails Pilao could not put in a dossier by itself. */
export function MailInbox({
  bids,
  onFiled,
}: {
  bids: Bid[];
  onFiled: (bidId: string) => void;
}) {
  const inbox = useApi<InboundMail[]>("/dce-mail/inbox");
  if (!inbox.data?.length) return null;
  return (
    <Card
      title={`À classer (${inbox.data.length})`}
      color="amber"
      icon="bids"
      id="a-classer"
    >
      <p className="mb-3 text-sm text-slate-700">
        Ces e-mails sont arrivés à votre adresse des DCE, mais Pilao n&apos;a
        pas su dans quel dossier les mettre.
      </p>
      <ul className="space-y-3">
        {inbox.data.map((item) => (
          <InboxItem
            key={item.id}
            item={item}
            bids={bids}
            onDone={(bidId) => {
              inbox.reload();
              if (bidId) onFiled(bidId);
            }}
          />
        ))}
      </ul>
    </Card>
  );
}

function InboxItem({
  item,
  bids,
  onDone,
}: {
  item: InboundMail;
  bids: Bid[];
  onDone: (bidId: string | null) => void;
}) {
  const choices = bidChoices(item, bids);
  // Pilao's suggestion, never a dossier picked at random: else the user chooses
  const [target, setTarget] = useState(item.suggested_bid?.id ?? "");
  const [mode, setMode] = useState<"add" | "new">("add");
  const act = useAction();
  const base = `/dce-mail/inbox/${item.id}`;
  const pieces = item.kind === "dce";

  async function file() {
    const done = await act.run(() =>
      api<{ bid_id: string }>(`${base}/file`, {
        json: { bid_id: target, mode },
      }),
    );
    if (done) onDone(done.bid_id);
  }
  async function create() {
    const done = await act.run(() =>
      api<{ bid_id: string }>(`${base}/new-bid`, { method: "POST" }),
    );
    if (done) onDone(done.bid_id);
  }
  async function ignore() {
    const ok = await act.run(async () => {
      await api(base, { method: "DELETE" });
      return true;
    });
    if (ok) onDone(null);
  }

  return (
    <li className="space-y-2 rounded-md border border-slate-300 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold break-words text-brand-navy">
          {item.subject || "(sans objet)"}
        </span>
        {item.suggested_bid && (
          <Badge tone="info">Peut-être : {item.suggested_bid.title}</Badge>
        )}
      </div>
      <p className="text-xs text-slate-500">{receivedLine(item)}</p>
      <p className="text-sm text-slate-700">{piecesLine(item)}</p>
      {item.skipped.length > 0 && (
        <p className="text-xs text-slate-600">
          Non gardé :{" "}
          {item.skipped.map((s) => `${s.path} (${s.reason})`).join(", ")}
        </p>
      )}
      {item.note && <p className="text-xs text-amber-800">{item.note}</p>}
      {!pieces && item.links.length > 0 && (
        <p className="text-sm">
          <a
            href={item.links[0]}
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold text-brand-navy underline"
          >
            Ouvrir le lien reçu
          </a>
        </p>
      )}
      <div className="flex flex-wrap items-end gap-2">
        {choices.length > 0 && (
          <>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700">Ranger dans</span>
              <Select
                aria-label={`Dossier pour « ${item.subject} »`}
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {!item.suggested_bid && (
                  <option value="">Choisir un dossier…</option>
                )}
                {choices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </Select>
            </label>
            <Button
              type="button"
              busy={act.busy}
              disabled={!target}
              onClick={file}
            >
              Ranger
            </Button>
          </>
        )}
        <Button
          type="button"
          variant="secondary"
          busy={act.busy}
          onClick={create}
        >
          Créer le dossier
        </Button>
        <Button type="button" variant="ghost" busy={act.busy} onClick={ignore}>
          Ignorer
        </Button>
      </div>
      {pieces && choices.length > 0 && (
        <fieldset className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <legend className="sr-only">Ces pièces sont</legend>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name={`mode-${item.id}`}
              checked={mode === "add"}
              onChange={() => setMode("add")}
            />
            Des pièces du DCE (le complètent)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name={`mode-${item.id}`}
              checked={mode === "new"}
              onChange={() => setMode("new")}
            />
            Une nouvelle version publiée par l&apos;acheteur
          </label>
        </fieldset>
      )}
      {act.error && <Alert tone="danger">{act.error}</Alert>}
    </li>
  );
}
