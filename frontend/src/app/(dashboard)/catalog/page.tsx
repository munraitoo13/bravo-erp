"use client";

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Lock,
  Package,
  Plus,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
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
import { catalogApi, toastProblemError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { CATEGORY_LABELS_PT_BR, formatCentsToBrl } from "@/lib/formatters";
import { type CatalogCategory, isCatalogOwnerItem } from "@/types/api";

export default function CatalogPage(): React.JSX.Element {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const [searchTerm, setSearchTerm] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  const catalogQuery = useQuery({
    queryKey: ["catalog"],
    queryFn: () => catalogApi.list(),
    enabled: Boolean(user),
  });

  const adjustStockMutation = useMutation({
    mutationFn: ({
      itemId,
      nextStock,
    }: {
      readonly itemId: string;
      readonly nextStock: number;
    }) => catalogApi.update(itemId, { stock_quantity: nextStock }),
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.success(`Estoque atualizado: ${updated.sku}`, {
        description: `Novo saldo físico: ${updated.stock_quantity} un. (Disponível: ${updated.available_quantity} un.)`,
      });
    },
    onError: (err) => {
      toastProblemError(err, "Erro ao atualizar estoque");
    },
  });

  const deleteCatalogMutation = useMutation({
    mutationFn: (itemId: string) => catalogApi.delete(itemId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.success("Item desativado do catálogo.");
    },
    onError: (err) => {
      toastProblemError(err, "Proteção de Catálogo Demo (RFC 7807)");
    },
  });

  const items = (catalogQuery.data ?? []).filter((item) => {
    const matchesCategory =
      selectedCategory === "ALL" || item.category === selectedCategory;
    const term = searchTerm.trim().toLowerCase();
    const matchesSearch =
      !term ||
      item.sku.toLowerCase().includes(term) ||
      item.name_pt_br.toLowerCase().includes(term) ||
      item.brand.toLowerCase().includes(term);
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Catálogo de Equipamentos & Controle de Estoque
          </h1>
          <p className="text-sm text-slate-600">
            Hardware homologado Intelbras Multi-HD MHDX, IP NVD, Western Digital
            WD Purple, fontes MCM e cabeamento Condutti / Furukawa.
          </p>
        </div>

        <Badge
          variant="outline"
          className={
            isOwner
              ? "bg-emerald-50 text-emerald-800 border-emerald-200 py-1.5 px-3"
              : "bg-sky-50 text-sky-800 border-sky-200 py-1.5 px-3"
          }
        >
          {isOwner ? (
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="size-4" />
              Visão OWNER: Custo e Margem Habilitados
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              <Lock className="size-4" />
              Visão TÉCNICO: Preço de Custo Omitido pelo Backend
            </span>
          )}
        </Badge>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Package className="size-4 text-emerald-600" />
                SKUs Ativos ({items.length})
              </CardTitle>
              <CardDescription className="text-xs">
                O saldo reservado é bloqueado atomicamente via{" "}
                <code>SELECT ... FOR UPDATE</code> quando propostas são
                aprovadas.
              </CardDescription>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="relative w-64">
                <Search className="size-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <Input
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Buscar por SKU, nome ou marca..."
                  className="h-8 pl-8 text-xs"
                />
              </div>

              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="h-8 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium"
              >
                <option value="ALL">Todas as Categorias</option>
                {(
                  Object.keys(CATEGORY_LABELS_PT_BR) as CatalogCategory[]
                ).map((cat) => (
                  <option key={cat} value={cat}>
                    {CATEGORY_LABELS_PT_BR[cat]}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {catalogQuery.isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <div className="rounded-lg border border-slate-200 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead>SKU</TableHead>
                    <TableHead>Produto (PT-BR)</TableHead>
                    <TableHead>Categoria</TableHead>
                    <TableHead className="text-center">Físico</TableHead>
                    <TableHead className="text-center">Reservado</TableHead>
                    <TableHead className="text-center">Disponível</TableHead>
                    {isOwner && (
                      <TableHead className="text-right">
                        Custo (Owner)
                      </TableHead>
                    )}
                    <TableHead className="text-right">Venda</TableHead>
                    {isOwner && (
                      <TableHead className="text-right">Ações Demo</TableHead>
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs font-semibold">
                        <div className="flex items-center gap-1.5">
                          <span>{item.sku}</span>
                          {item.is_seed_protected && (
                            <span
                              title="Item protegido da Seed Demo (is_seed_protected=true)"
                              className="text-amber-600"
                            >
                              <ShieldAlert className="size-3.5" />
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium text-xs text-slate-900">
                          {item.name_pt_br}
                        </div>
                        <div className="text-[11px] text-slate-500">
                          Marca: {item.brand}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">
                        <Badge variant="outline" className="text-[10px]">
                          {CATEGORY_LABELS_PT_BR[item.category]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center text-xs font-medium">
                        {item.stock_quantity}
                      </TableCell>
                      <TableCell className="text-center text-xs">
                        {item.reserved_quantity > 0 ? (
                          <Badge className="bg-amber-100 text-amber-900 border-amber-300">
                            {item.reserved_quantity} res.
                          </Badge>
                        ) : (
                          <span className="text-slate-400">0</span>
                        )}
                      </TableCell>
                      <TableCell className="text-center text-xs">
                        <Badge
                          variant="outline"
                          className={
                            item.available_quantity > 0
                              ? "bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold"
                              : "bg-red-50 text-red-800 border-red-200 font-semibold"
                          }
                        >
                          {item.available_quantity} un.
                        </Badge>
                      </TableCell>
                      {isOwner && (
                        <TableCell className="text-right text-xs text-slate-500">
                          {isCatalogOwnerItem(item)
                            ? formatCentsToBrl(item.cost_price_cents)
                            : "—"}
                        </TableCell>
                      )}
                      <TableCell className="text-right text-xs font-semibold text-slate-900">
                        {formatCentsToBrl(item.sale_price_cents)}
                      </TableCell>
                      {isOwner && (
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              type="button"
                              size="xs"
                              variant="outline"
                              disabled={adjustStockMutation.isPending}
                              onClick={() =>
                                adjustStockMutation.mutate({
                                  itemId: item.id,
                                  nextStock: item.stock_quantity + 5,
                                })
                              }
                              title="Adicionar +5 unidades ao estoque físico"
                            >
                              <Plus className="size-3 mr-0.5" />5 un.
                            </Button>
                            <Button
                              type="button"
                              size="icon-xs"
                              variant="ghost"
                              disabled={deleteCatalogMutation.isPending}
                              onClick={() =>
                                deleteCatalogMutation.mutate(item.id)
                              }
                              title={
                                item.is_seed_protected
                                  ? "Testar bloqueio 403 Problem+JSON em item protegido da Demo"
                                  : "Desativar item"
                              }
                            >
                              <Trash2 className="size-3.5 text-red-600" />
                            </Button>
                          </div>
                        </TableCell>
                      )}
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
