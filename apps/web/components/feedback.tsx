"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Field, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";

const KINDS = [
  { value: "idea", label: "Une idée" },
  { value: "problem", label: "Un problème" },
  { value: "question", label: "Une question" },
];

/** P4-02: tell the team something in two clicks, from any page of the application.
 * In the sidebar it sits at the bottom, so the form opens above it. */
export function FeedbackButton({ className = "" }: { className?: string }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState("idea");
  const [message, setMessage] = useState("");
  const [thanks, setThanks] = useState(false);
  const send = useAction();
  const bidId = /^\/dossiers\/([0-9a-f-]{36})/.exec(pathname)?.[1] ?? null;

  return (
    <div className="relative">
      <Button
        variant="secondary"
        className={className}
        aria-expanded={open}
        onClick={() => {
          setOpen((o) => !o);
          setThanks(false);
        }}
      >
        Votre avis
      </Button>
      {open && (
        <div
          role="dialog"
          aria-label="Votre avis"
          className="absolute bottom-full left-0 z-40 mb-2 w-[min(20rem,calc(100vw-2rem))] rounded-lg bg-white p-4 shadow-lg ring-1 ring-slate-200"
        >
          {thanks ? (
            <div className="space-y-3">
              <Alert tone="ok">
                Merci ! L&apos;équipe Pilao lit chaque message.
              </Alert>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Fermer
              </Button>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={async (e) => {
                e.preventDefault();
                const ok = await send.run(() =>
                  api("/feedback", {
                    json: { kind, message, page: pathname, bid_id: bidId },
                  }),
                );
                if (ok) {
                  setThanks(true);
                  setMessage("");
                }
              }}
            >
              <Field label="C'est…" htmlFor="feedback-kind">
                <Select
                  id="feedback-kind"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  {KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Votre message"
                htmlFor="feedback-message"
                hint="La page où vous êtes est jointe au message."
              >
                <Textarea
                  id="feedback-message"
                  rows={4}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  required
                  maxLength={4000}
                />
              </Field>
              {send.error && <Alert tone="danger">{send.error}</Alert>}
              <Button type="submit" busy={send.busy} disabled={!message.trim()}>
                Envoyer
              </Button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
