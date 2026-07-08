"use client";

import { useState } from "react";
import { Shield, Users, Search, Settings } from "lucide-react";
import { KspEmblem } from "@/components/shared/KspEmblem";
import { RoleTile } from "@/components/auth/RoleTile";
import { CredentialDialog } from "@/components/auth/CredentialDialog";
import type { Role } from "@/lib/types/auth";

// Role-first login is a demo convenience only (steering-docs §4). In a real
// deployment, role is derived from credentials — never pre-selected by the
// user. This screen exists purely to let the 3-minute demo hop personas
// quickly; a production build would start at the credential step.
const ROLE_TILES: { role: Role; label: string; description: string; icon: typeof Shield }[] = [
  { role: "io", label: "Investigating Officer", description: "Field lookups on the go", icon: Shield },
  { role: "supervisor", label: "Supervisor", description: "Unit oversight & review packs", icon: Users },
  { role: "analyst", label: "Crime Analyst", description: "Pattern & network analysis", icon: Search },
  { role: "admin", label: "Admin", description: "Audit & user management", icon: Settings },
];

export default function RoleSelectScreen() {
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-10 bg-muted/30 p-6">
      <KspEmblem />
      <div className="text-center">
        <h1 className="text-lg font-semibold">Demo mode — select a persona</h1>
        <p className="text-sm text-muted-foreground">
          Karnataka State Police · Intelligent Conversational AI &amp; Crime Analytics Platform
        </p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {ROLE_TILES.map((tile) => (
          <RoleTile
            key={tile.role}
            label={tile.label}
            description={tile.description}
            icon={tile.icon}
            onClick={() => setSelectedRole(tile.role)}
          />
        ))}
      </div>
      <CredentialDialog
        role={selectedRole}
        onOpenChange={(open) => !open && setSelectedRole(null)}
      />
    </div>
  );
}
