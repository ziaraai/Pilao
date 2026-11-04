"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AnalysisSection } from "@/components/dossier/analysis";
import { DceSection } from "@/components/dossier/dce";
import { MemoirSection } from "@/components/dossier/memoir";
import {
  Alert,
  Button,
  Field,
  Loading,
  PageTitle,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Bid } from "@/lib/types";

export default function BidPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const bid = useApi<Bid>(`/bids/${id}`);
  const [analysisKey, setAnalysisKey] = useState(0);
  const [memoirKey, setMemoirKey] = useState(0);
  const action = useAction();

  if (bid.error && !bid.data) return <Alert tone="danger">{bid.error}</Alert>;
  if (!bid.data) return <Loading />;
  const b = bid.data;

  return (
    <div className="space-y-6">
      <Link href="/dossiers" className="text-sm text-brand-navy underline">
        ← Tous les dossiers
      </Link>
      <PageTitle
        title={b.title}
        subtitle={`${b.buyer_name ?? "Acheteur à préciser"} · date limite : ${formatDateTime(b.deadline_at)}`}
        actions={
          <div className="flex items-end gap-2">
            <Field label="Statut" htmlFor="bid-status">
              <Select
                id="bid-status"
                value={b.status}
                disabled={action.busy}
                onChange={async (e) => {
                  const updated = await action.run(() =>
                    api<Bid>(`/bids/${id}`, {
                      method: "PATCH",
                      json: { status: e.target.value },
                    }),
                  );
                  if (updated) bid.setData(updated);
                }}
              >
                {Object.entries(BID_STATUS).map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              variant="danger"
              onClick={async () => {
                if (
                  !window.confirm(
                    "Supprimer ce dossier, son DCE et son analyse ?",
                  )
                )
                  return;
                const deleted = await action.run(async () => {
                  await api(`/bids/${id}`, { method: "DELETE" });
                  return true;
                });
                if (deleted) router.push("/dossiers");
              }}
            >
              Supprimer
            </Button>
          </div>
        }
      />
      {action.error && <Alert tone="danger">{action.error}</Alert>}
      <DceSection
        bidId={id}
        onProcessed={() => {
          setAnalysisKey((k) => k + 1);
          bid.reload();
        }}
      />
      {/* Re-mounted when a DCE version finishes processing: its analysis has just started. */}
      <AnalysisSection
        key={analysisKey}
        bidId={id}
        onReady={() => {
          bid.reload(); // the analysis pre-fills buyer and deadline
          setMemoirKey((k) => k + 1); // and unlocks the memoir outline
        }}
      />
      <MemoirSection key={`memoir-${analysisKey}-${memoirKey}`} bidId={id} />
    </div>
  );
}
