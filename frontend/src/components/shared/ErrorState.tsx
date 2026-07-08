import { AlertTriangle } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";

/**
 * Distinct from the `no_answer` block: an error means something broke
 * (a real service failure). A no-answer means the system correctly
 * declined to guess. Never conflate the two (steering-docs §6).
 */
export function ErrorState({ message }: { message?: string }) {
  return (
    <Alert variant="destructive">
      <AlertTriangle className="size-4" />
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription>
        {message ?? "The request could not be completed. Please try again."}
      </AlertDescription>
    </Alert>
  );
}
