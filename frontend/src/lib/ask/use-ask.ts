"use client";

import { useMutation } from "@tanstack/react-query";
import { mockAskService } from "./mock-ask-service";
import type { AskInput } from "./ask-service";

export function useAsk() {
  return useMutation({
    mutationFn: (input: AskInput) => mockAskService.ask(input),
  });
}
