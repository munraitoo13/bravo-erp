"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Calculator,
  ClipboardList,
  DollarSign,
  ExternalLink,
  FileSpreadsheet,
  Lock,
  PlusCircle,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { quotesApi, workOrdersApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  QUOTE_STATUS_LABELS_PT_BR,
  WORK_ORDER_STATUS_LABELS_PT_BR,
  formatCentsToBrl,
  formatDatePtBr,
} from "@/lib/formatters";
import { isQuoteOwnerResponse } from "@/types/api";

export default function DashboardPage(): React.JSX.Element {
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const quotesQuery = useQuery({
    queryKey: ["quotes"],
    queryFn: () => quotesApi.list(),
    enabled: Boolean(user),
  });

  const workOrdersQuery = useQuery({
    queryKey: ["work-orders"],
    queryFn: () => workOrdersApi.list(),
    enabled: Boolean(user),
  });

  const warrantiesQuery = useQuery({
    queryKey: ["warranties-expiring"],
    queryFn: () => workOrdersApi.listExpiringWarranties(),
    enabled: Boolean(user) && isOwner,
  });

  const quotes = quotesQuery.data ?? [];
  const workOrders = workOrdersQuery.data ?? [];
  const expiringWarranties = warrantiesQuery.data ?? [];

  const totalQuotedCents = quotes.reduce(
    (acc, q) => acc + q.total_sale_cents,
    0
  );
  const approvedQuotes = quotes.filter((q) =>
    ["APPROVED", "IN_PROGRESS", "COMPLETED"].includes(q.status)
  );
  const approvedRevenueCents = approvedQuotes.reduce(
    (acc, q) => acc + q.total_sale_cents,
    0
  );

  const ownerQuotes = quotes.filter(isQuoteOwnerResponse);
  const totalOwnerSaleCents = ownerQuotes.reduce(
    (acc, q) => acc + q.total_sale_cents,
    0
  );
  const totalOwnerCostCents = ownerQuotes.reduce(
    (acc, q) => acc + q.total_cost_cents,
    0
  );
  const weightedMarginPercent =
    totalOwnerSaleCents > 0
      ? ((totalOwnerSaleCents - totalOwnerCostCents) / totalOwnerSaleCents) *
        100
      : 0;

  const activeWorkOrdersCount = workOrders.filter(
    (wo) => wo.status !== "COMPLETED"
  ).length;

  return (
    <div className="space-y-6">
      {/* Page Header & Quick Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Painel Executivo & Operacional
          </h1>
          <p className="text-sm text-slate-600">
            Acompanhamento em tempo real de propostas CFTV, ordens de serviço em
            campo e radar preventivo de garantias.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link href="/sizing">
            <Button variant="outline" className="gap-1.5">
              <Calculator className="size-4 text-emerald-600" />
              Calculadora CFTV
            </Button>
          </Link>
          <Link href="/quotes/new">
            <Button className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5">
              <PlusCircle className="size-4" />
              Nova Proposta Comercial
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs">
              <span>Volume Total Orçado</span>
              <FileSpreadsheet className="size-4 text-slate-400" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900">
              {quotesQuery.isLoading ? (
                <Skeleton className="h-8 w-32" />
              ) : (
                formatCentsToBrl(totalQuotedCents)
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-500">
            {quotes.length} proposta(s) comercial(is) registrada(s)
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs">
              <span>Receita Aprovada / Executada</span>
              <DollarSign className="size-4 text-emerald-600" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-emerald-700">
              {quotesQuery.isLoading ? (
                <Skeleton className="h-8 w-32" />
              ) : (
                formatCentsToBrl(approvedRevenueCents)
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-500">
            {approvedQuotes.length} projeto(s) com estoque reservado/concluído
          </CardContent>
        </Card>

        <Card className={isOwner ? "border-emerald-200 bg-emerald-50/30" : "bg-slate-100/80"}>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs">
              <span>Margem Bruta & Custo (RBAC)</span>
              {isOwner ? (
                <TrendingUp className="size-4 text-emerald-600" />
              ) : (
                <Lock className="size-4 text-slate-500" />
              )}
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900">
              {isOwner ? (
                quotesQuery.isLoading ? (
                  <Skeleton className="h-8 w-24" />
                ) : (
                  `${weightedMarginPercent.toFixed(2)}%`
                )
              ) : (
                <span className="text-sm font-semibold text-slate-500">
                  Restrito ao Proprietário
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-600">
            {isOwner ? (
              <span>
                Custo total: <strong>{formatCentsToBrl(totalOwnerCostCents)}</strong>{" "}
                • Lucro:{" "}
                <strong>
                  {formatCentsToBrl(totalOwnerSaleCents - totalOwnerCostCents)}
                </strong>
              </span>
            ) : (
              <span>
                Campos <code>total_cost_cents</code> e{" "}
                <code>margin_percent</code> omitidos pelo schema Pydantic{" "}
                <code>QuoteTechnicianResponse</code>.
              </span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center justify-between text-xs">
              <span>Ordens de Serviço em Campo</span>
              <Wrench className="size-4 text-sky-600" />
            </CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-900">
              {workOrdersQuery.isLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                `${activeWorkOrdersCount} ativa(s)`
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-slate-500">
            Total de {workOrders.length} O.S. emitida(s) na organização
          </CardContent>
        </Card>
      </div>

      {/* 11-Month Preventive Maintenance & Warranty Radar (Owner Only) */}
      {isOwner && (
        <Card className="border-amber-300 bg-amber-50/40">
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <div className="size-9 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-700">
                  <ShieldAlert className="size-5" />
                </div>
                <div>
                  <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
                    Radar de Renovação de Garantia & Manutenção Preventiva (11
                    Meses)
                    <Badge className="bg-amber-500 text-slate-950 font-semibold">
                      {expiringWarranties.length} Alerta(s)
                    </Badge>
                  </CardTitle>
                  <CardDescription className="text-xs text-slate-600">
                    Instalações concluídas há ~11 meses identificadas pelo job
                    Taskiq (<code>warranty_cron.py</code>) para oferta de
                    contrato de manutenção preventiva antes do vencimento de 12
                    meses.
                  </CardDescription>
                </div>
              </div>
              <Link href="/vault">
                <Button variant="outline" size="sm" className="gap-1.5">
                  <ShieldCheck className="size-4 text-emerald-700" />
                  Abrir Cofre de Garantias
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {warrantiesQuery.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : expiringWarranties.length === 0 ? (
              <p className="text-xs text-slate-600">
                Nenhuma instalação próxima ao vencimento de 12 meses no momento.
              </p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {expiringWarranties.map((item) => (
                  <div
                    key={item.work_order_id}
                    className="rounded-xl bg-white border border-amber-200 p-4 shadow-xs flex flex-col justify-between gap-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-sm text-slate-900">
                          {item.customer_name}
                        </span>
                        <Badge className="bg-amber-100 text-amber-900 border-amber-300">
                          Vence em {item.days_until_expiration} dia(s)
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-600">
                        Garantia até:{" "}
                        <strong>
                          {formatDatePtBr(item.warranty_expires_at)}
                        </strong>{" "}
                        • WhatsApp: <strong>{item.customer_phone_whatsapp}</strong>
                      </p>
                      <p className="text-xs text-slate-500">
                        Cloud P2P:{" "}
                        <code className="bg-slate-100 px-1.5 py-0.5 rounded">
                          {item.cloud_p2p_id ?? "N/A"}
                        </code>{" "}
                        • {item.installed_serials_count} equipamento(s) com S/N
                        rastreado(s)
                      </p>
                    </div>
                    <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                      <span className="text-[11px] text-amber-800 flex items-center gap-1 font-medium">
                        <AlertTriangle className="size-3.5" />
                        Alerta preventivo disparado no Outbox
                      </span>
                      <Link href={`/work-orders/${item.work_order_id}`}>
                        <Button size="xs" variant="outline" className="gap-1">
                          Inspecionar O.S. & S/Ns
                          <ArrowRight className="size-3" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Two-Column Operational Overview: Quotes & Field Work Orders */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Commercial Proposals */}
        <Card>
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold">
                Propostas Comerciais Recentes
              </CardTitle>
              <CardDescription className="text-xs">
                Ciclo de vida com aprovação pública e bloqueio pessimista de
                estoque
              </CardDescription>
            </div>
            <Link href="/quotes">
              <Button variant="ghost" size="sm" className="gap-1 text-xs">
                Ver todas
                <ArrowRight className="size-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {quotesQuery.isLoading ? (
              <Skeleton className="h-36 w-full" />
            ) : quotes.length === 0 ? (
              <p className="text-xs text-slate-500">
                Nenhum orçamento cadastrado.
              </p>
            ) : (
              quotes.slice(0, 5).map((quote) => (
                <div
                  key={quote.id}
                  className="rounded-lg border border-slate-200 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white hover:border-slate-300 transition-colors"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-900">
                        {quote.customer.name}
                      </span>
                      <Badge variant="outline" className="text-[11px]">
                        {QUOTE_STATUS_LABELS_PT_BR[quote.status]}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-500">
                      Valor Venta:{" "}
                      <strong className="text-slate-800">
                        {formatCentsToBrl(quote.total_sale_cents)}
                      </strong>
                      {isQuoteOwnerResponse(quote) && (
                        <span className="ml-2 text-emerald-700 font-medium">
                          • Margem: {Number(quote.margin_percent).toFixed(1)}%
                        </span>
                      )}
                    </p>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <Link href={`/p/${quote.public_token}`}>
                      <Button
                        size="xs"
                        variant="outline"
                        className="gap-1 text-amber-800 border-amber-300 bg-amber-50 hover:bg-amber-100"
                      >
                        <ExternalLink className="size-3" />
                        Portal Cliente
                      </Button>
                    </Link>
                    <Link href={`/quotes/${quote.id}`}>
                      <Button size="xs" variant="secondary">
                        Detalhes
                      </Button>
                    </Link>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Field Work Orders */}
        <Card>
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold">
                Ordens de Serviço de Instalação (CFTV)
              </CardTitle>
              <CardDescription className="text-xs">
                Checklist de campo, fotos no MinIO e Cofre de Números de Série
              </CardDescription>
            </div>
            <Link href="/work-orders">
              <Button variant="ghost" size="sm" className="gap-1 text-xs">
                Ver todas
                <ArrowRight className="size-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {workOrdersQuery.isLoading ? (
              <Skeleton className="h-36 w-full" />
            ) : workOrders.length === 0 ? (
              <p className="text-xs text-slate-500">
                Nenhuma Ordem de Serviço ativa.
              </p>
            ) : (
              workOrders.slice(0, 5).map((wo) => {
                const checkedSteps = wo.checklist_json.filter(
                  (s) => s.is_checked
                ).length;
                const totalSteps = wo.checklist_json.length;
                return (
                  <div
                    key={wo.id}
                    className="rounded-lg border border-slate-200 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white hover:border-slate-300 transition-colors"
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-slate-900">
                          {wo.customer.name}
                        </span>
                        <Badge
                          variant="outline"
                          className={
                            wo.status === "COMPLETED"
                              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                              : "bg-sky-50 text-sky-800 border-sky-200"
                          }
                        >
                          {WORK_ORDER_STATUS_LABELS_PT_BR[wo.status]}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500">
                        Checklist: {checkedSteps}/{totalSteps} • Fotos:{" "}
                        {wo.installation_photos_keys.length} • S/Ns Registrados:{" "}
                        {wo.installed_serials.length}
                      </p>
                    </div>

                    <Link href={`/work-orders/${wo.id}`}>
                      <Button
                        size="xs"
                        className="bg-slate-900 hover:bg-slate-800 text-white gap-1"
                      >
                        <ClipboardList className="size-3" />
                        Executar O.S.
                      </Button>
                    </Link>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
