"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  Calculator,
  CheckCircle2,
  Plus,
  Trash2,
  UserPlus,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  SizingCalculatorWorkspace,
  type SizingDraftSnapshot,
} from "@/components/sizing/sizing-calculator-workspace";
import {
  SIZING_DRAFT_STORAGE_KEY,
  catalogApi,
  quotesApi,
  toastProblemError,
} from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { CATEGORY_LABELS_PT_BR, formatCentsToBrl } from "@/lib/formatters";
import { isCatalogOwnerItem } from "@/types/api";

interface EditableQuoteLine {
  readonly catalog_item_id: string;
  readonly sku: string;
  readonly name_pt_br: string;
  readonly quantity: number;
  readonly unit_sale_cents: number;
  readonly unit_cost_cents?: number;
  readonly is_auto_derived: boolean;
}

const newCustomerSchema = z.object({
  name: z.string().min(2, "Informe a razão social ou nome do condomínio."),
  document_cpf_cnpj: z.string().min(11, "Informe um CPF ou CNPJ válido."),
  phone_whatsapp: z.string().min(8, "Informe o WhatsApp de contato."),
  email: z.string().email("Informe um e-mail válido."),
});

type NewCustomerFormValues = z.infer<typeof newCustomerSchema>;

function loadStoredSizingDraft(): {
  readonly lines: EditableQuoteLine[];
  readonly snapshot: Readonly<Record<string, unknown>> | null;
} {
  if (typeof window === "undefined") {
    return { lines: [], snapshot: null };
  }
  try {
    const raw = window.localStorage.getItem(SIZING_DRAFT_STORAGE_KEY);
    if (!raw) {
      return { lines: [], snapshot: null };
    }
    const parsed = JSON.parse(raw) as SizingDraftSnapshot;
    if (parsed?.calculation?.bom_items) {
      return {
        lines: parsed.calculation.bom_items.map((item) => ({
          catalog_item_id: item.catalog_item_id,
          sku: item.sku,
          name_pt_br: item.name_pt_br,
          quantity: item.quantity,
          unit_sale_cents: item.unit_sale_cents,
          unit_cost_cents:
            "unit_cost_cents" in item ? item.unit_cost_cents : undefined,
          is_auto_derived: item.is_auto_derived,
        })),
        snapshot: {
          camera_groups: parsed.camera_groups,
          topology: parsed.calculation.topology,
          storage: parsed.calculation.storage,
          electrical: parsed.calculation.electrical,
        },
      };
    }
  } catch {
    // Ignore corrupt draft
  }
  return { lines: [], snapshot: null };
}

export default function NewQuotePage(): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [validDays, setValidDays] = useState<number>(15);
  const [showNewCustomerForm, setShowNewCustomerForm] =
    useState<boolean>(false);
  const [lines, setLines] = useState<EditableQuoteLine[]>(
    () => loadStoredSizingDraft().lines
  );
  const [sizingSnapshotJson] = useState<
    Readonly<Record<string, unknown>> | null
  >(() => loadStoredSizingDraft().snapshot);
  const [selectedCatalogItemId, setSelectedCatalogItemId] =
    useState<string>("");
  const [addQuantity, setAddQuantity] = useState<number>(1);

  const customersQuery = useQuery({
    queryKey: ["customers"],
    queryFn: () => quotesApi.listCustomers(),
    enabled: Boolean(user),
  });

  const catalogQuery = useQuery({
    queryKey: ["catalog"],
    queryFn: () => catalogApi.list(),
    enabled: Boolean(user),
  });

  const activeCustomerId =
    selectedCustomerId || customersQuery.data?.[0]?.id || "";
  const activeCatalogItemId =
    selectedCatalogItemId || catalogQuery.data?.[0]?.id || "";

  const customerForm = useForm<NewCustomerFormValues>({
    resolver: zodResolver(newCustomerSchema),
    defaultValues: {
      name: "",
      document_cpf_cnpj: "",
      phone_whatsapp: "",
      email: "",
    },
  });

  const createCustomerMutation = useMutation({
    mutationFn: (values: NewCustomerFormValues) =>
      quotesApi.createCustomer({
        ...values,
        address_json: { city: "São Paulo", state: "SP" },
      }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
      setSelectedCustomerId(created.id);
      setShowNewCustomerForm(false);
      customerForm.reset();
      toast.success(`Cliente "${created.name}" cadastrado com sucesso!`);
    },
    onError: (err) => {
      toastProblemError(err, "Erro ao cadastrar cliente");
    },
  });

  const createQuoteMutation = useMutation({
    mutationFn: () =>
      quotesApi.create({
        customer_id: activeCustomerId,
        valid_days: validDays,
        sizing_input_json: sizingSnapshotJson,
        items: lines.map((line) => ({
          catalog_item_id: line.catalog_item_id,
          quantity: line.quantity,
          unit_sale_cents: line.unit_sale_cents,
          is_auto_derived: line.is_auto_derived,
        })),
      }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      toast.success("Proposta Comercial criada em Rascunho (DRAFT)!", {
        description: `Total: ${formatCentsToBrl(created.total_sale_cents)}`,
      });
      router.push(`/quotes/${created.id}`);
    },
    onError: (err) => {
      toastProblemError(err, "Falha ao salvar proposta comercial");
    },
  });

  const handleAddManualItem = (): void => {
    const item = (catalogQuery.data ?? []).find(
      (c) => c.id === activeCatalogItemId
    );
    if (!item) return;

    setLines((prev) => {
      const existingIdx = prev.findIndex(
        (l) => l.catalog_item_id === item.id
      );
      if (existingIdx >= 0) {
        return prev.map((l, idx) =>
          idx === existingIdx
            ? { ...l, quantity: l.quantity + Math.max(1, addQuantity) }
            : l
        );
      }
      return [
        ...prev,
        {
          catalog_item_id: item.id,
          sku: item.sku,
          name_pt_br: item.name_pt_br,
          quantity: Math.max(1, addQuantity),
          unit_sale_cents: item.sale_price_cents,
          unit_cost_cents: isCatalogOwnerItem(item)
            ? item.cost_price_cents
            : undefined,
          is_auto_derived: false,
        },
      ];
    });
  };

  const totalSaleCents = lines.reduce(
    (acc, l) => acc + l.quantity * l.unit_sale_cents,
    0
  );
  const totalCostCents = lines.reduce(
    (acc, l) => acc + l.quantity * (l.unit_cost_cents ?? 0),
    0
  );
  const marginPercent =
    totalSaleCents > 0
      ? ((totalSaleCents - totalCostCents) / totalSaleCents) * 100
      : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link href="/quotes">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="size-4" />
            Voltar para Propostas
          </Button>
        </Link>
        <Badge variant="outline" className="bg-emerald-50 text-emerald-800">
          Construtor de Propostas CFTV
        </Badge>
      </div>

      <Tabs defaultValue="wizard" className="space-y-4">
        <TabsList>
          <TabsTrigger value="wizard" className="gap-1.5">
            <Calculator className="size-3.5" />
            1. Dimensionamento Assistido (/api/v1/sizing/calculate)
          </TabsTrigger>
          <TabsTrigger value="manual" className="gap-1.5">
            <Plus className="size-3.5" />
            2. Edição de Itens & Cadastro de Cliente ({lines.length} itens)
          </TabsTrigger>
        </TabsList>

        <TabsContent value="wizard">
          <SizingCalculatorWorkspace mode="quote-builder" />
        </TabsContent>

        <TabsContent value="manual" className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-base font-bold">
                    Cliente & Condições Comerciais
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Selecione um cliente existente ou cadastre um novo condomínio
                    / empresa.
                  </CardDescription>
                </div>
                {isOwner && (
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    onClick={() => setShowNewCustomerForm((v) => !v)}
                    className="gap-1"
                  >
                    <UserPlus className="size-3.5" />
                    {showNewCustomerForm ? "Cancelar Novo Cliente" : "Novo Cliente"}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {showNewCustomerForm && (
                <form
                  onSubmit={(e) =>
                    void customerForm.handleSubmit((vals) =>
                      createCustomerMutation.mutate(vals)
                    )(e)
                  }
                  className="rounded-xl bg-slate-50 border border-slate-200 p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end"
                >
                  <div className="space-y-1">
                    <Label className="text-xs">Razão Social / Nome</Label>
                    <Input
                      className="h-8 bg-white text-xs"
                      placeholder="Condomínio Solar..."
                      {...customerForm.register("name")}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">CNPJ / CPF</Label>
                    <Input
                      className="h-8 bg-white text-xs"
                      placeholder="12.345.678/0001-90"
                      {...customerForm.register("document_cpf_cnpj")}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">WhatsApp</Label>
                    <Input
                      className="h-8 bg-white text-xs"
                      placeholder="(11) 99999-0000"
                      {...customerForm.register("phone_whatsapp")}
                    />
                  </div>
                  <div className="flex items-end gap-2">
                    <div className="space-y-1 flex-1">
                      <Label className="text-xs">E-mail</Label>
                      <Input
                        className="h-8 bg-white text-xs"
                        placeholder="sindico@condominio.com.br"
                        {...customerForm.register("email")}
                      />
                    </div>
                    <Button
                      type="submit"
                      size="sm"
                      disabled={createCustomerMutation.isPending}
                      className="bg-emerald-600 hover:bg-emerald-700 text-white"
                    >
                      Salvar
                    </Button>
                  </div>
                </form>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2 space-y-1">
                  <Label className="text-xs">Cliente Selecionado</Label>
                  <select
                    value={activeCustomerId}
                    onChange={(e) => setSelectedCustomerId(e.target.value)}
                    className="w-full h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium"
                  >
                    {(customersQuery.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} — {c.document_cpf_cnpj} ({c.phone_whatsapp})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Prazo de Validade (Dias)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={180}
                    value={validDays}
                    onChange={(e) =>
                      setValidDays(Math.max(1, Number(e.target.value) || 15))
                    }
                    className="h-9 bg-white text-xs"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base font-bold">
                Itens da Proposta Comercial
              </CardTitle>
              <CardDescription className="text-xs">
                Adicione equipamentos do catálogo Intelbras / WD Purple ou ajuste
                quantidades derivadas pelo dimensionamento.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-end gap-3 bg-slate-50 p-3 rounded-xl border border-slate-200">
                <div className="flex-1 min-w-[240px] space-y-1">
                  <Label className="text-xs">Adicionar Item do Catálogo</Label>
                  <select
                    value={activeCatalogItemId}
                    onChange={(e) => setSelectedCatalogItemId(e.target.value)}
                    className="w-full h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium"
                  >
                    {(catalogQuery.data ?? []).map((item) => (
                      <option key={item.id} value={item.id}>
                        [{item.sku}] {item.name_pt_br} —{" "}
                        {formatCentsToBrl(item.sale_price_cents)} (Disp:{" "}
                        {item.available_quantity} un.) —{" "}
                        {CATEGORY_LABELS_PT_BR[item.category]}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="w-28 space-y-1">
                  <Label className="text-xs">Quantidade</Label>
                  <Input
                    type="number"
                    min={1}
                    value={addQuantity}
                    onChange={(e) =>
                      setAddQuantity(Math.max(1, Number(e.target.value) || 1))
                    }
                    className="h-9 bg-white text-xs"
                  />
                </div>

                <Button
                  type="button"
                  onClick={handleAddManualItem}
                  className="h-9 gap-1.5"
                >
                  <Plus className="size-4" />
                  Incluir Item
                </Button>
              </div>

              {lines.length === 0 ? (
                <p className="text-xs text-slate-500 py-6 text-center">
                  Nenhum item adicionado. Utilize a aba de Dimensionamento
                  Assistido ou inclua um equipamento do catálogo acima.
                </p>
              ) : (
                <div className="rounded-lg border border-slate-200 overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-50">
                        <TableHead>SKU</TableHead>
                        <TableHead>Descrição</TableHead>
                        <TableHead>Origem</TableHead>
                        <TableHead className="text-right">Qtd.</TableHead>
                        <TableHead className="text-right">Venda Unit.</TableHead>
                        <TableHead className="text-right">Subtotal</TableHead>
                        <TableHead className="w-16" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {lines.map((line, idx) => (
                        <TableRow key={line.catalog_item_id}>
                          <TableCell className="font-mono text-xs font-semibold">
                            {line.sku}
                          </TableCell>
                          <TableCell className="text-xs font-medium">
                            {line.name_pt_br}
                          </TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="text-[10px]">
                              {line.is_auto_derived
                                ? "Auto-BOM Engenharia"
                                : "Inclusão Manual"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Input
                              type="number"
                              min={1}
                              value={line.quantity}
                              onChange={(e) => {
                                const q = Math.max(
                                  1,
                                  Number(e.target.value) || 1
                                );
                                setLines((prev) =>
                                  prev.map((l, i) =>
                                    i === idx ? { ...l, quantity: q } : l
                                  )
                                );
                              }}
                              className="h-7 w-20 ml-auto text-right text-xs"
                            />
                          </TableCell>
                          <TableCell className="text-right text-xs">
                            {formatCentsToBrl(line.unit_sale_cents)}
                          </TableCell>
                          <TableCell className="text-right font-semibold text-xs">
                            {formatCentsToBrl(
                              line.quantity * line.unit_sale_cents
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              type="button"
                              size="icon-xs"
                              variant="ghost"
                              onClick={() =>
                                setLines((prev) =>
                                  prev.filter((_, i) => i !== idx)
                                )
                              }
                            >
                              <Trash2 className="size-3.5 text-red-600" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-3 border-t border-slate-200">
                <div className="text-xs text-slate-600 space-x-4">
                  <span>
                    Total Venda:{" "}
                    <strong className="text-base text-slate-900">
                      {formatCentsToBrl(totalSaleCents)}
                    </strong>
                  </span>
                  {isOwner && totalCostCents > 0 && (
                    <span>
                      Custo: <strong>{formatCentsToBrl(totalCostCents)}</strong>{" "}
                      • Margem:{" "}
                      <strong className="text-emerald-700">
                        {marginPercent.toFixed(2)}%
                      </strong>
                    </span>
                  )}
                </div>

                <Button
                  type="button"
                  disabled={
                    !isOwner ||
                    lines.length === 0 ||
                    !activeCustomerId ||
                    createQuoteMutation.isPending
                  }
                  onClick={() => createQuoteMutation.mutate()}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold gap-1.5"
                >
                  <CheckCircle2 className="size-4" />
                  {createQuoteMutation.isPending
                    ? "Salvando..."
                    : "Emitir Proposta Comercial"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
