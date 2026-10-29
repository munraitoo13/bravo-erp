"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Camera,
  CheckCircle2,
  HardHat,
  QrCode,
  ShieldCheck,
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
import { workOrdersApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  WORK_ORDER_STATUS_LABELS_PT_BR,
  formatDatePtBr,
} from "@/lib/formatters";
import type { WorkOrderStatus } from "@/types/api";

export default function WorkOrdersListPage(): React.JSX.Element {
  const { user } = useAuth();
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const workOrdersQuery = useQuery({
    queryKey: ["work-orders"],
    queryFn: () => workOrdersApi.list(),
    enabled: Boolean(user),
  });

  const workOrders = (workOrdersQuery.data ?? []).filter(
    (wo) => statusFilter === "ALL" || wo.status === statusFilter
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <HardHat className="size-6 text-sky-600" />
            Ordens de Serviço de Campo (Mobile-First)
          </h1>
          <p className="text-sm text-slate-600">
            Execução técnica de instalações CFTV: checklist operacional, upload
            de fotos no MinIO e Cofre de Números de Série obrigatório.
          </p>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium"
        >
          <option value="ALL">Todos os Status de O.S.</option>
          {(
            Object.keys(WORK_ORDER_STATUS_LABELS_PT_BR) as WorkOrderStatus[]
          ).map((st) => (
            <option key={st} value={st}>
              {WORK_ORDER_STATUS_LABELS_PT_BR[st]}
            </option>
          ))}
        </select>
      </div>

      {workOrdersQuery.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : workOrders.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-xs text-slate-500">
            Nenhuma Ordem de Serviço encontrada. Aprove uma proposta comercial
            para gerar uma O.S. automaticamente.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {workOrders.map((wo) => {
            const checkedCount = wo.checklist_json.filter(
              (s) => s.is_checked
            ).length;
            const totalSteps = wo.checklist_json.length;
            const totalRequiredSerials = wo.required_serials_summary.reduce(
              (acc, r) => acc + r.required_quantity,
              0
            );
            const totalRegisteredSerials = wo.required_serials_summary.reduce(
              (acc, r) => acc + r.registered_quantity,
              0
            );

            return (
              <Card
                key={wo.id}
                className="border-slate-200 hover:border-sky-300 transition-colors flex flex-col justify-between"
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-base font-bold text-slate-900">
                        {wo.customer.name}
                      </CardTitle>
                      <CardDescription className="text-xs">
                        Técnico:{" "}
                        <strong>
                          {wo.assigned_technician_name ?? "Equipe Técnica Bravo"}
                        </strong>{" "}
                        • WhatsApp: {wo.customer.phone_whatsapp}
                      </CardDescription>
                    </div>
                    <Badge
                      variant="outline"
                      className={
                        wo.status === "COMPLETED"
                          ? "bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold"
                          : wo.status === "IN_FIELD"
                            ? "bg-sky-50 text-sky-800 border-sky-200 font-semibold"
                            : "bg-amber-50 text-amber-800 border-amber-200"
                      }
                    >
                      {WORK_ORDER_STATUS_LABELS_PT_BR[wo.status]}
                    </Badge>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  {/* Progress Badges */}
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="rounded-lg bg-slate-50 border border-slate-200 p-2.5 text-center">
                      <span className="text-[10px] text-slate-500 block">
                        Checklist
                      </span>
                      <strong className="text-slate-900">
                        {checkedCount} / {totalSteps}
                      </strong>
                    </div>

                    <div className="rounded-lg bg-slate-50 border border-slate-200 p-2.5 text-center">
                      <span className="text-[10px] text-slate-500 block">
                        Fotos MinIO
                      </span>
                      <strong className="text-slate-900 flex items-center justify-center gap-1">
                        <Camera className="size-3 text-sky-600" />
                        {wo.installation_photos_keys.length}
                      </strong>
                    </div>

                    <div className="rounded-lg bg-slate-50 border border-slate-200 p-2.5 text-center">
                      <span className="text-[10px] text-slate-500 block">
                        Cofre de S/N
                      </span>
                      <strong className="text-slate-900 flex items-center justify-center gap-1">
                        <QrCode className="size-3 text-emerald-600" />
                        {totalRegisteredSerials} / {totalRequiredSerials}
                      </strong>
                    </div>
                  </div>

                  {wo.warranty_expires_at && (
                    <div className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-1.5 flex items-center justify-between">
                      <span className="flex items-center gap-1.5 font-medium">
                        <ShieldCheck className="size-3.5" />
                        Garantia ativa até{" "}
                        {formatDatePtBr(wo.warranty_expires_at)}
                      </span>
                      {wo.cloud_p2p_id && (
                        <code className="text-[11px]">{wo.cloud_p2p_id}</code>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                    <Link href={`/quotes/${wo.quote_id}`}>
                      <Button variant="ghost" size="xs" className="text-xs">
                        Ver Proposta Origem
                      </Button>
                    </Link>

                    <Link href={`/work-orders/${wo.id}`}>
                      <Button
                        size="sm"
                        className="bg-slate-900 hover:bg-slate-800 text-white gap-1.5"
                      >
                        {wo.status === "COMPLETED" ? (
                          <>
                            <CheckCircle2 className="size-4 text-emerald-400" />
                            Inspecionar O.S. Concluída
                          </>
                        ) : (
                          <>
                            <Wrench className="size-4 text-sky-400" />
                            Abrir Execução em Campo
                          </>
                        )}
                      </Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
