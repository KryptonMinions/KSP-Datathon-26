"use client";

import { useRoleGuard } from "@/lib/auth/use-role-guard";
import { USERS } from "@/lib/fixtures/admin";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

/** Presentation UI over users/roles — actual access control lives at the DB view layer (steering-docs §7.4). */
export default function AdminUsersPage() {
  useRoleGuard((role) => role === "admin", "/ask");

  return (
    <div className="p-4">
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Unit</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {USERS.map((u) => (
              <TableRow key={u.id}>
                <TableCell>{u.name}</TableCell>
                <TableCell>{u.role}</TableCell>
                <TableCell>{u.unit}</TableCell>
                <TableCell>
                  <Badge variant={u.status === "Active" ? "secondary" : "destructive"}>
                    {u.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
