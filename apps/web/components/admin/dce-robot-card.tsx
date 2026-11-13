"use client";

import { Button, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { originLabel, robotSummary } from "@/lib/settings";
import type { AdminDceRobot } from "@/lib/types";

type Run = (fn: () => Promise<unknown>) => Promise<boolean>;

/** The DCE robot's switch (spec « Récupération des DCE », § 4.5): off, every company gets the
 * guided retrieval and the daily watch stops. The safety valve if a platform complains. */
export function DceRobotCard({
  robot,
  run,
}: {
  robot: AdminDceRobot;
  run: Run;
}) {
  return (
    <Card title="Robot de récupération des DCE" color="sky">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-brand-navy">
            {robotSummary(robot)}{" "}
            <span className="text-xs font-normal text-slate-500">
              ({originLabel(robot.origin)})
            </span>
          </p>
          <p className="text-xs text-slate-600">
            PLACE et plateformes Atexo. Coupé, chaque client garde
            l&apos;aide-mémoire et le dépôt du ZIP.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={robot.enabled}
              aria-label="Robot de récupération des DCE actif"
              onChange={(e) =>
                run(() =>
                  api("/admin/settings/dce-robot", {
                    method: "PUT",
                    json: { enabled: e.target.checked },
                  }),
                )
              }
            />
            Actif
          </label>
          {robot.origin === "admin" && (
            <Button
              variant="ghost"
              className="px-2 py-1 text-xs"
              onClick={() =>
                run(() =>
                  api("/admin/settings/dce-robot", { method: "DELETE" }),
                )
              }
            >
              Revenir à la valeur du serveur
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
