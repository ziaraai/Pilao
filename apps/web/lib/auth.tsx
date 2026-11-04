"use client";

import { createContext, useContext } from "react";

import type { Me } from "./types";

export const AuthContext = createContext<{
  me: Me;
  refresh: () => void;
} | null>(null);

export function useMe() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useMe must be used inside the (app) layout");
  return ctx;
}
