"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

import { Alert, Button, Field, Input, Textarea } from "@/components/ui";
import { useAdminAction } from "@/lib/admin-auth";

export type DialogInput = { name: string; code: string; reason: string };

/**
 * A confirmation window for the actions of the administration. A native modal ``<dialog>``:
 * the focus stays inside, Échap closes it. Asks, when needed, for the company's name typed
 * again, the authenticator code, or a reason. Closes itself once ``onConfirm`` succeeded.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  danger = false,
  needsName,
  needsCode = false,
  needsReason = false,
  onConfirm,
  onClose,
}: {
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  /** The company's name, to be typed again. */
  needsName?: string;
  needsCode?: boolean;
  needsReason?: boolean;
  onConfirm: (input: DialogInput) => Promise<unknown>;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const action = useAdminAction();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  const ready =
    (!needsName || name.trim().length > 0) &&
    (!needsCode || code.trim().length > 0) &&
    (!needsReason || reason.trim().length > 0);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const done = await action.run(async () => {
      await onConfirm({ name, code, reason });
      return true;
    });
    if (done) onClose();
  }

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      className="w-[min(32rem,calc(100vw-2rem))] rounded-lg p-0 shadow-xl backdrop:bg-slate-900/50"
    >
      <form onSubmit={onSubmit} className="space-y-4 p-5" noValidate>
        <h2 className="text-lg font-bold text-brand-navy">{title}</h2>
        {children && (
          <div className="space-y-2 text-sm text-slate-700">{children}</div>
        )}
        {needsReason && (
          <Field
            label="Raison"
            htmlFor="dialog-reason"
            hint="Visible seulement dans l'administration et le journal."
          >
            <Textarea
              id="dialog-reason"
              rows={3}
              maxLength={500}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </Field>
        )}
        {needsName && (
          <Field
            label={`Recopiez le nom de l'entreprise : ${needsName}`}
            htmlFor="dialog-name"
          >
            <Input
              id="dialog-name"
              autoComplete="off"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </Field>
        )}
        {needsCode && (
          <Field
            label="Code de l'application d'authentification"
            htmlFor="dialog-code"
            hint="Les 6 chiffres affichés sur votre téléphone, ou un code de secours."
          >
            <Input
              id="dialog-code"
              autoComplete="one-time-code"
              autoCapitalize="none"
              spellCheck={false}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
          </Field>
        )}
        {action.error && <Alert tone="danger">{action.error}</Alert>}
        <div className="flex flex-wrap justify-end gap-3">
          <Button type="button" variant="ghost" onClick={onClose}>
            Annuler
          </Button>
          <Button
            type="submit"
            variant={danger ? "danger" : "primary"}
            busy={action.busy}
            disabled={!ready}
          >
            {confirmLabel}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
