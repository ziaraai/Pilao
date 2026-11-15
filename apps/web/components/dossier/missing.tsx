"use client";

import { useEffect, useRef, useState } from "react";

import { Disclosure } from "@/components/blocks";
import { AddToProfileDialog } from "@/components/dossier/missing-dialog";
import { Alert, Button, Card, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import {
  KIND_META,
  chaptersLabel,
  fillMessage,
  gapMessages,
  isCompanyKind,
  missingTitle,
} from "@/lib/missing";
import type {
  Memoir,
  MissingItem,
  MissingKind,
  MissingList,
  ProfileGaps,
} from "@/lib/types";

const running = (i: MissingItem) =>
  i.fill?.status === "pending" || i.fill?.status === "running";

/**
 * « Ce qu'il manque » (ADR-048), at the top of the Mémoire tab: every missing item of the
 * dossier once, with the way to fill it — the drawer of the profile for a company's datum,
 * an answer in place for a detail of the tender, or the sentence removed. Before the
 * drafting, the empty parts of the profile are named instead.
 */
export function MissingBlock({
  bidId,
  memoirStatus,
  revisionKey,
  onChanged,
}: {
  bidId: string;
  memoirStatus: Memoir["status"] | null;
  /** Changes whenever a chapter changes: the list is read again. */
  revisionKey: string;
  onChanged: () => void;
}) {
  const list = useApi<MissingList>(
    `/bids/${bidId}/missing?v=${encodeURIComponent(revisionKey)}`,
    (d) => d.memoir_busy || d.items.some(running),
  );
  const [open, setOpen] = useState(true);
  const filling = (list.data?.items ?? [])
    .filter(running)
    .map((i) => i.key)
    .join("|");
  const [wasFilling, setWasFilling] = useState(filling);
  const [finished, setFinished] = useState(0);
  if (filling !== wasFilling) {
    // a completion ended: the chapters changed, the memoir must be read again
    if (
      wasFilling.split("|").some((k) => k && !filling.split("|").includes(k))
    ) {
      setFinished((n) => n + 1);
    }
    setWasFilling(filling);
  }
  // the parent's callback may change at each render: only the end of a completion calls it
  const changedRef = useRef(onChanged);
  useEffect(() => {
    changedRef.current = onChanged;
  });
  useEffect(() => {
    if (finished) changedRef.current();
  }, [finished]);

  const data = list.data;
  if (!data)
    return list.error ? <Alert tone="danger">{list.error}</Alert> : null;
  const drafted = memoirStatus !== null && memoirStatus !== "draft";

  function changed(next: MissingList) {
    list.setData(next);
    // a completion runs in the background: read the list again until it ends (setData
    // alone does not start the polling of useApi)
    if (next.memoir_busy || next.items.some(running)) list.reload();
    onChanged();
  }

  return (
    <div className="space-y-4">
      {!drafted && (
        <ProfileGapsCard gaps={data.profile_gaps} onAdded={list.reload} />
      )}
      {data.items.length > 0 ? (
        <Disclosure
          id="bloc-missing"
          title={missingTitle(data.items.length)}
          summary="Complétez-les ici : chaque réponse va dans tous les chapitres concernés."
          open={open}
          onToggle={() => setOpen((o) => !o)}
        >
          <ul className="divide-y divide-slate-200">
            {data.items.map((item) => (
              <MissingRow
                key={item.key}
                bidId={bidId}
                item={item}
                busy={data.memoir_busy}
                onDone={changed}
              />
            ))}
          </ul>
        </Disclosure>
      ) : (
        drafted && (
          <p
            id="bloc-missing"
            className="text-sm font-semibold text-emerald-800"
          >
            Rien ne manque
          </p>
        )
      )}
    </div>
  );
}

function MissingRow({
  bidId,
  item,
  busy,
  onDone,
}: {
  bidId: string;
  item: MissingItem;
  busy: boolean;
  onDone: (next: MissingList) => void;
}) {
  const meta = KIND_META[item.kind];
  const company = isCompanyKind(item.kind);
  const [answering, setAnswering] = useState(!company);
  const [value, setValue] = useState("");
  const [removing, setRemoving] = useState(false);
  const [adding, setAdding] = useState(false);
  const act = useAction();
  const message = fillMessage(item);
  const inChapters = item.sections.length > 0;

  async function send(path: string, json: Record<string, string>) {
    const next = await act.run(() =>
      api<MissingList>(`/bids/${bidId}/missing/${path}`, { json }),
    );
    if (next) onDone(next);
  }

  async function afterProfile() {
    setAdding(false);
    if (inChapters) await send("fill", { key: item.key });
    if (item.documents.length > 0) await send("regenerate-documents", {});
  }

  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-brand-navy">
          <span aria-hidden="true">{meta.icon}</span> {item.text}
        </p>
        <p className="text-xs text-slate-600">
          {inChapters && (
            <a
              href={`#chapter-${item.sections[0].id}`}
              className="text-sky-800 underline"
            >
              {chaptersLabel(item.sections.length)}
            </a>
          )}
          {inChapters && item.documents.length > 0 && " · "}
          {item.documents.length > 0 &&
            `dans ${item.documents.map((d) => d.toUpperCase()).join(", ")}`}
        </p>
        {message && <p className="mt-1 text-xs text-amber-800">{message}</p>}
        {act.error && (
          <div className="mt-2">
            <Alert tone="danger">{act.error}</Alert>
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
        {busy ? (
          <span className="text-xs text-slate-500">Rédaction en cours</span>
        ) : (
          <>
            {company && meta.button && (
              <Button
                variant="secondary"
                busy={act.busy || running(item)}
                onClick={() => setAdding(true)}
              >
                {meta.button}
              </Button>
            )}
            {answering && inChapters && (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send("answer", { key: item.key, answer: value });
                }}
              >
                <Input
                  aria-label={`Réponse : ${item.text}`}
                  value={value}
                  maxLength={2000}
                  onChange={(e) => setValue(e.target.value)}
                  className="w-56"
                />
                <Button type="submit" busy={act.busy} disabled={!value.trim()}>
                  OK
                </Button>
              </form>
            )}
            {inChapters && (
              <div className="flex flex-wrap gap-3 text-xs">
                {company && !answering && (
                  <button
                    type="button"
                    className="text-sky-800 underline"
                    onClick={() => setAnswering(true)}
                  >
                    Répondre directement
                  </button>
                )}
                {removing ? (
                  <span className="flex items-center gap-2">
                    Supprimer cette phrase de{" "}
                    {chaptersLabel(item.sections.length).replace("dans ", "")} ?
                    <button
                      type="button"
                      className="font-semibold text-red-700 underline"
                      onClick={() => void send("remove", { key: item.key })}
                    >
                      Oui
                    </button>
                    <button
                      type="button"
                      className="underline"
                      onClick={() => setRemoving(false)}
                    >
                      Non
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="text-slate-700 underline"
                    onClick={() => setRemoving(true)}
                  >
                    Retirer cette phrase
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
      {adding && (
        <AddToProfileDialog
          kind={item.kind}
          markerText={item.text}
          onClose={() => setAdding(false)}
          onSaved={() => void afterProfile()}
        />
      )}
    </li>
  );
}

const GAP_KIND: Record<keyof ProfileGaps, MissingKind> = {
  staff: "staff",
  equipment: "equipment",
  references: "reference",
};

/** Before the drafting: the empty parts of the profile, each with its form. */
export function ProfileGapsCard({
  gaps,
  onAdded,
}: {
  gaps: ProfileGaps;
  onAdded: () => void;
}) {
  const [adding, setAdding] = useState<keyof ProfileGaps | null>(null);
  const messages = gapMessages(gaps);
  if (messages.length === 0) return null;
  return (
    <Card title="Avant la rédaction" color="amber">
      <ul className="space-y-2">
        {messages.map((g) => (
          <li
            key={g.key}
            className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
          >
            <span className="text-sm text-slate-700">{g.text}</span>
            <Button variant="secondary" onClick={() => setAdding(g.key)}>
              {KIND_META[GAP_KIND[g.key]].button}
            </Button>
          </li>
        ))}
      </ul>
      {adding && (
        <AddToProfileDialog
          kind={GAP_KIND[adding]}
          markerText={null}
          onClose={() => setAdding(null)}
          onSaved={() => {
            setAdding(null);
            onAdded();
          }}
        />
      )}
    </Card>
  );
}
