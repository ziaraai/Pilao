"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { TabPanel, Tabs } from "@/components/blocks";
import { AnalysisSection } from "@/components/dossier/analysis";
import { DceSection } from "@/components/dossier/dce";
import { DocumentsSection } from "@/components/dossier/documents";
import { ExportTab } from "@/components/dossier/export";
import { MemoirSection } from "@/components/dossier/memoir";
import { Overview } from "@/components/dossier/overview";
import { ResultSection } from "@/components/dossier/result";
import { TimeSpent } from "@/components/dossier/time-spent";
import {
  Alert,
  Button,
  Field,
  Loading,
  PageTitle,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  TABS,
  type TabId,
  daysLeftText,
  defaultTab,
  tabDone,
  tabFromQuery,
} from "@/lib/dossier";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Bid } from "@/lib/types";

export default function BidPage() {
  // useSearchParams (the open tab) needs a Suspense boundary
  return (
    <Suspense fallback={<Loading />}>
      <Dossier />
    </Suspense>
  );
}

function Dossier() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const bid = useApi<Bid>(`/bids/${id}`);
  const [analysisKey, setAnalysisKey] = useState(0);
  const [memoirKey, setMemoirKey] = useState(0);
  const [anchor, setAnchor] = useState<{ id: string; n: number }>();
  // The default tab is chosen once, at the first load: the page must not jump to the overview
  // by itself when the DCE becomes ready while the user is on the DCE tab.
  const [firstTab, setFirstTab] = useState<TabId | null>(null);
  const action = useAction();
  const scrolled = useRef(0);
  if (bid.data && firstTab === null) setFirstTab(defaultTab(bid.data.progress));
  const query = params.get("onglet");
  const tab: TabId | null = bid.data
    ? query
      ? tabFromQuery(query, bid.data.progress)
      : (firstTab ?? defaultTab(bid.data.progress))
    : null;

  // A to-do line was clicked: once its tab is shown, bring the block into view and focus it.
  useEffect(() => {
    if (!anchor || anchor.n === scrolled.current) return;
    const el = document.getElementById(anchor.id);
    if (!el || el.offsetParent === null) return; // its panel is still hidden
    scrolled.current = anchor.n;
    el.scrollIntoView({ block: "start" });
    el.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  }, [anchor, tab]);

  if (bid.error && !bid.data) return <Alert tone="danger">{bid.error}</Alert>;
  if (!bid.data || !tab) return <Loading />;
  const b = bid.data;

  function select(next: string) {
    // The native history API keeps useSearchParams in sync without a navigation round trip
    window.history.replaceState(null, "", `/dossiers/${id}?onglet=${next}`);
    bid.reload(); // the marks of the tabs follow the work done in the other tabs
  }

  function open(next: TabId, target?: string) {
    if (target) setAnchor((prev) => ({ id: target, n: (prev?.n ?? 0) + 1 }));
    select(next);
  }

  return (
    <div className="space-y-6">
      <Link href="/dossiers" className="text-sm text-brand-navy underline">
        ← Tous les dossiers
      </Link>
      <PageTitle
        title={b.title}
        subtitle={`${b.buyer_name ?? "Acheteur à préciser"} · date limite : ${formatDateTime(b.deadline_at)}${b.deadline_at ? ` (${daysLeftText(b.deadline_at, new Date())})` : ""}`}
        icon="bids"
        color="blue"
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
      <Tabs
        tabs={TABS}
        active={tab}
        done={tabDone(b.progress)}
        alert={{ analyse: (b.progress?.blocking_points ?? 0) > 0 }}
        onSelect={select}
      />
      {/* Every panel stays mounted (the background tracking keeps running); the overview
          and the export are mounted when shown, so they read fresh data. */}
      <TabPanel id="apercu" active={tab === "apercu"}>
        {tab === "apercu" && (
          <>
            <Overview key={`overview-${analysisKey}`} bid={b} onOpen={open} />
            <ResultSection
              key={`${b.id}:${b.status}`}
              bid={b}
              onSaved={bid.setData}
            />
            <TimeSpent
              key={`time:${b.id}:${b.status}`}
              bid={b}
              onSaved={bid.setData}
            />
          </>
        )}
      </TabPanel>
      <TabPanel id="dce" active={tab === "dce"}>
        <DceSection
          bidId={id}
          onProcessed={() => {
            setAnalysisKey((k) => k + 1);
            bid.reload();
          }}
        />
      </TabPanel>
      <TabPanel id="analyse" active={tab === "analyse"}>
        {/* Re-mounted when a DCE version finishes processing: its analysis has just started. */}
        <AnalysisSection
          key={analysisKey}
          bidId={id}
          openAnchor={anchor}
          onReady={() => {
            bid.reload(); // the analysis pre-fills buyer and deadline
            setMemoirKey((k) => k + 1); // and unlocks the memoir outline
          }}
        />
      </TabPanel>
      <TabPanel id="memoire" active={tab === "memoire"}>
        <MemoirSection key={`memoir-${analysisKey}-${memoirKey}`} bidId={id} />
      </TabPanel>
      <TabPanel id="documents" active={tab === "documents"}>
        <DocumentsSection
          key={`documents-${analysisKey}-${memoirKey}`}
          bidId={id}
        />
      </TabPanel>
      <TabPanel id="export" active={tab === "export"}>
        {tab === "export" && <ExportTab bidId={id} onOpen={open} />}
      </TabPanel>
    </div>
  );
}
