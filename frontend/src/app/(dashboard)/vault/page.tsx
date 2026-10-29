"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ExternalLink,
  Fingerprint,
  Search,
  ShieldAlert,
  ShieldCheck,
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { quotesApi, workOrdersApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  CATEGORY_LABELS_PT_BR,
  formatDatePtBr,
} from "@/lib/formatters";

export default function EquipmentWarrantyVaultPage(): React.JSX.Element {
  const router = useRouter();
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const [serialSearch, setSerialSearch] = useState<string>("");
  const [sha256Input, setSha256Input] = useState<string>("");

  const workOrdersQuery = useQuery({
    queryKey: ["work-orders"],
    queryFn: () => workOrdersApi.list(),
    enabled: Boolean(user),
  });

  const quotesQuery = useQuery({
    queryKey: ["quotes"],
    queryFn: () => quotesApi.list(),
    enabled: Boolean(user),
  });

  const expiringQuery = useQuery({
    queryKey: ["warranties-expiring"],
    queryFn: () => workOrdersApi.listExpiringWarranties(),
    enabled: Boolean(user && isOwner),
  });

  const workOrders = workOrdersQuery.data ?? [];
  const quotesWithHash = (quotesQuery.data ?? []).filter(
    (q) => Boolean(q.pdf_sha256_hash)
  );
  const expiringWarranties = expiringQuery.data ?? [];

  const flattenedSerials = workOrders.flatMap((wo) =>
    wo.installed_serials.map((sn) => ({
      ...sn,
      customerName: wo.customer.name,
      customerPhone: wo.customer.phone_whatsapp,
      workOrderStatus: wo.status,
      cloudP2pId: wo.cloud_p2p_id,
    }))
  );

  const filteredSerials = flattenedSerials.filter((sn) => {
    const term = serialSearch.trim().toLowerCase();
    if (!term) return true;
    return (
      sn.serial_number.toLowerCase().includes(term) ||
      sn.sku.toLowerCase().includes(term) ||
      sn.name_pt_br.toLowerCase().includes(term) ||
      sn.customerName.toLowerCase().includes(term) ||
      sn.channel_or_slot_label.toLowerCase().includes(term)
    );
  });

  const handleVerifyHashSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    const cleaned = sha256Input.trim();
    if (!cleaned) return;
    router.push(`/verify/${cleaned}`);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <ShieldCheck className="size-6 text-emerald-600" />
            Cofre de Equipamentos, Números de Série & Garantias
          </h1>
          <p className="text-sm text-slate-600">
            Rastreabilidade individual de DVRs Intelbras MHDX, HDs WD Purple e
            câmeras por cliente, canal/slot, vigência de garantia e verificação
            criptográfica SHA-256.
          </p>
        </div>

        <Badge className="bg-emerald-600 text-white py-1.5 px-3">
          {flattenedSerials.length} S/N(s) Registrado(s) no Cofre
        </Badge>
      </div>

      {/* Cryptographic SHA-256 Verifier Lookup Card */}
      <Card className="border-emerald-200 bg-emerald-50/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <Fingerprint className="size-4 text-emerald-700" />
            Verificador Público de Certificado PDF & Assinatura SHA-256 (
            <code>/verify/[hash]</code>)
          </CardTitle>
          <CardDescription className="text-xs">
            Insira o hash SHA-256 de 64 caracteres de qualquer proposta/termo de
            garantia ou clique em um certificado emitido abaixo.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            onSubmit={handleVerifyHashSubmit}
            className="flex flex-col sm:flex-row gap-2"
          >
            <Input
              value={sha256Input}
              onChange={(e) => setSha256Input(e.target.value)}
              placeholder="Cole o hash SHA-256 (64 hex chars) para validar autenticidade..."
              className="h-9 bg-white font-mono text-xs flex-1"
            />
            <Button
              type="submit"
              disabled={!sha256Input.trim()}
              className="bg-emerald-600 hover:bg-emerald-700 text-white h-9 gap-1.5"
            >
              <Fingerprint className="size-4" />
              Verificar Autenticidade
            </Button>
          </form>

          {quotesWithHash.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-slate-700 block">
                Certificados Criptográficos Emitidos na Organização:
              </span>
              <div className="flex flex-wrap gap-2">
                {quotesWithHash.map((q) => (
                  <Link
                    key={q.id}
                    href={`/verify/${q.pdf_sha256_hash ?? ""}`}
                  >
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      className="bg-white border-emerald-300 text-emerald-900 hover:bg-emerald-50 font-mono gap-1.5"
                    >
                      <ShieldCheck className="size-3.5 text-emerald-600" />
                      {q.customer.name} ({q.pdf_sha256_hash?.slice(0, 12)}...)
                      <ExternalLink className="size-3" />
                    </Button>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 11-Month Expiring Warranties Radar (if Owner) */}
      {isOwner && expiringWarranties.length > 0 && (
        <Card className="border-amber-300 bg-amber-50/40">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-bold text-amber-950 flex items-center gap-2">
              <ShieldAlert className="size-4 text-amber-600" />
              Instalações no Radar Preventivo de 11 Meses (
              {expiringWarranties.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {expiringWarranties.map((item) => (
              <div
                key={item.work_order_id}
                className="rounded-lg bg-white border border-amber-200 p-3 flex items-center justify-between gap-2 text-xs"
              >
                <div>
                  <strong className="text-slate-900 block">
                    {item.customer_name}
                  </strong>
                  <span className="text-slate-600">
                    Vencimento: {formatDatePtBr(item.warranty_expires_at)} (
                    {item.days_until_expiration} dias) •{" "}
                    {item.installed_serials_count} S/Ns
                  </span>
                </div>
                <Link href={`/work-orders/${item.work_order_id}`}>
                  <Button size="xs" variant="outline">
                    Ver O.S.
                  </Button>
                </Link>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Master Serial Number Vault Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-bold">
                Registro Geral de Números de Série Instalados (
                {filteredSerials.length})
              </CardTitle>
              <CardDescription className="text-xs">
                Consulte qualquer equipamento instalado por Número de Série,
                SKU, cliente ou porta BNC/SATA.
              </CardDescription>
            </div>

            <div className="relative w-full sm:w-80">
              <Search className="size-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <Input
                value={serialSearch}
                onChange={(e) => setSerialSearch(e.target.value)}
                placeholder="Buscar S/N, SKU, cliente ou canal..."
                className="h-8 pl-8 text-xs"
              />
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {workOrdersQuery.isLoading ? (
            <Skeleton className="h-56 w-full" />
          ) : filteredSerials.length === 0 ? (
            <p className="text-xs text-slate-500 py-8 text-center">
              Nenhum número de série encontrado para a busca informada.
            </p>
          ) : (
            <div className="rounded-lg border border-slate-200 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead>Número de Série (S/N)</TableHead>
                    <TableHead>Canal / Slot</TableHead>
                    <TableHead>Equipamento (SKU)</TableHead>
                    <TableHead>Categoria</TableHead>
                    <TableHead>Cliente / Local</TableHead>
                    <TableHead>Garantia Cliente (12m)</TableHead>
                    <TableHead>Garantia Fábrica</TableHead>
                    <TableHead className="text-right">O.S.</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredSerials.map((sn) => (
                    <TableRow key={sn.id}>
                      <TableCell className="font-mono text-xs font-bold text-emerald-800">
                        {sn.serial_number}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {sn.channel_or_slot_label}
                      </TableCell>
                      <TableCell className="text-xs font-medium">
                        [{sn.sku}] {sn.name_pt_br}
                      </TableCell>
                      <TableCell className="text-xs">
                        <Badge variant="outline" className="text-[10px]">
                          {CATEGORY_LABELS_PT_BR[sn.category]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">
                        <div className="font-semibold text-slate-900">
                          {sn.customerName}
                        </div>
                        {sn.cloudP2pId && (
                          <span className="text-[10px] font-mono text-slate-500">
                            P2P: {sn.cloudP2pId}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs font-semibold text-emerald-800">
                        {formatDatePtBr(sn.client_warranty_until)}
                      </TableCell>
                      <TableCell className="text-xs text-slate-600">
                        {formatDatePtBr(sn.distributor_warranty_until)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Link href={`/work-orders/${sn.work_order_id}`}>
                          <Button size="xs" variant="ghost">
                            Ver O.S.
                          </Button>
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
