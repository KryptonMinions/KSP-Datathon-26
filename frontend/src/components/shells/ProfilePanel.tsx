"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth/auth-context";
import { useIsMobile } from "@/lib/use-media-query";
import { ROLE_LABELS } from "@/lib/types/auth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

function initialsOf(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function ProfileBody({ onSignOut }: { onSignOut: () => void }) {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Avatar className="size-12">
          <AvatarFallback>{initialsOf(user.name)}</AvatarFallback>
        </Avatar>
        <div>
          <div className="font-medium">{user.name}</div>
          <div className="text-sm text-muted-foreground">{ROLE_LABELS[user.role]}</div>
        </div>
      </div>

      <div className="space-y-3 rounded-md border border-border p-3 text-sm">
        <div>
          <div className="text-muted-foreground">Role</div>
          <div>{ROLE_LABELS[user.role]}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Unit</div>
          <div>{user.unit}</div>
        </div>
      </div>

      <Button variant="outline" className="w-full" onClick={onSignOut}>
        <LogOut className="size-4" />
        Sign out
      </Button>
    </div>
  );
}

/**
 * The single entry point to view profile details and sign out, for every
 * role in both shells — triggered by the avatar in AppHeader. There is no
 * separate Profile page/tab; this dialog/sheet is the only way to reach it.
 */
export function ProfilePanel({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const isMobile = useIsMobile();
  const { logout } = useAuth();
  const router = useRouter();

  const handleSignOut = () => {
    logout();
    onOpenChange(false);
    router.push("/");
  };

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom">
          <SheetHeader>
            <SheetTitle>Profile</SheetTitle>
          </SheetHeader>
          <div className="px-4 pb-4">
            <ProfileBody onSignOut={handleSignOut} />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Profile</DialogTitle>
        </DialogHeader>
        <ProfileBody onSignOut={handleSignOut} />
      </DialogContent>
    </Dialog>
  );
}
