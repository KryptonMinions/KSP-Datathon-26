import type { AskService } from "./ask-service";
import { mockAskService } from "./mock-ask-service";
import { RealAskService } from "./real-ask-service";

/**
 * Mock/real toggle (ASK_ENDPOINT_CONTRACT.md §3.4). Resolved once at module
 * load, not per-call. Default is "real" whenever NEXT_PUBLIC_API_URL is set;
 * explicitly set NEXT_PUBLIC_ASK_SERVICE=mock to force the mock path (e.g.
 * offline dev) even when an API URL is configured.
 */
function resolveAskService(): AskService {
  const mode = process.env.NEXT_PUBLIC_ASK_SERVICE;
  if (mode === "mock") return mockAskService;
  if (mode === "real") return new RealAskService();
  return process.env.NEXT_PUBLIC_API_URL ? new RealAskService() : mockAskService;
}

export const askService: AskService = resolveAskService();
