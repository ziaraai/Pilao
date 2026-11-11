"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect } from "react";

import { adminSignInPath } from "./admin";
import { ApiError } from "./api";
import { useAction, useApi } from "./hooks";
import type { AdminMe } from "./types";

export const AdminAuthContext = createContext<{ me: AdminMe } | null>(null);

/** The signed-in super admin. */
export function useAdmin() {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdmin must be used inside the admin shell");
  return ctx;
}

/**
 * ``useApi`` for the screens of the administration. A 401 means the session ended (12 hours,
 * account closed or reset from the server): back to the sign-in page, then to this screen.
 */
export function useAdminApi<T>(path: string | null) {
  const router = useRouter();
  const result = useApi<T>(path);
  const expired = result.status === 401;
  useEffect(() => {
    if (expired)
      router.replace(
        adminSignInPath(window.location.pathname, window.location.search),
      );
  }, [expired, router]);
  return result;
}

/**
 * ``useAction`` for the actions of the administration. A 401 means the session ended (or was
 * closed after five wrong codes): back to the sign-in page, then to this screen.
 */
export function useAdminAction() {
  const router = useRouter();
  const action = useAction();
  async function run<R>(fn: () => Promise<R>): Promise<R | undefined> {
    return action.run(async () => {
      try {
        return await fn();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401)
          router.replace(
            adminSignInPath(window.location.pathname, window.location.search),
          );
        throw err;
      }
    });
  }
  return { ...action, run };
}
