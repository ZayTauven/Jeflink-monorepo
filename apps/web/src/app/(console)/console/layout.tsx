import type { ReactNode } from "react";

import { ConsoleShell } from "@/console/shell";
import type { Badges } from "@/console/types";
import { api, requireStaff } from "@/lib/api";

const NO_BADGES: Badges = { pros_pending: 0, stale_requests: 0, contact_unhandled: 0 };

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const { me, token } = await requireStaff("/console");
  const badges = await api<Badges>("/api/console/badges/", { token });
  return (
    <ConsoleShell
      me={{ first_name: me.first_name, last_name: me.last_name, email: me.email }}
      badges={badges.ok ? badges.data : NO_BADGES}
    >
      {children}
    </ConsoleShell>
  );
}
