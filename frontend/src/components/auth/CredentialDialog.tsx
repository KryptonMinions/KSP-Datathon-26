"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/auth-context";
import { AuthApiError } from "@/lib/auth/auth-api";
import { ROLE_LABELS, type Role } from "@/lib/types/auth";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function CredentialDialog({
  role,
  onOpenChange,
}: {
  role: Role | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!role || !username.trim() || !password.trim() || submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      // The tapped tile (`role`) only picked which dialog to show. Routing
      // below uses the server-verified role from the response, never this
      // value — per the Role Authority Rule, a client-picked role is never
      // an authorization input.
      const authUser = await login({ username, password });
      router.push(authUser.role === "investigating_officer" ? "/ask" : "/dashboard");
    } catch (err) {
      setError(err instanceof AuthApiError ? err.message : "Sign-in failed. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={role !== null}
      onOpenChange={(open) => {
        if (!open) {
          setUsername("");
          setPassword("");
          setError(null);
        }
        onOpenChange(open);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{role ? ROLE_LABELS[role] : ""} sign-in</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!username.trim() || !password.trim() || submitting}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
