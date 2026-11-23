"use client";

import { type KeyboardEvent, useRef } from "react";

import { LevelBadge, StatTile } from "@/components/blocks";
import { Alert, Button } from "@/components/ui";
import type { TabId, Tile, TodoItem } from "@/lib/dossier";
import type { GuideStep, NextStep } from "@/lib/guide";

/**
 * The guided dossier (ADR-053): the key facts, the steps with where the answer stands, and the
 * one thing to do next. The detail of a step opens only when the user clicks it.
 */

export function KeyFacts({ tiles }: { tiles: Tile[] }) {
  return (
    <section
      aria-label="Chiffres clés"
      className="grid grid-cols-2 gap-3 lg:grid-cols-4"
    >
      {tiles.map((t) => (
        <StatTile key={t.label} {...t} />
      ))}
    </section>
  );
}

function Check() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}

const STATE_TEXT: Record<GuideStep["state"], string> = {
  done: "fait",
  current: "étape en cours",
  todo: "à venir",
};

/** The steps, as tabs: none is open until the user clicks one. */
export function StepBar({
  steps,
  open,
  onSelect,
}: {
  steps: GuideStep[];
  open: TabId | null;
  onSelect: (id: TabId) => void;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const done = steps.filter((s) => s.state === "done").length;
  const total = steps.length;
  // one step takes the keyboard focus: the open one, else the current one, else the first
  const focusable =
    open ?? steps.find((s) => s.state === "current")?.id ?? steps[0]?.id;

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const keys = ["ArrowRight", "ArrowLeft", "Home", "End"];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    const i = steps.findIndex(
      (s) =>
        s.id === (document.activeElement as HTMLElement | null)?.dataset.step,
    );
    const n = steps.length;
    const next =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? n - 1
          : (Math.max(i, 0) + (e.key === "ArrowRight" ? 1 : -1) + n) % n;
    refs.current[steps[next].id]?.focus();
  }

  return (
    <section
      aria-label="Avancement du dossier"
      className="rounded-lg border border-slate-300 bg-white p-4 shadow-sm"
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm text-slate-600">
        <p>
          <b className="text-slate-900">
            {done} étape{done > 1 ? "s" : ""} sur {total}
          </b>{" "}
          terminée{done > 1 ? "s" : ""}
        </p>
        <p className="text-xs">Cliquez sur une étape pour ouvrir son détail.</p>
      </div>
      <div
        className="mb-3 h-1.5 overflow-hidden rounded-full bg-slate-200"
        aria-hidden="true"
      >
        <span
          className="block h-full rounded-full bg-brand-green transition-[width] duration-500"
          style={{
            width: `${Math.max(4, (done / Math.max(total, 1)) * 100)}%`,
          }}
        />
      </div>
      <div
        role="tablist"
        aria-label="Étapes du dossier"
        onKeyDown={onKey}
        className="grid grid-cols-3 gap-1.5 sm:auto-cols-fr sm:grid-flow-col sm:grid-cols-none"
      >
        {steps.map((s, i) => {
          const selected = s.id === open;
          return (
            <button
              key={s.id}
              ref={(el) => {
                refs.current[s.id] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${s.id}`}
              data-step={s.id}
              aria-selected={selected}
              aria-controls={`panel-${s.id}`}
              aria-current={s.state === "current" ? "step" : undefined}
              aria-label={`${i + 1}. ${s.label} — ${s.note} (${STATE_TEXT[s.state]})`}
              tabIndex={s.id === focusable ? 0 : -1}
              onClick={() => onSelect(s.id)}
              className={`flex min-h-14 min-w-0 flex-col items-center gap-1 rounded-md border px-1.5 py-2 text-center focus-visible:outline-2 focus-visible:outline-brand-navy sm:flex-row sm:gap-2.5 sm:px-2.5 sm:text-left ${
                selected
                  ? "border-brand-navy bg-slate-50 ring-1 ring-brand-navy"
                  : "border-transparent hover:border-slate-300 hover:bg-slate-50"
              }`}
            >
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  s.state === "done"
                    ? "bg-emerald-600 text-white"
                    : s.state === "current"
                      ? "bg-brand-navy text-white"
                      : "border-2 border-slate-300 text-slate-500"
                }`}
                aria-hidden="true"
              >
                {s.state === "done" ? <Check /> : i + 1}
              </span>
              <span className="flex min-w-0 flex-col break-words">
                <span
                  className={`text-sm leading-tight font-semibold ${s.state === "todo" ? "text-slate-600" : "text-slate-900"}`}
                >
                  {s.label}
                </span>
                <span
                  className={`text-xs leading-tight ${s.alert ? "font-semibold text-red-700" : "text-slate-500"}`}
                >
                  {s.note}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** The one thing to do next, its button, and up to three reminders from the analysis. */
export function NextStepCard({
  next,
  openStep,
  consultation,
  reminders,
  more,
  lastStep,
  status,
  busy,
  error,
  onOpen,
  onStatus,
}: {
  next: NextStep;
  /** The step whose detail is open below: its button would only repeat it. */
  openStep: TabId | null;
  consultation: boolean;
  reminders: TodoItem[];
  more: number;
  lastStep: TabId;
  status: string;
  busy: boolean;
  error: string | null;
  onOpen: (id: TabId, anchor?: string) => void;
  onStatus: (status: "submitted" | "won" | "lost") => void;
}) {
  const over = next.id === null;
  let buttons: React.ReactNode = null;
  if (next.result)
    buttons = (
      <>
        <Button busy={busy} onClick={() => onStatus("won")}>
          Marché gagné
        </Button>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => onStatus("lost")}
        >
          Marché perdu
        </Button>
      </>
    );
  else if (next.deposit && consultation)
    buttons = (
      <>
        <Button onClick={() => onOpen("devis")}>{next.action}</Button>
        <Button
          variant="secondary"
          busy={busy}
          onClick={() => onStatus("submitted")}
        >
          J&apos;ai envoyé le devis
        </Button>
      </>
    );
  else if (next.deposit)
    buttons = (
      <>
        <Button busy={busy} onClick={() => onStatus("submitted")}>
          {next.action}
        </Button>
        <Button variant="secondary" onClick={() => onOpen("export")}>
          Revoir le dossier final
        </Button>
      </>
    );
  else if (next.action && next.id && (next.id !== openStep || next.anchor)) {
    const id = next.id;
    buttons = (
      <Button onClick={() => onOpen(id, next.anchor)}>{next.action}</Button>
    );
  }
  const shown = reminders.filter((r) => r.anchor !== next.anchor);

  return (
    <section
      aria-labelledby="prochaine-etape"
      className="space-y-3 rounded-xl border-2 border-brand-navy bg-white p-5 shadow-sm"
    >
      <p className="text-xs font-bold tracking-wide text-slate-600 uppercase">
        {over
          ? "Dossier terminé"
          : next.result
            ? "Offre déposée"
            : `Prochaine étape · ${next.index} sur ${next.total}`}
      </p>
      <h2 id="prochaine-etape" className="text-xl font-bold text-brand-navy">
        {next.title}
      </h2>
      <p className="max-w-prose text-sm text-slate-700">{next.text}</p>
      {next.id && next.id === openStep && !buttons && (
        <p className="text-sm font-semibold text-brand-navy">
          Le détail de cette étape est ouvert ci-dessous.
        </p>
      )}
      {(buttons || ["won", "lost"].includes(status)) && (
        <div className="flex flex-wrap items-center gap-2">
          {buttons}
          {["won", "lost"].includes(status) && (
            <Button
              variant="ghost"
              onClick={() => onOpen(lastStep, "resultat")}
            >
              Ajouter le montant et le rang
            </Button>
          )}
        </div>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      {!over && !next.result && shown.length > 0 && (
        <div className="border-t border-slate-200 pt-3">
          <p className="mb-1 text-sm font-semibold text-slate-800">
            À ne pas oublier
          </p>
          <ul className="divide-y divide-slate-100">
            {shown.map((item) => (
              <li key={`${item.level}-${item.title}`}>
                <button
                  type="button"
                  onClick={() => onOpen(item.tab, item.anchor)}
                  className="flex min-h-11 w-full items-start gap-3 py-2 text-left hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-brand-navy"
                >
                  <span className="shrink-0 pt-0.5">
                    <LevelBadge level={item.level} />
                  </span>
                  <span className="text-sm font-medium text-brand-navy">
                    {item.title}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {more > 0 && (
            <button
              type="button"
              onClick={() => onOpen("analyse")}
              className="mt-1 text-sm font-semibold text-sky-800 underline"
            >
              + {more} autre{more > 1 ? "s" : ""} point{more > 1 ? "s" : ""}{" "}
              dans l&apos;analyse
            </button>
          )}
        </div>
      )}
    </section>
  );
}
