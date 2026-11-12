"use client";

import { Button, type ButtonProps } from "@/components/ui";
import { useMe } from "@/lib/auth";
import { missing, withPrice } from "@/lib/credits";

/**
 * A button that costs credits (lot 4): its price is shown, it is greyed out with the reason
 * when the credits are short, and the balance is read again once it has run. The server
 * decides in the end (402 `credits_exhausted`).
 */
export function PaidButton({
  action,
  label,
  free = false,
  onClick,
  disabled,
  ...rest
}: Omit<ButtonProps, "children" | "onClick"> & {
  action: string;
  label: string;
  /** A relaunch that costs nothing (a chapter in error). */
  free?: boolean;
  onClick: () => Promise<unknown>;
}) {
  const { me, refresh } = useMe();
  const price = free ? 0 : (me.credits?.prices[action] ?? 0);
  const short = me.credits
    ? missing(price, me.credits.total, me.support_email)
    : null;
  return (
    <span className="inline-flex flex-col gap-1">
      <Button
        {...rest}
        disabled={disabled || short !== null}
        onClick={async () => {
          await onClick();
          refresh(); // the balance shown everywhere follows
        }}
      >
        {withPrice(label, price)}
      </Button>
      {short && (
        <span role="note" className="max-w-xs text-xs text-amber-800">
          {short}
        </span>
      )}
    </span>
  );
}
