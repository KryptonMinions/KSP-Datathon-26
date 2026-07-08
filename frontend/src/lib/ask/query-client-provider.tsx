"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider as TanstackProvider } from "@tanstack/react-query";

export function QueryClientProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return <TanstackProvider client={client}>{children}</TanstackProvider>;
}
