"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { Alert, Loading } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<{ ok: boolean; message: string } | null>(
    null,
  );
  const sent = useRef(false); // the token is single-use: never post it twice (React strict mode)

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    api<{ message: string }>("/auth/verify-email", { json: { token } })
      .then((r) => setState({ ok: true, message: r.message }))
      .catch((err) => setState({ ok: false, message: errorMessage(err) }));
  }, [token]);

  if (!token)
    return (
      <Alert tone="danger">
        Lien incomplet : ouvrez le lien reçu par e-mail.
      </Alert>
    );
  if (!state) return <Loading />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-brand-navy">
        Confirmation de l&apos;adresse e-mail
      </h1>
      <Alert tone={state.ok ? "ok" : "danger"}>{state.message}</Alert>
      <Link
        href="/connexion"
        className="text-sm font-semibold text-brand-navy underline"
      >
        Aller à la connexion
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <Verify />
    </Suspense>
  );
}
