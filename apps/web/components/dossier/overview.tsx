"use client";

import { LevelBadge, StatTile } from "@/components/blocks";
import { Button, Card } from "@/components/ui";
import { overviewTiles, todoItems, type TabId } from "@/lib/dossier";
import { useApi } from "@/lib/hooks";
import type { Analysis, Bid } from "@/lib/types";

/**
 * The « Aperçu » tab: what the dossier is worth at a glance (four tiles), what to do before
 * answering, and where the answer stands. Every line leads to the tab that holds its detail.
 */
export function Overview({
  bid,
  onOpen,
}: {
  bid: Bid;
  onOpen: (tab: TabId, anchor?: string) => void;
}) {
  const analysis = useApi<Analysis>(
    bid.progress?.dce_ready ? `/bids/${bid.id}/analysis` : null,
    (a) => a.status === "pending" || a.status === "processing", // until it is ready
  );
  const now = new Date();

  if (!bid.progress?.dce_ready) {
    return (
      <Card title="Le DCE n'est pas encore prêt" color="blue">
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-slate-700">
            Récupérez ou déposez le dossier de consultation dans l&apos;onglet
            DCE : une fois lu et analysé, Pilao vous résume ici ce qu&apos;il
            faut retenir.
          </p>
          <Button onClick={() => onOpen("dce")}>
            Ouvrir l&apos;onglet DCE
          </Button>
        </div>
      </Card>
    );
  }

  const data = analysis.data ?? null;
  const tiles = overviewTiles(data, bid, now);
  const { items, more } = todoItems(data, bid, now);
  const p = bid.progress;
  const steps: { tab: TabId; title: string; state: string }[] = [
    {
      tab: "memoire",
      title: "Mémoire technique",
      state: p.memoir_ready ? "Rédigé" : "Pas encore rédigé",
    },
    {
      tab: "documents",
      title: "Documents (DC1, DC2…)",
      state: p.documents_ready
        ? "Au moins un document prêt"
        : "Pré-remplis depuis votre profil",
    },
    {
      tab: "export",
      title: "Export",
      state: p.exported ? "Déjà exporté" : "Word, PDF ou dossier complet",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t) => (
          <StatTile key={t.label} {...t} />
        ))}
      </div>

      {(data?.status === "error" || data?.status === "waiting_credits") && (
        <Card
          title={
            data.status === "error"
              ? "L'analyse n'a pas abouti"
              : "L'analyse attend des crédits"
          }
          color="amber"
        >
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm text-slate-700">
              {data.status === "error"
                ? "Relancez-la depuis l'onglet Analyse."
                : "Lancez-la depuis l'onglet Analyse quand vous avez des crédits."}
            </p>
            <Button onClick={() => onOpen("analyse")}>
              Ouvrir l&apos;onglet Analyse
            </Button>
          </div>
        </Card>
      )}

      {data?.status === "ready" && (
        <Card title="À faire avant de répondre" color="amber">
          {items.length === 0 ? (
            <p className="text-sm text-slate-700">
              Rien d&apos;urgent : tout est dans l&apos;onglet Analyse.
            </p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {items.map((item) => (
                <li key={`${item.level}-${item.title}`}>
                  <button
                    type="button"
                    onClick={() => onOpen(item.tab, item.anchor)}
                    className="flex min-h-12 w-full items-start gap-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-brand-navy"
                  >
                    <span className="shrink-0 pt-0.5">
                      <LevelBadge level={item.level} />
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <span className="text-sm font-semibold text-brand-navy">
                        {item.title}
                      </span>
                      {item.detail && (
                        <span className="text-sm text-slate-600">
                          {item.detail}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {more > 0 && (
            <button
              type="button"
              onClick={() => onOpen("analyse")}
              className="mt-2 text-sm font-semibold text-sky-800 underline"
            >
              + {more} autre{more > 1 ? "s" : ""} dans l&apos;onglet Analyse
            </button>
          )}
        </Card>
      )}

      <section aria-labelledby="votre-reponse" className="space-y-3">
        <h2
          id="votre-reponse"
          className="text-sm font-bold tracking-wide text-slate-600 uppercase"
        >
          Votre réponse
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {steps.map((s) => (
            <div
              key={s.tab}
              className="flex flex-col items-start gap-2 rounded-lg border border-slate-300 bg-white p-4 shadow-sm"
            >
              <span className="text-base font-bold text-brand-navy">
                {s.title}
              </span>
              <span className="text-sm text-slate-600">{s.state}</span>
              <Button
                variant="secondary"
                aria-label={`Ouvrir : ${s.title}`}
                onClick={() => onOpen(s.tab)}
              >
                Ouvrir
              </Button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
