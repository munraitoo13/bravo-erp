"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertOctagon,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  FileDown,
  Lock,
  ShieldCheck,
  Sparkles,
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiProblemError,
  quotesApi,
  toastProblemError,
} from "@/lib/api-client";
import {
  CATEGORY_LABELS_PT_BR,
  QUOTE_STATUS_LABELS_PT_BR,
  formatCentsToBrl,
  formatDatePtBr,
  formatDateTimePtBr,
} from "@/lib/formatters";
import type { ProblemDetails } from "@/types/api";

export function PublicQuotePortal({
  publicToken,
}: {
  readonly publicToken: string;
}): React.JSX.Element {
  const queryClient = useQueryClient();
  const [clientNotes, setClientNotes] = useState<string>("");
  const [lastProblem, setLastProblem] = useState<ProblemDetails | null>(null);

  const quoteQuery = useQuery({
    queryKey: ["public-quote", publicToken],
    queryFn: () => quotesApi.getPublicQuote(publicToken),
    enabled: Boolean(publicToken),
  });

  const approveMutation = useMutation({
    mutationFn: () =>
      quotesApi.approvePublicQuote(publicToken, {
        accepted_terms: true,
        client_notes: clientNotes.trim() || null,
      }),
    onSuccess: async (updated) => {
      setLastProblem(null);
      await queryClient.invalidateQueries({
        queryKey: ["public-quote", publicToken],
      });
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      await queryClient.invalidateQueries({ queryKey: ["work-orders"] });
      toast.success("Proposta Comercial Aprovada com Sucesso!", {
        description: `Estoque reservado atomicamente e Ordem de Serviço gerada (${updated.work_order_id ?? ""}).`,
      });
    },
    onError: (err) => {
      if (err instanceof ApiProblemError) {
        setLastProblem(err.problem);
      }
      toastProblemError(err, "Não foi possível aprovar a proposta");
    },
  });

  if (quoteQuery.isLoading) {
    return (
      <div className="max-w-5xl mx-auto p-6 space-y-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  if (quoteQuery.isError || !quoteQuery.data) {
    return (
      <div className="max-w-3xl mx-auto p-8 text-center space-y-4">
        <h1 className="text-xl font-bold text-slate-900">
          Proposta Comercial não encontrada
        </h1>
        <p className="text-sm text-slate-600">
          Verifique se o link público está correto ou restaure os dados da Demo.
        </p>
        <Link href="/login">
          <Button>Voltar ao Login / Demo</Button>
        </Link>
      </div>
    );
  }

  const quote = quoteQuery.data;

  return (
    <div className="min-h-screen bg-slate-100 pb-12">
      {/* Top Recruiter Helper Bar */}
      <div className="bg-slate-950 text-slate-100 px-4 py-2.5 border-b border-slate-800">
        <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <Badge className="bg-amber-500/20 text-amber-300 border-amber-400/30 gap-1">
              <Sparkles className="size-3" />
              Portal Público do Cliente (Zero-Login)
            </Badge>
            <span className="text-slate-400 hidden sm:inline">
              Preços de custo e margens são 100% omitidos no schema{" "}
              <code>QuotePublicResponse</code>.
            </span>
          </div>

          <div className="flex items-center gap-2">
            {quote.work_order_id && (
              <Link href={`/work-orders/${quote.work_order_id}`}>
                <Button
                  size="xs"
                  className="bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold gap-1"
                >
                  <ClipboardList className="size-3" />
                  Executar O.S. Gerada (Visão Técnico)
                </Button>
              </Link>
            )}
            <Link href="/dashboard">
              <Button
                size="xs"
                variant="outline"
                className="border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800 gap-1"
              >
                <ArrowLeft className="size-3" />
                Voltar ao ERP Interno
              </Button>
            </Link>
          </div>
        </div>
      </div>

      <main className="max-w-5xl mx-auto px-4 pt-6 space-y-6">
        {/* Company & Proposal Header */}
        <Card className="border-slate-200 shadow-md">
          <CardHeader className="bg-slate-900 text-white rounded-t-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="size-11 rounded-xl bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-400">
                  <ShieldCheck className="size-6" />
                </div>
                <div>
                  <CardTitle className="text-lg font-bold text-white">
                    Bravo Segurança Eletrônica Ltda
                  </CardTitle>
                  <CardDescription className="text-xs text-slate-300">
                    Proposta Técnica e Comercial de Sistema CFTV Intelbras •
                    Token #{quote.public_token.slice(0, 8)}
                  </CardDescription>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Badge className="bg-emerald-500 text-slate-950 font-bold">
                  {QUOTE_STATUS_LABELS_PT_BR[quote.status]}
                </Badge>
                {quote.pdf_download_url && (
                  <a
                    href={quote.pdf_download_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-slate-600 bg-slate-800 text-white hover:bg-slate-700 gap-1.5"
                    >
                      <FileDown className="size-4" />
                      Baixar Proposta PDF
                    </Button>
                  </a>
                )}
                {quote.pdf_sha256_hash && (
                  <Link href={`/verify/${quote.pdf_sha256_hash}`}>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-emerald-500/50 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 gap-1.5"
                    >
                      <ShieldCheck className="size-4" />
                      Verificar Autenticidade SHA-256
                    </Button>
                  </Link>
                )}
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-6 space-y-6">
            {/* Customer & Dates */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 rounded-xl bg-slate-50 border border-slate-200 p-4 text-xs">
              <div>
                <span className="text-slate-500 block">Cliente / Destinatário</span>
                <strong className="text-sm text-slate-900">
                  {quote.customer.name}
                </strong>
                <span className="block text-slate-600">
                  Doc: {quote.customer.document_cpf_cnpj}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Contato</span>
                <strong className="text-slate-900">
                  {quote.customer.phone_whatsapp}
                </strong>
                <span className="block text-slate-600">
                  {quote.customer.email}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Validade da Proposta</span>
                <strong className="text-slate-900">
                  Até {formatDatePtBr(quote.valid_until)}
                </strong>
                {quote.approved_at && (
                  <span className="block text-emerald-700 font-semibold">
                    Aprovada em {formatDateTimePtBr(quote.approved_at)}
                  </span>
                )}
              </div>
            </div>

            {/* RFC 7807 Problem Details Alert if Stock Conflict Occurred */}
            {lastProblem && (
              <div className="rounded-xl border border-red-300 bg-red-50 p-4 text-xs text-red-900 space-y-2">
                <div className="flex items-center justify-between">
                  <strong className="text-sm flex items-center gap-1.5">
                    <AlertOctagon className="size-4 text-red-600" />
                    {lastProblem.title} (HTTP {lastProblem.status})
                  </strong>
                  <code className="text-[11px] bg-red-100 px-2 py-0.5 rounded">
                    Correlation-ID: {lastProblem.correlation_id}
                  </code>
                </div>
                <p>{lastProblem.detail}</p>
                {lastProblem.errors && lastProblem.errors.length > 0 && (
                  <ul className="list-disc pl-5 space-y-0.5">
                    {lastProblem.errors.map((e, idx) => (
                      <li key={idx}>
                        SKU <strong>{e.sku}</strong>: disponível{" "}
                        {e.available_quantity} un. / solicitado{" "}
                        {e.requested_quantity} un.
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Itemized BOM Table */}
            <div className="space-y-2">
              <h2 className="text-sm font-bold text-slate-900">
                Escopo de Equipamentos, Acessórios e Serviços Inclusos
              </h2>
              <div className="rounded-lg border border-slate-200 overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50">
                      <TableHead>Código SKU</TableHead>
                      <TableHead>Descrição do Item (PT-BR)</TableHead>
                      <TableHead>Categoria</TableHead>
                      <TableHead className="text-right">Qtd.</TableHead>
                      <TableHead className="text-right">Valor Unit.</TableHead>
                      <TableHead className="text-right">Subtotal</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {quote.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="font-mono text-xs font-semibold">
                          {item.sku}
                        </TableCell>
                        <TableCell className="text-xs font-medium text-slate-900">
                          {item.name_pt_br}
                        </TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className="text-[10px]">
                            {CATEGORY_LABELS_PT_BR[item.category]}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-bold text-xs">
                          {item.quantity}
                        </TableCell>
                        <TableCell className="text-right text-xs">
                          {formatCentsToBrl(item.unit_sale_cents)}
                        </TableCell>
                        <TableCell className="text-right font-semibold text-xs text-slate-900">
                          {formatCentsToBrl(item.line_total_sale_cents)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            {/* Total & 1-Click Customer Approval Section */}
            <div className="rounded-xl bg-emerald-950 text-white p-6 flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-1">
                <span className="text-xs uppercase tracking-wider text-emerald-300 font-semibold">
                  Investimento Total da Proposta
                </span>
                <div className="text-3xl font-bold text-white">
                  {formatCentsToBrl(quote.total_sale_cents)}
                </div>
                <p className="text-xs text-slate-300 flex items-center gap-1.5">
                  <Lock className="size-3.5 text-emerald-400" />
                  Garantia integral de 12 meses para instalação + garantia de
                  fábrica Intelbras / WD Purple.
                </p>
              </div>

              {quote.status === "SENT" ? (
                <div className="flex flex-col sm:flex-row sm:items-end gap-3 w-full md:w-auto">
                  <div className="space-y-1 flex-1 sm:w-64">
                    <Label className="text-xs text-emerald-200">
                      Observações para a equipe técnica (Opcional)
                    </Label>
                    <Input
                      value={clientNotes}
                      onChange={(e) => setClientNotes(e.target.value)}
                      placeholder="Ex.: Liberar portaria a partir das 08h"
                      className="h-10 bg-slate-900 border-slate-700 text-white text-xs"
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={approveMutation.isPending}
                    onClick={() => approveMutation.mutate()}
                    className="h-10 px-5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold gap-2"
                  >
                    <CheckCircle2 className="size-4" />
                    {approveMutation.isPending
                      ? "Reservando Estoque..."
                      : "Aprovar Proposta Comercial (1 Clique)"}
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col sm:items-end gap-2">
                  <Badge className="bg-emerald-500 text-slate-950 font-bold py-1 px-3 text-xs">
                    Status Atual: {QUOTE_STATUS_LABELS_PT_BR[quote.status]}
                  </Badge>
                  {quote.work_order_id && (
                    <Link href={`/work-orders/${quote.work_order_id}`}>
                      <Button
                        size="sm"
                        className="bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold gap-1.5"
                      >
                        <ClipboardList className="size-4" />
                        Acompanhar / Executar Ordem de Serviço
                      </Button>
                    </Link>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
