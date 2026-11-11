"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/admin/dialogs";
import { CELL, HEAD, Pill } from "@/components/admin/ui";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  Select,
  tableHead,
  tableRow,
} from "@/components/ui";
import { type UserAction, userActions } from "@/lib/admin";
import { useAdminAction } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { formatDate, formatDateTimeShort } from "@/lib/format";
import { ROLES, label } from "@/lib/labels";
import type { AdminOrgUser } from "@/lib/types";

function StatePill({ u }: { u: AdminOrgUser }) {
  if (u.status === "active") return <Pill tone="ok">Actif</Pill>;
  if (u.status === "unverified")
    return <Pill tone="warning">E-mail non confirmé</Pill>;
  if (u.status === "invited")
    return (
      <Pill tone="neutral">
        Invitation envoyée
        {u.invited_at ? ` le ${formatDate(u.invited_at)}` : ""}
      </Pill>
    );
  return <Pill tone="danger">Invitation expirée</Pill>;
}

/** What each button sends, and what to say once it is done. */
const SENDS: Partial<
  Record<UserAction, { label: string; path: string; done: string }>
> = {
  invitation: {
    label: "Renvoyer l'invitation",
    path: "invitation",
    done: "Invitation renvoyée",
  },
  verification: {
    label: "Renvoyer la confirmation",
    path: "verification",
    done: "E-mail de confirmation renvoyé",
  },
  "password-reset": {
    label: "Lien nouveau mot de passe",
    path: "password-reset",
    done: "Lien de mot de passe envoyé",
  },
};

/** Lot 2, spec §2.4: a company's users, and what Pilao can do for them. */
export function OrgUsers({
  orgId,
  orgName,
  users,
  suspended,
  onChanged,
}: {
  orgId: string;
  orgName: string;
  users: AdminOrgUser[];
  suspended: boolean;
  onChanged: () => void;
}) {
  const base = `/admin/organizations/${orgId}/users`;
  const act = useAdminAction();
  const [done, setDone] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("org_member");
  const [removing, setRemoving] = useState<AdminOrgUser | null>(null);

  async function run(message: string, fn: () => Promise<unknown>) {
    setDone(null);
    if (await act.run(async () => (await fn(), true))) {
      setDone(message);
      onChanged();
    }
  }

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    await run(`Invitation envoyée à ${email}.`, () =>
      api(base, {
        json: { email, full_name: fullName || null, role },
      }),
    );
    setAdding(false);
    setEmail("");
    setFullName("");
  }

  return (
    <Card
      title="Utilisateurs"
      color="blue"
      flush
      actions={
        <Button
          variant="secondary"
          onClick={() => setAdding((a) => !a)}
          disabled={suspended}
          aria-expanded={adding}
        >
          Ajouter un utilisateur
        </Button>
      }
    >
      {(done || act.error) && (
        <div className="px-5 pt-4">
          {act.error ? (
            <Alert tone="danger">{act.error}</Alert>
          ) : (
            <Alert tone="ok">{done}</Alert>
          )}
        </div>
      )}
      {adding && (
        <form
          onSubmit={onInvite}
          className="grid gap-3 border-b border-slate-200 px-5 py-4 sm:grid-cols-[1fr_1fr_12rem_auto] sm:items-end"
          noValidate
        >
          <Field label="E-mail" htmlFor="invite-email">
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field label="Nom" htmlFor="invite-name">
            <Input
              id="invite-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </Field>
          <Field label="Rôle" htmlFor="invite-role">
            <Select
              id="invite-role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {Object.entries(ROLES).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" busy={act.busy} disabled={!email.trim()}>
            Inviter
          </Button>
        </form>
      )}
      {users.length === 0 ? (
        <p className="px-5 py-4 text-sm text-slate-600">Aucun utilisateur.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className={tableHead}>
                <th className={HEAD}>Utilisateur</th>
                <th className={HEAD}>Rôle</th>
                <th className={HEAD}>État</th>
                <th className={HEAD}>Dernière connexion</th>
                <th className={HEAD}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={tableRow}>
                  <td className={CELL}>
                    <span className="block font-semibold">
                      {u.full_name ?? "—"}
                    </span>
                    <span className="block text-slate-600">{u.email}</span>
                  </td>
                  <td className={CELL}>{label(ROLES, u.role)}</td>
                  <td className={CELL}>
                    <StatePill u={u} />
                  </td>
                  <td className={`${CELL} whitespace-nowrap`}>
                    {u.last_login_at
                      ? formatDateTimeShort(u.last_login_at)
                      : "Jamais"}
                  </td>
                  <td className={CELL}>
                    <div className="flex min-w-[16rem] flex-wrap gap-2">
                      {userActions(u, suspended).map((a) => {
                        const send = SENDS[a];
                        if (send)
                          return (
                            <Button
                              key={a}
                              variant="secondary"
                              className="!px-2.5 !py-1 text-xs"
                              onClick={() =>
                                run(`${send.done} à ${u.email}.`, () =>
                                  api(`${base}/${u.id}/${send.path}`, {
                                    method: "POST",
                                  }),
                                )
                              }
                            >
                              {send.label}
                            </Button>
                          );
                        if (a === "role") {
                          const next =
                            u.role === "org_admin" ? "org_member" : "org_admin";
                          return (
                            <Button
                              key={a}
                              variant="secondary"
                              className="!px-2.5 !py-1 text-xs"
                              onClick={() =>
                                run(
                                  `${u.email} est maintenant ${label(ROLES, next).toLowerCase()}.`,
                                  () =>
                                    api(`${base}/${u.id}`, {
                                      method: "PATCH",
                                      json: { role: next },
                                    }),
                                )
                              }
                            >
                              Passer {label(ROLES, next).toLowerCase()}
                            </Button>
                          );
                        }
                        if (a === "logout")
                          return (
                            <Button
                              key={a}
                              variant="secondary"
                              className="!px-2.5 !py-1 text-xs"
                              onClick={() =>
                                run(`${u.email} est déconnecté partout.`, () =>
                                  api(`${base}/${u.id}/logout`, {
                                    method: "POST",
                                  }),
                                )
                              }
                            >
                              Déconnecter partout
                            </Button>
                          );
                        return (
                          <Button
                            key={a}
                            variant="danger"
                            className="!px-2.5 !py-1 text-xs"
                            onClick={() => setRemoving(u)}
                          >
                            Retirer
                          </Button>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {removing && (
        <ConfirmDialog
          title={`Retirer ${removing.email}`}
          confirmLabel="Retirer l'utilisateur"
          danger
          needsCode
          onConfirm={async ({ code }) => {
            await api(`${base}/${removing.id}/remove`, { json: { code } });
            setDone(`${removing.email} a été retiré de ${orgName}.`);
            onChanged();
          }}
          onClose={() => setRemoving(null)}
        >
          <p>
            Son compte est supprimé et ses sessions fermées. Son travail reste
            dans l&apos;espace de l&apos;entreprise, sans auteur.
          </p>
        </ConfirmDialog>
      )}
    </Card>
  );
}
