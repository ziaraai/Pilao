"use client";

import { useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Field,
  Input,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { MEMBER_STATUS, ROLES } from "@/lib/labels";
import type { Member } from "@/lib/types";

/** The colleagues of the company (US-1.5): administrators invite and manage them. */
export function Members() {
  const { me } = useMe();
  const admin = me.role === "org_admin";
  const members = useApi<Member[]>("/organization/members");
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    role: "org_member",
  });
  const [notice, setNotice] = useState<string | null>(null);
  const inviting = useAction();
  const acting = useAction();

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    setNotice(null);
    const ok = await inviting.run(() =>
      api<Member>("/organization/members", { json: form }),
    );
    if (ok) {
      setNotice(`Invitation envoyée à ${form.email}.`);
      setForm({ email: "", full_name: "", role: "org_member" });
      members.reload();
    }
  }

  async function act(fn: () => Promise<unknown>, done: string) {
    setNotice(null);
    const ok = await acting.run(async () => {
      await fn(); // a 204 resolves to undefined: success is "no error"
      return true;
    });
    if (ok) {
      setNotice(done);
      members.reload();
    }
  }

  return (
    <Card title="Utilisateurs" color="brand">
      <div className="space-y-4">
        <ul className="divide-y divide-slate-100">
          {(members.data ?? []).map((m) => {
            const status = MEMBER_STATUS[m.status];
            return (
              <li
                key={m.id}
                aria-label={m.email}
                className="flex flex-wrap items-center gap-3 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">
                    {m.full_name || m.email}
                    {m.is_me && <span className="text-slate-500"> (vous)</span>}
                  </p>
                  <p className="text-xs text-slate-500">
                    {m.email}
                    {m.last_login_at &&
                      ` · dernière connexion le ${formatDateTime(m.last_login_at)}`}
                  </p>
                </div>
                <Badge tone={status.tone}>{status.label}</Badge>
                {admin && !m.is_me ? (
                  <Select
                    aria-label={`Rôle de ${m.email}`}
                    value={m.role}
                    disabled={acting.busy}
                    onChange={(e) =>
                      act(
                        () =>
                          api(`/organization/members/${m.id}`, {
                            method: "PATCH",
                            json: { role: e.target.value },
                          }),
                        `${m.email} est maintenant ${ROLES[e.target.value].toLowerCase()}.`,
                      )
                    }
                  >
                    {Object.entries(ROLES).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Badge>{ROLES[m.role]}</Badge>
                )}
                {admin && m.status !== "active" && (
                  <Button
                    variant="secondary"
                    disabled={acting.busy}
                    onClick={() =>
                      act(
                        () =>
                          api(`/organization/members/${m.id}/resend`, {
                            method: "POST",
                          }),
                        `Invitation renvoyée à ${m.email}.`,
                      )
                    }
                  >
                    Renvoyer l&apos;invitation
                  </Button>
                )}
                {admin && !m.is_me && (
                  <Button
                    variant="danger"
                    disabled={acting.busy}
                    onClick={() => {
                      const what =
                        m.status === "active"
                          ? `Retirer l'accès de ${m.email} ? Son travail reste dans les dossiers.`
                          : `Annuler l'invitation de ${m.email} ?`;
                      if (!window.confirm(what)) return;
                      act(
                        () =>
                          api(`/organization/members/${m.id}`, {
                            method: "DELETE",
                          }),
                        `Accès de ${m.email} retiré.`,
                      );
                    }}
                  >
                    {m.status === "active" ? "Retirer" : "Annuler"}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>

        {admin ? (
          <form
            onSubmit={onInvite}
            className="grid gap-3 rounded-md bg-slate-50 p-4 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end"
          >
            <Field label="E-mail du collaborateur" htmlFor="invite-email">
              <Input
                id="invite-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </Field>
            <Field label="Nom (facultatif)" htmlFor="invite-name">
              <Input
                id="invite-name"
                value={form.full_name}
                onChange={(e) =>
                  setForm({ ...form, full_name: e.target.value })
                }
              />
            </Field>
            <Field label="Rôle" htmlFor="invite-role">
              <Select
                id="invite-role"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {Object.entries(ROLES).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Button type="submit" busy={inviting.busy} disabled={!form.email}>
              Inviter
            </Button>
          </form>
        ) : (
          <p className="text-sm text-slate-600">
            Seul un administrateur peut inviter ou retirer des collaborateurs.
          </p>
        )}
        <p className="text-xs text-slate-500">
          Un administrateur gère aussi les utilisateurs, l&apos;export et la
          suppression des données. Un collaborateur prépare les dossiers :
          annonces, analyses, mémoires, documents et exports.
        </p>
        {notice && <Alert tone="ok">{notice}</Alert>}
        {(inviting.error || acting.error || members.error) && (
          <Alert tone="danger">
            {inviting.error || acting.error || members.error}
          </Alert>
        )}
      </div>
    </Card>
  );
}
