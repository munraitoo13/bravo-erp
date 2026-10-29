import React from "react";
import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function DashboardGroupLayout({
  children,
}: {
  readonly children: React.ReactNode;
}): React.JSX.Element {
  return <DashboardShell>{children}</DashboardShell>;
}
