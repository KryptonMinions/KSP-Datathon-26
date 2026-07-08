"use client";

import { useRoleGuard } from "@/lib/auth/use-role-guard";
import { AUDIT_LOG } from "@/lib/fixtures/admin";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

/** Immutable audit log visibility (steering-docs §7.4, demo-script Story 15). */
export default function AdminAuditPage() {
  useRoleGuard((role) => role === "admin", "/ask");

  return (
    <div className="p-4">
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Officer</TableHead>
              <TableHead>Action</TableHead>
              <TableHead className="text-right">Timestamp</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {AUDIT_LOG.map((row) => (
              <TableRow key={row.id}>
                <TableCell>{row.officer}</TableCell>
                <TableCell>{row.action}</TableCell>
                <TableCell className="text-right tabular-nums">{row.timestamp}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
