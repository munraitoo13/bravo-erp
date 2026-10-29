"use client";

import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  ExternalLink,
  FileDown,
  History,
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
  CATEGORY_LABELS_PT_BR,
  QUOTE_STATUS_LABELS_PT_BR,
  formatCentsToBrl,
  formatDatePtBr,
  formatDateTimePtBr,
} from "@/lib/formatters";
import { isQuoteOwnerItem, isQuoteOwnerResponse } from "@/types/api";

export default function QuoteDetailPage(): React.JSX.Element {
  const params = useParams<{ id: string }>();
  const quoteId = params.id;
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const quoteQuery = useQuery({
    queryKey: ["quote", quoteId],
    queryFn: () => quotesApi.getById(quoteId),
    enabled: Boolean(user && quoteId),
  });

  const sendMutation = useMutation({
    mutationFn: () => quotesApi.send(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["quote", quoteId] });
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      toast.success("Proposta enviada ao cliente (DRAFT -> SENT)!");
    },
    onError: (err) => toastProblemError(err, "Erro ao enviar proposta"),
  });

  const approveMutation = useMutation({
    mutationFn: () => quotesApi.approveByOwner(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["quote", quoteId] });
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      await queryClient.invalidateQueries({ queryKey: ["work-orders"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.success(
        "Proposta Aprovada! Estoque reservado e Ordem de Serviço gerada."
      );
    },
    onError: (err) =>
      toastProblemError(err, "Conflito de Estoque ou Transição Inválida"),
  });

  const cancelMutation = useMutation({
    mutationFn: () => quotesApi.cancel(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["quote", quoteId] });
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.info("Proposta cancelada com sucesso.");
    },
    onError: (err) => toastProblemError(err, "Erro ao cancelar proposta"),
  });

  if (quoteQuery.isLoading || !quoteQuery.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const quote = quoteQuery.data;
  const ownerQuote = isQuoteOwnerResponse(quote) ? quote : null;

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/quotes">
            <Button variant="ghost" size="sm" className="gap-1.5">
              <ArrowLeft className="size-4" />
              Propostas
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">
                {quote.customer.name}
              </h1>
              <Badge variant="outline">
                {QUOTE_STATUS_LABELS_PT_BR[quote.status]}
              </Badge>
              <Badge variant="secondary">v{quote.version}</Badge>
            </div>
            <p className="text-xs text-slate-500">
              CNPJ/CPF: {quote.customer.document_cpf_cnpj} • Validade:{" "}
              {formatDatePtBr(quote.valid_until)}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/p/${quote.public_token}`}>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
            >
              <ExternalLink className="size-4" />
              Abrir Portal Público do Cliente
            </Button>
          </Link>

          {quote.work_order_id && (
            <Link href={`/work-orders/${quote.work_order_id}`}>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 border-sky-300 bg-sky-50 text-sky-900"
              >
                <ClipboardList className="size-4" />
                Abrir Ordem de Serviço
              </Button>
            </Link>
          )}

          {quote.pdf_download_url && (
            <a
              href={quote.pdf_download_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Button variant="outline" size="sm" className="gap-1.5">
                <FileDown className="size-4" />
                Baixar PDF Assinado
              </Button>
            </a>
          )}

          {quote.pdf_sha256_hash && (
            <Link href={`/verify/${quote.pdf_sha256_hash}`}>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 border-emerald-300 bg-emerald-50 text-emerald-900"
              >
                <ShieldCheck className="size-4" />
                Verificar SHA-256
              </Button>
            </Link>
          )}

          {isOwner && quote.status === "DRAFT" && (
            <Button
              size="sm"
              disabled={sendMutation.isPending}
              onClick={() => sendMutation.mutate()}
              className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
            >
              <Send className="size-4" />
              Enviar ao Cliente
            </Button>
          )}

          {isOwner && quote.status === "SENT" && (
            <Button
              size="sm"
              disabled={approveMutation.isPending}
              onClick={() => approveMutation.mutate()}
              className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
            >
              <CheckCircle2 className="size-4" />
              Aprovar e Reservar Estoque
            </Button>
          )}

          {isOwner &&
            ["DRAFT", "SENT", "APPROVED"].includes(quote.status) && (
              <Button
                size="sm"
                variant="destructive"
                disabled={cancelMutation.isPending}
                onClick={() => cancelMutation.mutate()}
                className="gap-1.5"
              >
                <XCircle className="size-4" />
                Cancelar
              </Button>
            )}
        </div>
      </div>

      {/* Line Items & Financial Totals */}
      <Card>
        <CardHeader className="pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base font-bold">
              Itens da Proposta Comercial ({quote.items.length})
            </CardTitle>
            <CardDescription className="text-xs">
              Valores monetários armazenados em centavos inteiros (ADR-007).
            </CardDescription>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs bg-slate-900 text-white px-4 py-2 rounded-xl">
            {ownerQuote && (
              <>
                <span>
                  Custo:{" "}
                  <strong>{formatCentsToBrl(ownerQuote.total_cost_cents)}</strong>
                </span>
                <span className="text-emerald-400">
                  Margem:{" "}
                  <strong>
                    {Number(ownerQuote.margin_percent).toFixed(2)}%
                  </strong>
                </span>
              </>
            )}
            <span>
              Total Venda:{" "}
              <strong className="text-sm text-amber-300">
                {formatCentsToBrl(quote.total_sale_cents)}
              </strong>
            </span>
          </div>
        </CardHeader>

        <CardContent>
          <div className="rounded-lg border border-slate-200 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead>SKU</TableHead>
                  <TableHead>Descrição (PT-BR)</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead className="text-right">Qtd.</TableHead>
                  {ownerQuote && (
                    <TableHead className="text-right">Custo Unit.</TableHead>
                  )}
                  <TableHead className="text-right">Venda Unit.</TableHead>
                  <TableHead className="text-right">Subtotal Venda</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {quote.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-mono text-xs font-semibold">
                      {item.sku}
                    </TableCell>
                    <TableCell className="text-xs font-medium">
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
                    {ownerQuote && (
                      <TableCell className="text-right text-xs text-slate-500">
                        {isQuoteOwnerItem(item)
                          ? formatCentsToBrl(item.unit_cost_cents)
                          : "—"}
                      </TableCell>
                    )}
                    <TableCell className="text-right text-xs">
                      {formatCentsToBrl(item.unit_sale_cents)}
                    </TableCell>
                    <TableCell className="text-right font-semibold text-xs">
                      {formatCentsToBrl(item.line_total_sale_cents)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Immutable Audit Log Trail */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-bold flex items-center gap-2">
            <History className="size-4 text-slate-600" />
            Trilha de Auditoria Imutável (audit_logs)
          </CardTitle>
          <CardDescription className="text-xs">
            Registro de transições de estado, IP do aprovador e reservas de
            estoque.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {quote.audit_logs.length === 0 ? (
            <p className="text-xs text-slate-500">
              Nenhum evento de auditoria registrado.
            </p>
          ) : (
            quote.audit_logs.map((log) => (
              <div
                key={log.id}
                className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {log.action}
                    </Badge>
                    <span className="text-slate-600">
                      IP: <code>{log.actor_ip ?? "sistema"}</code>
                    </span>
                  </div>
                  <p className="text-slate-700 font-mono text-[11px]">
                    {log.previous_state
                      ? `${JSON.stringify(log.previous_state)} → `
                      : ""}
                    {JSON.stringify(log.new_state)}
                  </p>
                </div>
                <span className="text-slate-500 shrink-0">
                  {formatDateTimePtBr(log.created_at)}
                </span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
