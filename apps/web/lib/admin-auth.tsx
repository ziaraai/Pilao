"use client";

import { createContext, useContext } from "react";

import type { AdminMe } from "./types";

export const AdminAuthContext = createContext<{ me: AdminMe } | null>(null);

/** The signed-in super admin. */
export function useAdmin() {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdmin must be used inside the admin shell");
  return ctx;
}
