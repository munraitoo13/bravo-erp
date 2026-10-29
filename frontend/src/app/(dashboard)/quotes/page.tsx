"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ClipboardList,
  Copy,
  ExternalLink,
  FileSpreadsheet,
  PlusCircle,
  Send,
  ShieldCheck,
  XCircle,
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
import { quotesApi, toastProblemError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  QUOTE_STATUS_LABELS_PT_BR,
  formatCentsToBrl,
  formatDatePtBr,
} from "@/lib/formatters";
import { type QuoteStatus, isQuoteOwnerResponse } from "@/types/api";

export default function QuotesListPage(): React.JSX.Element {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const quotesQuery = useQuery({
    queryKey: ["quotes"],
    queryFn: () => quotesApi.list(),
    enabled: Boolean(user),
  });

  const sendQuoteMutation = useMutation({
    mutationFn: (quoteId: string) => quotesApi.send(quoteId),
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      toast.success("Proposta enviada ao cliente (DRAFT -> SENT)!", {
        description: `Link público liberado: /p/${updated.public_token}`,
      });
    },
    onError: (err) => {
      toastProblemError(err, "Erro ao enviar proposta");
    },
  });

  const cancelQuoteMutation = useMutation({
    mutationFn: (quoteId: string) => quotesApi.cancel(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.info(
        "Proposta cancelada e eventual estoque reservado foi liberado."
      );
    },
    onError: (err) => {
      toastProblemError(err, "Erro ao cancelar proposta");
    },
  });

  const copyPublicLink = (token: string): void => {
    if (typeof window === "undefined") return;
    const url = `${window.location.origin}/p/${token}`;
    void navigator.clipboard.writeText(url);
    toast.success("Link público copiado para a área de transferência!", {
      description: url,
    });
  };

  const quotes = (quotesQuery.data ?? []).filter(
    (q) => statusFilter === "ALL" || q.status === statusFilter
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Propostas Comerciais & Orçamentos CFTV
          </h1>
          <p className="text-sm text-slate-600">
            Máquina de estados determinística, portal público de aceite em 1
            clique e reserva pessimista de estoque (
            <code>SELECT ... FOR UPDATE</code>).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium"
          >
            <option value="ALL">Todos os Status</option>
            {(Object.keys(QUOTE_STATUS_LABELS_PT_BR) as QuoteStatus[]).map(
              (st) => (
                <option key={st} value={st}>
                  {QUOTE_STATUS_LABELS_PT_BR[st]}
                </option>
              )
            )}
          </select>

          <Link href="/quotes/new">
            <Button className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5 h-9">
              <PlusCircle className="size-4" />
              Nova Proposta
            </Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <FileSpreadsheet className="size-4 text-emerald-600" />
            Propostas Emitidas ({quotes.length})
          </CardTitle>
          <CardDescription className="text-xs">
            Clique em <strong>Portal Cliente</strong> para simular a visão
            pública de aprovação do condomínio/empresa sem necessidade de login.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {quotesQuery.isLoading ? (
            <Skeleton className="h-56 w-full" />
          ) : quotes.length === 0 ? (
            <p className="text-xs text-slate-500 py-8 text-center">
              Nenhuma proposta encontrada para o filtro selecionado.
            </p>
          ) : (
            <div className="rounded-lg border border-slate-200 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead>Cliente / Condomínio</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Validade</TableHead>
                    {isOwner && (
                      <TableHead className="text-right">Custo Total</TableHead>
                    )}
                    {isOwner && (
                      <TableHead className="text-right">Margem</TableHead>
                    )}
                    <TableHead className="text-right">Valor Venda</TableHead>
                    <TableHead className="text-right">
                      Ações & Links Públicos
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {quotes.map((quote) => (
                    <TableRow key={quote.id}>
                      <TableCell>
                        <Link
                          href={`/quotes/${quote.id}`}
                          className="font-semibold text-xs text-slate-900 hover:text-emerald-700 hover:underline block"
                        >
                          {quote.customer.name}
                        </Link>
                        <span className="text-[11px] text-slate-500">
                          {quote.items.length} item(ns) • Versão v{quote.version}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            quote.status === "COMPLETED" ||
                            quote.status === "APPROVED"
                              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                              : quote.status === "SENT"
                                ? "bg-amber-50 text-amber-800 border-amber-200"
                                : quote.status === "CANCELED"
                                  ? "bg-red-50 text-red-800 border-red-200"
                                  : "bg-slate-100 text-slate-700"
                          }
                        >
                          {QUOTE_STATUS_LABELS_PT_BR[quote.status]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-slate-600">
                        {formatDatePtBr(quote.valid_until)}
                      </TableCell>
                      {isOwner && (
                        <TableCell className="text-right text-xs text-slate-500">
                          {isQuoteOwnerResponse(quote)
                            ? formatCentsToBrl(quote.total_cost_cents)
                            : "—"}
                        </TableCell>
                      )}
                      {isOwner && (
                        <TableCell className="text-right text-xs font-semibold text-emerald-700">
                          {isQuoteOwnerResponse(quote)
                            ? `${Number(quote.margin_percent).toFixed(1)}%`
                            : "—"}
                        </TableCell>
                      )}
                      <TableCell className="text-right font-bold text-xs text-slate-900">
                        {formatCentsToBrl(quote.total_sale_cents)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap items-center justify-end gap-1.5">
                          {isOwner && quote.status === "DRAFT" && (
                            <Button
                              type="button"
                              size="xs"
                              disabled={sendQuoteMutation.isPending}
                              onClick={() =>
                                sendQuoteMutation.mutate(quote.id)
                              }
                              className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1"
                            >
                              <Send className="size-3" />
                              Enviar ao Cliente
                            </Button>
                          )}

                          <Link href={`/p/${quote.public_token}`}>
                            <Button
                              type="button"
                              size="xs"
                              variant="outline"
                              className="gap-1 border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
                            >
                              <ExternalLink className="size-3" />
                              Portal Cliente (/p)
                            </Button>
                          </Link>

                          <Button
                            type="button"
                            size="icon-xs"
                            variant="ghost"
                            onClick={() => copyPublicLink(quote.public_token)}
                            title="Copiar Link Público do Cliente"
                          >
                            <Copy className="size-3.5 text-slate-600" />
                          </Button>

                          {quote.work_order_id && (
                            <Link href={`/work-orders/${quote.work_order_id}`}>
                              <Button
                                type="button"
                                size="xs"
                                variant="outline"
                                className="gap-1 border-sky-300 bg-sky-50 text-sky-900"
                              >
                                <ClipboardList className="size-3" />
                                O.S.
                              </Button>
                            </Link>
                          )}

                          {quote.pdf_sha256_hash && (
                            <Link href={`/verify/${quote.pdf_sha256_hash}`}>
                              <Button
                                type="button"
                                size="xs"
                                variant="outline"
                                className="gap-1 border-emerald-300 bg-emerald-50 text-emerald-900"
                                title="Verificar Autenticidade SHA-256"
                              >
                                <ShieldCheck className="size-3" />
                                SHA-256
                              </Button>
                            </Link>
                          )}

                          {isOwner &&
                            ["DRAFT", "SENT", "APPROVED"].includes(
                              quote.status
                            ) && (
                              <Button
                                type="button"
                                size="icon-xs"
                                variant="ghost"
                                disabled={cancelQuoteMutation.isPending}
                                onClick={() =>
                                  cancelQuoteMutation.mutate(quote.id)
                                }
                                title="Cancelar Proposta"
                              >
                                <XCircle className="size-3.5 text-red-600" />
                              </Button>
                            )}

                          <Link href={`/quotes/${quote.id}`}>
                            <Button type="button" size="xs" variant="secondary">
                              Ver
                            </Button>
                          </Link>
                        </div>
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
