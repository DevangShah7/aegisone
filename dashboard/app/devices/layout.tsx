"use client";

import { DashboardShell } from "@/app/dashboard-shell";

export default function DevicesLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
