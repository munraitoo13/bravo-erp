"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Fingerprint,
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { workOrdersApi } from "@/lib/api-client";
import {
  CATEGORY_LABELS_PT_BR,
  QUOTE_STATUS_LABELS_PT_BR,
  formatCentsToBrl,
  formatDatePtBr,
  formatDateTimePtBr,
} from "@/lib/formatters";

export function Sha256VerifierPortal({
  sha256Hash,
}: {
  readonly sha256Hash: string;
}): React.JSX.Element {
  const verifyQuery = useQuery({
    queryKey: ["verify-sha256", sha256Hash],
    queryFn: () => workOrdersApi.verifyBySha256(sha256Hash),
    enabled: Boolean(sha256Hash),
  });

  if (verifyQuery.isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6 space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (verifyQuery.isError || !verifyQuery.data) {
    return (
      <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
        <Card className="max-w-lg w-full border-red-300">
          <CardHeader>
            <div className="flex items-center gap-2 text-red-600">
              <ShieldAlert className="size-6" />
              <CardTitle>Hash Criptográfico Não Localizado</CardTitle>
            </div>
            <CardDescription>
              Nenhum certificado de proposta ou garantia corresponde ao digest
              SHA-256 informado.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <code className="block text-xs bg-slate-100 p-2.5 rounded break-all">
              {sha256Hash}
            </code>
            <Link href="/vault">
              <Button variant="outline" className="w-full">
                Voltar ao Cofre de Garantias (/vault)
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  const doc = verifyQuery.data;

  return (
    <div className="min-h-screen bg-slate-100 pb-12">
      <div className="bg-slate-950 text-slate-100 px-4 py-2.5 border-b border-slate-800">
        <div className="max-w-4xl mx-auto flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="flex items-center gap-1.5 text-emerald-400 font-semibold">
            <Fingerprint className="size-4" />
            Verificador Público de Autenticidade Criptográfica SHA-256
          </span>
          <Link href="/vault">
            <Button
              size="xs"
              variant="outline"
              className="border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800 gap-1"
            >
              <ArrowLeft className="size-3" />
              Voltar ao Cofre de Garantias
            </Button>
          </Link>
        </div>
      </div>

      <main className="max-w-4xl mx-auto px-4 pt-6 space-y-6">
        <Card className="border-emerald-300 shadow-lg">
          <CardHeader className="bg-emerald-950 text-white rounded-t-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="size-12 rounded-xl bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-300">
                  <ShieldCheck className="size-7" />
                </div>
                <div>
                  <CardTitle className="text-lg font-bold text-white flex items-center gap-2">
                    Documento Autêntico & Certificado Verificado
                    <CheckCircle2 className="size-5 text-emerald-400" />
                  </CardTitle>
                  <CardDescription className="text-xs text-emerald-200">
                    Emitido por {doc.organization_name} (CNPJ:{" "}
                    {doc.organization_cnpj})
                  </CardDescription>
                </div>
              </div>

              <Badge
                className={
                  doc.is_warranty_active
                    ? "bg-emerald-400 text-slate-950 font-bold"
                    : "bg-amber-400 text-slate-950 font-bold"
                }
              >
                {doc.is_warranty_active
                  ? "GARANTIA ATIVA"
                  : "PROPOSTA AUTENTICADA"}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="p-6 space-y-6">
            {/* SHA-256 Digest Box */}
            <div className="rounded-xl bg-slate-900 text-slate-100 p-4 space-y-1">
              <span className="text-[11px] uppercase tracking-wider text-emerald-400 font-semibold block">
                Assinatura Digital SHA-256 do PDF (WeasyPrint)
              </span>
              <code className="text-xs font-mono break-all text-white block">
                {doc.pdf_sha256_hash}
              </code>
            </div>

            {/* Metadata Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 rounded-xl bg-slate-50 border border-slate-200 p-4 text-xs">
              <div>
                <span className="text-slate-500 block">Cliente</span>
                <strong className="text-slate-900 text-sm">
                  {doc.customer_name}
                </strong>
                <span className="block text-slate-500">
                  Doc: {doc.customer_document_masked}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">
                  Status & Valor Comercial
                </span>
                <strong className="text-slate-900">
                  {QUOTE_STATUS_LABELS_PT_BR[doc.quote_status]} (v
                  {doc.quote_version})
                </strong>
                <span className="block text-emerald-700 font-semibold">
                  {formatCentsToBrl(doc.total_sale_cents)}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">
                  Aprovação & Vigência de Garantia
                </span>
                <strong className="text-slate-900">
                  {doc.warranty_expires_at
                    ? `Garantia até ${formatDatePtBr(doc.warranty_expires_at)}`
                    : "Aguardando conclusão de campo"}
                </strong>
                <span className="block text-slate-500">
                  IP Aceite: {doc.approved_by_ip ?? "—"} (
                  {formatDateTimePtBr(doc.approved_at)})
                </span>
              </div>
            </div>

            {/* Registered Hardware Serial Numbers */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">
                  Cofre de Números de Série & Garantias Registradas (
                  {doc.installed_serials.length})
                </h2>
                {doc.cloud_p2p_id && (
                  <Badge variant="outline" className="font-mono text-xs">
                    Intelbras Cloud P2P: {doc.cloud_p2p_id}
                  </Badge>
                )}
              </div>

              {doc.installed_serials.length === 0 ? (
                <p className="text-xs text-slate-500 py-4">
                  Nenhum número de série registrado até o momento para esta
                  proposta.
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
                        <TableHead>Garantia Cliente (12m)</TableHead>
                        <TableHead>Garantia Fábrica</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {doc.installed_serials.map((sn) => (
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
                          <TableCell className="text-xs font-semibold">
                            {formatDatePtBr(sn.client_warranty_until)}
                          </TableCell>
                          <TableCell className="text-xs text-slate-600">
                            {formatDatePtBr(sn.distributor_warranty_until)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
