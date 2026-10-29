"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  Calculator,
  ClipboardList,
  ExternalLink,
  FileSpreadsheet,
  HardHat,
  LayoutDashboard,
  LogOut,
  Package,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { ROLE_LABELS_PT_BR } from "@/lib/formatters";

interface NavItem {
  readonly href: string;
  readonly label: string;
  readonly icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", label: "Painel Executivo", icon: LayoutDashboard },
  { href: "/sizing", label: "Dimensionamento CFTV", icon: Calculator },
  { href: "/quotes", label: "Propostas & Orçamentos", icon: FileSpreadsheet },
  { href: "/work-orders", label: "Ordens de Serviço", icon: ClipboardList },
  { href: "/vault", label: "Cofre de S/N & Garantias", icon: ShieldCheck },
  { href: "/catalog", label: "Catálogo & Estoque", icon: Package },
];

export function DashboardShell({
  children,
}: {
  readonly children: React.ReactNode;
}): React.JSX.Element {
  const pathname = usePathname();
  const {
    user,
    organization,
    isLoading,
    isSwitchingDemo,
    loginWithDemoPersona,
    resetDemoData,
    logout,
  } = useAuth();

  const autoBootTriggered = useRef(false);

  // Zero-friction Recruiter Demo auto-session if someone navigates directly to a dashboard route unauthenticated
  useEffect(() => {
    if (!isLoading && !user && !isSwitchingDemo && !autoBootTriggered.current) {
      autoBootTriggered.current = true;
      void loginWithDemoPersona("OWNER", { redirect: false });
    }
  }, [isLoading, user, isSwitchingDemo, loginWithDemoPersona]);

  const currentRole = user?.role ?? "OWNER";

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* Top 1-Click Recruiter Demo Persona Switcher Banner */}
      <div className="bg-slate-950 text-slate-100 border-b border-slate-800 px-3 sm:px-6 py-2">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs">
            <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-400/30 gap-1">
              <Sparkles className="size-3" />
              Modo Recruiter Demo
            </Badge>
            <span className="hidden md:inline text-slate-400">
              Alterne instantaneamente entre as personas para testar RBAC,
              aprovação pública e execução de O.S.:
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              type="button"
              size="xs"
              variant={currentRole === "OWNER" ? "default" : "outline"}
              disabled={isSwitchingDemo}
              onClick={() =>
                void loginWithDemoPersona("OWNER", { redirect: false })
              }
              className={
                currentRole === "OWNER"
                  ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold"
                  : "border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
              }
            >
              <Building2 className="size-3 mr-1" />
              Proprietário (Owner)
            </Button>

            <Button
              type="button"
              size="xs"
              variant={currentRole === "TECHNICIAN" ? "default" : "outline"}
              disabled={isSwitchingDemo}
              onClick={() =>
                void loginWithDemoPersona("TECHNICIAN", { redirect: false })
              }
              className={
                currentRole === "TECHNICIAN"
                  ? "bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold"
                  : "border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
              }
            >
              <HardHat className="size-3 mr-1" />
              Técnico de Campo
            </Button>

            <Button
              type="button"
              size="xs"
              variant="outline"
              disabled={isSwitchingDemo}
              onClick={() =>
                void loginWithDemoPersona("PUBLIC_CLIENT", { redirect: true })
              }
              className="border-amber-500/50 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
            >
              <ExternalLink className="size-3 mr-1" />
              Link Público do Cliente
            </Button>

            <Button
              type="button"
              size="xs"
              variant="outline"
              disabled={isSwitchingDemo}
              onClick={() => void resetDemoData()}
              className="border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
            >
              <RefreshCw
                className={`size-3 mr-1 ${isSwitchingDemo ? "animate-spin" : ""}`}
              />
              Restaurar Demo
            </Button>
          </div>
        </div>
      </div>

      {/* Main Navigation Header */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="flex items-center gap-2.5">
              <div className="size-8 rounded-lg bg-emerald-600 text-white flex items-center justify-center font-bold shadow-xs">
                <ShieldCheck className="size-5" />
              </div>
              <div className="leading-tight">
                <span className="font-bold text-sm tracking-tight text-slate-900 block">
                  BRAVO ERP
                </span>
                <span className="text-[11px] text-slate-500 block">
                  {organization?.name ?? "Bravo Segurança Eletrônica Ltda"}
                </span>
              </div>
            </Link>

            <nav className="hidden lg:flex items-center gap-1">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive =
                  pathname === item.href ||
                  pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      isActive
                        ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                    }`}
                  >
                    <Icon className="size-3.5" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-2.5">
            {user && (
              <div className="hidden sm:flex items-center gap-2 text-right">
                <div>
                  <p className="text-xs font-semibold text-slate-900 leading-none">
                    {user.full_name}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {ROLE_LABELS_PT_BR[user.role]}
                  </p>
                </div>
                <Badge
                  variant="outline"
                  className={
                    user.role === "OWNER"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                      : "bg-sky-50 text-sky-700 border-sky-300"
                  }
                >
                  {user.role === "OWNER" ? "OWNER (Com Margem)" : "TÉCNICO (Sem Custo)"}
                </Badge>
              </div>
            )}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={logout}
              title="Encerrar sessão"
              className="text-slate-600 hover:text-slate-900"
            >
              <LogOut className="size-4 mr-1" />
              <span className="hidden sm:inline">Sair</span>
            </Button>
          </div>
        </div>

        {/* Mobile / Tablet Horizontal Scroll Nav */}
        <div className="lg:hidden border-t border-slate-100 px-3 py-1.5 flex items-center gap-1 overflow-x-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap ${
                  isActive
                    ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <Icon className="size-3.5" />
                {item.label}
              </Link>
            );
          })}
        </div>
      </header>

      {/* Page Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 py-6">
        {children}
      </main>
    </div>
  );
}
