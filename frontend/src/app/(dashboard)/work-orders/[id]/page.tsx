"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  Play,
  QrCode,
  ScanBarcode,
  ShieldCheck,
  Sparkles,
  Upload,
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
import { toastProblemError, workOrdersApi } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import {
  CATEGORY_LABELS_PT_BR,
  WORK_ORDER_STATUS_LABELS_PT_BR,
  formatDatePtBr,
  formatDateTimePtBr,
} from "@/lib/formatters";
import type { RequiredSerialItemSummary } from "@/types/api";

function generateRealisticSerial(sku: string, index: number): string {
  const randomSuffix = Math.random().toString(36).substring(2, 7).toUpperCase();
  if (sku.startsWith("WD")) {
    return `WDP-WX${index}2A9${randomSuffix}`;
  }
  return `ITB-${sku.replace(/[^A-Z0-9]/gi, "")}-${randomSuffix}`;
}

function suggestChannelLabel(
  reqItem: RequiredSerialItemSummary,
  nextIndex: number
): string {
  const num = String(nextIndex).padStart(2, "0");
  if (reqItem.category === "DVR") {
    return `RACK-DVR-${num}`;
  }
  if (reqItem.category === "HDD") {
    return `SATA-${num}`;
  }
  if (reqItem.category === "CAMERA_IP") {
    return `IP-CH-${num} (Portaria / Acesso)`;
  }
  if (reqItem.category === "POE_SWITCH") {
    return `RACK-SW-POE-${num}`;
  }
  return `BNC-${num} (Perímetro)`;
}

export default function WorkOrderExecutionPage(): React.JSX.Element {
  const params = useParams<{ id: string }>();
  const workOrderId = params.id;
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [cloudP2pIdDraft, setCloudP2pIdDraft] = useState<string | null>(null);
  const [fieldNotesDraft, setFieldNotesDraft] = useState<string | null>(null);
  const [selectedCatalogItemId, setSelectedCatalogItemId] =
    useState<string>("");
  const [serialNumberInput, setSerialNumberInput] = useState<string>("");
  const [channelLabelDraft, setChannelLabelDraft] = useState<string | null>(
    null
  );

  const woQuery = useQuery({
    queryKey: ["work-order", workOrderId],
    queryFn: () => workOrdersApi.getById(workOrderId),
    enabled: Boolean(user && workOrderId),
  });

  const woData = woQuery.data;
  const cloudP2pId = cloudP2pIdDraft ?? woData?.cloud_p2p_id ?? "";
  const fieldNotes = fieldNotesDraft ?? woData?.notes ?? "";

  const defaultTargetSummary =
    woData?.required_serials_summary.find((r) => !r.is_satisfied) ??
    woData?.required_serials_summary[0];
  const activeCatalogItemId =
    selectedCatalogItemId || defaultTargetSummary?.catalog_item_id || "";
  const activeSummary =
    woData?.required_serials_summary.find(
      (r) => r.catalog_item_id === activeCatalogItemId
    ) ?? defaultTargetSummary;
  const channelLabelInput =
    channelLabelDraft ??
    (activeSummary
      ? suggestChannelLabel(activeSummary, activeSummary.registered_quantity + 1)
      : "");

  const invalidateWo = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: ["work-order", workOrderId],
    });
    await queryClient.invalidateQueries({ queryKey: ["work-orders"] });
    await queryClient.invalidateQueries({ queryKey: ["quotes"] });
  };

  const startMutation = useMutation({
    mutationFn: () => workOrdersApi.start(workOrderId, fieldNotes || undefined),
    onSuccess: async () => {
      await invalidateWo();
      toast.success("Ordem de Serviço iniciada em campo (IN_FIELD)!");
    },
    onError: (err) => toastProblemError(err, "Erro ao iniciar O.S."),
  });

  const checklistMutation = useMutation({
    mutationFn: (payload: {
      readonly step_id?: string;
      readonly is_checked?: boolean;
      readonly steps?: readonly {
        readonly step_id: string;
        readonly is_checked: boolean;
      }[];
      readonly cloud_p2p_id?: string | null;
      readonly notes?: string | null;
    }) => workOrdersApi.updateChecklist(workOrderId, payload),
    onSuccess: async () => {
      await invalidateWo();
      toast.success("Checklist / metadados de campo atualizados!");
    },
    onError: (err) => toastProblemError(err, "Erro ao atualizar checklist"),
  });

  const uploadDemoPhotoMutation = useMutation({
    mutationFn: () =>
      workOrdersApi.uploadPhotoJson(workOrderId, {
        filename: `evidencia_rack_intelbras_${Date.now()}.jpg`,
        content_type: "image/jpeg",
      }),
    onSuccess: async (updated) => {
      await invalidateWo();
      toast.success("Foto de instalação enviada ao MinIO S3!", {
        description: `Total de fotos anexadas: ${updated.installation_photos_keys.length}`,
      });
    },
    onError: (err) => toastProblemError(err, "Erro no upload da foto"),
  });

  const uploadFilePhotoMutation = useMutation({
    mutationFn: (file: File) =>
      workOrdersApi.uploadPhotoFile(workOrderId, file),
    onSuccess: async (updated) => {
      await invalidateWo();
      toast.success("Arquivo de foto enviado ao MinIO S3!", {
        description: `Total de fotos anexadas: ${updated.installation_photos_keys.length}`,
      });
    },
    onError: (err) => toastProblemError(err, "Erro no upload do arquivo"),
  });

  const registerSerialMutation = useMutation({
    mutationFn: () =>
      workOrdersApi.registerSerial(workOrderId, {
        catalog_item_id: activeCatalogItemId,
        serial_number: serialNumberInput.trim(),
        channel_or_slot_label: channelLabelInput.trim(),
      }),
    onSuccess: async (created) => {
      setSerialNumberInput("");
      setChannelLabelDraft(null);
      await invalidateWo();
      toast.success(`S/N ${created.serial_number} registrado no Cofre!`, {
        description: `${created.name_pt_br} • Garantia cliente até ${formatDatePtBr(created.client_warranty_until)}`,
      });
    },
    onError: (err) =>
      toastProblemError(err, "Falha ao registrar Número de Série"),
  });

  const completeMutation = useMutation({
    mutationFn: () =>
      workOrdersApi.complete(workOrderId, {
        cloud_p2p_id: cloudP2pId.trim() || null,
        notes: fieldNotes.trim() || null,
      }),
    onSuccess: async (completed) => {
      await invalidateWo();
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.success(
        "Ordem de Serviço Concluída & Garantia de 12 Meses Ativada!",
        {
          description: `Estoque baixado e certificado PDF enfileirado no Outbox. Garantia até ${formatDatePtBr(completed.warranty_expires_at)}.`,
        }
      );
    },
    onError: (err) =>
      toastProblemError(
        err,
        "Guardas de Conclusão Pendentes (Checklist, Foto ou S/N)"
      ),
  });

  if (woQuery.isLoading || !woQuery.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const wo = woQuery.data;
  const isCompleted = wo.status === "COMPLETED";

  const checkedStepsCount = wo.checklist_json.filter(
    (s) => s.is_checked
  ).length;
  const allChecklistDone =
    wo.checklist_json.length > 0 &&
    checkedStepsCount === wo.checklist_json.length;
  const hasPhoto = wo.installation_photos_keys.length >= 1;
  const allSerialsSatisfied = wo.required_serials_summary.every(
    (r) => r.is_satisfied
  );

  const handleSimulateBarcodeScan = (): void => {
    const unsatisfied = wo.required_serials_summary.find(
      (r) => !r.is_satisfied
    );
    const target =
      unsatisfied ??
      wo.required_serials_summary.find(
        (r) => r.catalog_item_id === activeCatalogItemId
      ) ??
      wo.required_serials_summary[0];

    if (!target) return;
    setSelectedCatalogItemId(target.catalog_item_id);
    const nextIdx = target.registered_quantity + 1;
    const simulatedSn = generateRealisticSerial(target.sku, nextIdx);
    const simulatedChannel = suggestChannelLabel(target, nextIdx);
    setSerialNumberInput(simulatedSn);
    setChannelLabelDraft(simulatedChannel);
    toast.info(`Leitor Código de Barras / QR: ${simulatedSn}`, {
      description: `Identificado ${target.sku} -> ${simulatedChannel}`,
    });
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/work-orders">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="size-4" />
              O.S.
            </Button>
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">
                O.S. — {wo.customer.name}
              </h1>
              <Badge
                variant="outline"
                className={
                  isCompleted
                    ? "bg-emerald-50 text-emerald-800 border-emerald-200 font-bold"
                    : "bg-sky-50 text-sky-800 border-sky-200 font-bold"
                }
              >
                {WORK_ORDER_STATUS_LABELS_PT_BR[wo.status]}
              </Badge>
            </div>
            <p className="text-xs text-slate-500">
              WhatsApp Cliente: {wo.customer.phone_whatsapp} • Técnico:{" "}
              {wo.assigned_technician_name ?? "Carlos Eduardo (Campo)"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(wo.status === "PENDING" || wo.status === "SCHEDULED") && (
            <Button
              size="sm"
              disabled={startMutation.isPending}
              onClick={() => startMutation.mutate()}
              className="bg-sky-600 hover:bg-sky-700 text-white gap-1.5"
            >
              <Play className="size-4" />
              Iniciar Execução em Campo (IN_FIELD)
            </Button>
          )}

          {!isCompleted && (
            <Button
              size="sm"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
              className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold gap-1.5"
            >
              <CheckCircle2 className="size-4" />
              {completeMutation.isPending
                ? "Finalizando O.S...."
                : "Concluir Ordem de Serviço"}
            </Button>
          )}
        </div>
      </div>

      {/* 3 Completion Guards Status Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div
          className={`rounded-xl border p-3.5 flex items-center justify-between ${
            allChecklistDone
              ? "bg-emerald-50/70 border-emerald-300 text-emerald-900"
              : "bg-amber-50/70 border-amber-300 text-amber-900"
          }`}
        >
          <div>
            <span className="text-[11px] uppercase font-semibold block">
              Guarda 1: Checklist Técnico
            </span>
            <strong className="text-sm">
              {checkedStepsCount} de {wo.checklist_json.length} concluídos
            </strong>
          </div>
          <ClipboardCheck className="size-5" />
        </div>

        <div
          className={`rounded-xl border p-3.5 flex items-center justify-between ${
            hasPhoto
              ? "bg-emerald-50/70 border-emerald-300 text-emerald-900"
              : "bg-amber-50/70 border-amber-300 text-amber-900"
          }`}
        >
          <div>
            <span className="text-[11px] uppercase font-semibold block">
              Guarda 2: Evidência Fotográfica
            </span>
            <strong className="text-sm">
              {wo.installation_photos_keys.length} foto(s) no MinIO (mín. 1)
            </strong>
          </div>
          <Camera className="size-5" />
        </div>

        <div
          className={`rounded-xl border p-3.5 flex items-center justify-between ${
            allSerialsSatisfied
              ? "bg-emerald-50/70 border-emerald-300 text-emerald-900"
              : "bg-amber-50/70 border-amber-300 text-amber-900"
          }`}
        >
          <div>
            <span className="text-[11px] uppercase font-semibold block">
              Guarda 3: Cofre de Números de Série
            </span>
            <strong className="text-sm">
              {allSerialsSatisfied
                ? "100% dos hardwares registrados"
                : "Hardwares pendentes de S/N"}
            </strong>
          </div>
          <QrCode className="size-5" />
        </div>
      </div>

      {/* Section 1: Interactive Field Checklist */}
      <Card>
        <CardHeader className="pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base font-bold">
              1. Checklist de Instalação e Comissionamento CFTV
            </CardTitle>
            <CardDescription className="text-xs">
              Toque em cada etapa concluída em campo. Todas as etapas são
              obrigatórias para encerramento.
            </CardDescription>
          </div>
          {!isCompleted && !allChecklistDone && (
            <Button
              type="button"
              size="xs"
              variant="outline"
              disabled={checklistMutation.isPending}
              onClick={() =>
                checklistMutation.mutate({
                  steps: wo.checklist_json.map((s) => ({
                    step_id: s.step_id,
                    is_checked: true,
                  })),
                })
              }
            >
              Marcar Todas as Etapas
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {wo.checklist_json.map((step) => (
            <label
              key={step.step_id}
              className={`flex items-center justify-between gap-3 rounded-xl border p-3.5 cursor-pointer transition-colors ${
                step.is_checked
                  ? "bg-emerald-50/50 border-emerald-200 text-emerald-950"
                  : "bg-white border-slate-200 hover:bg-slate-50"
              }`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={step.is_checked}
                  disabled={isCompleted || checklistMutation.isPending}
                  onChange={(e) =>
                    checklistMutation.mutate({
                      step_id: step.step_id,
                      is_checked: e.target.checked,
                    })
                  }
                  className="size-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                <span
                  className={`text-sm font-medium ${
                    step.is_checked ? "line-through text-slate-600" : ""
                  }`}
                >
                  {step.label_pt_br}
                </span>
              </div>
              {step.checked_at && (
                <span className="text-[11px] text-slate-500">
                  {formatDateTimePtBr(step.checked_at)}
                </span>
              )}
            </label>
          ))}
        </CardContent>
      </Card>

      {/* Section 2: Photos & Intelbras Cloud P2P ID */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Camera className="size-4 text-sky-600" />
              2. Fotos da Instalação (MinIO S3)
            </CardTitle>
            <CardDescription className="text-xs">
              Envie fotos do rack organizador, conexões BNC/PoE e posicionamento
              das câmeras.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!isCompleted && (
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={uploadDemoPhotoMutation.isPending}
                  onClick={() => uploadDemoPhotoMutation.mutate()}
                  className="bg-sky-600 hover:bg-sky-700 text-white gap-1.5"
                >
                  <Sparkles className="size-4" />
                  {uploadDemoPhotoMutation.isPending
                    ? "Enviando..."
                    : "Anexar Foto de Evidência Rápida (Demo)"}
                </Button>

                <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-medium cursor-pointer hover:bg-slate-50">
                  <Upload className="size-3.5" />
                  Selecionar Arquivo...
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        uploadFilePhotoMutation.mutate(file);
                      }
                    }}
                  />
                </label>
              </div>
            )}

            {wo.installation_photos_keys.length === 0 ? (
              <p className="text-xs text-slate-500">
                Nenhuma foto enviada ainda. Adicione pelo menos 1 foto para
                liberar a conclusão da O.S.
              </p>
            ) : (
              <div className="space-y-1.5">
                {wo.installation_photos_keys.map((key, idx) => (
                  <div
                    key={key}
                    className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 flex items-center justify-between text-xs"
                  >
                    <span className="font-mono text-[11px] truncate max-w-xs">
                      #{idx + 1}: {key}
                    </span>
                    <Badge
                      variant="outline"
                      className="bg-emerald-50 text-emerald-800 border-emerald-200"
                    >
                      Salvo no MinIO
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold">
              3. Intelbras Cloud P2P & Observações Técnicas
            </CardTitle>
            <CardDescription className="text-xs">
              Código QR de acesso remoto no app Intelbras ISIC Lite / Sim Next.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label className="text-xs">ID Intelbras Cloud P2P</Label>
                {!isCompleted && (
                  <button
                    type="button"
                    onClick={() =>
                      setCloudP2pIdDraft(
                        `ITB-P2P-MHDX-${Math.random().toString(36).substring(2, 8).toUpperCase()}`
                      )
                    }
                    className="text-[11px] text-emerald-700 hover:underline font-medium"
                  >
                    Gerar ID P2P Simulado
                  </button>
                )}
              </div>
              <Input
                value={cloudP2pId}
                disabled={isCompleted}
                onChange={(e) => setCloudP2pIdDraft(e.target.value)}
                placeholder="Ex.: ITB-P2P-MHDX-9A8B7C"
                className="h-8 text-xs font-mono"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Notas de Campo do Técnico</Label>
              <Input
                value={fieldNotes}
                disabled={isCompleted}
                onChange={(e) => setFieldNotesDraft(e.target.value)}
                placeholder="Ex.: DVR instalado no rack da portaria com nobreak..."
                className="h-8 text-xs"
              />
            </div>

            {!isCompleted && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={checklistMutation.isPending}
                onClick={() =>
                  checklistMutation.mutate({
                    cloud_p2p_id: cloudP2pId.trim() || null,
                    notes: fieldNotes.trim() || null,
                  })
                }
                className="w-full"
              >
                Salvar P2P ID & Observações
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Section 4: Hardware Serial Number Vault */}
      <Card className="border-emerald-200">
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <ShieldCheck className="size-5 text-emerald-600" />
                4. Cofre de Números de Série & Rastreabilidade de Garantia
                (Serial Vault)
              </CardTitle>
              <CardDescription className="text-xs">
                Todos os DVRs, HDs WD Purple e Câmeras exigem registro do Número
                de Série físico vinculado ao canal/slot antes da conclusão da
                O.S.
              </CardDescription>
            </div>

            {!isCompleted && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleSimulateBarcodeScan}
                className="border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100 gap-1.5"
              >
                <ScanBarcode className="size-4" />
                Simular Leitura Código de Barras (Próximo Pendente)
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Required Serials Progress Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {wo.required_serials_summary.map((reqItem) => (
              <div
                key={reqItem.catalog_item_id}
                className={`rounded-xl border p-3 text-xs space-y-1 ${
                  reqItem.is_satisfied
                    ? "bg-emerald-50/60 border-emerald-200"
                    : "bg-amber-50/60 border-amber-300"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-bold text-slate-900">
                    {reqItem.sku}
                  </span>
                  <Badge
                    variant="outline"
                    className={
                      reqItem.is_satisfied
                        ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                        : "bg-amber-100 text-amber-900 border-amber-300"
                    }
                  >
                    {reqItem.registered_quantity} / {reqItem.required_quantity}{" "}
                    S/N
                  </Badge>
                </div>
                <p className="text-slate-700 font-medium truncate">
                  {reqItem.name_pt_br}
                </p>
              </div>
            ))}
          </div>

          {/* Serial Registration Form */}
          {!isCompleted && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
              <div className="sm:col-span-5 space-y-1">
                <Label className="text-xs">Equipamento (SKU)</Label>
                <select
                  value={activeCatalogItemId}
                  onChange={(e) => {
                    const id = e.target.value;
                    setSelectedCatalogItemId(id);
                    const found = wo.required_serials_summary.find(
                      (r) => r.catalog_item_id === id
                    );
                    if (found) {
                      setChannelLabelDraft(
                        suggestChannelLabel(
                          found,
                          found.registered_quantity + 1
                        )
                      );
                    }
                  }}
                  className="w-full h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium"
                >
                  {wo.required_serials_summary.map((r) => (
                    <option key={r.catalog_item_id} value={r.catalog_item_id}>
                      [{r.sku}] {r.name_pt_br} ({r.registered_quantity}/
                      {r.required_quantity})
                    </option>
                  ))}
                </select>
              </div>

              <div className="sm:col-span-3 space-y-1">
                <Label className="text-xs">Número de Série (S/N)</Label>
                <Input
                  value={serialNumberInput}
                  onChange={(e) => setSerialNumberInput(e.target.value)}
                  placeholder="Ex.: ITB-MHDX1108-98F2A"
                  className="h-9 bg-white text-xs font-mono"
                />
              </div>

              <div className="sm:col-span-2 space-y-1">
                <Label className="text-xs">Canal / Slot</Label>
                <Input
                  value={channelLabelInput}
                  onChange={(e) => setChannelLabelDraft(e.target.value)}
                  placeholder="Ex.: BNC-01 / SATA-01"
                  className="h-9 bg-white text-xs font-mono"
                />
              </div>

              <div className="sm:col-span-2">
                <Button
                  type="button"
                  disabled={
                    registerSerialMutation.isPending ||
                    !activeCatalogItemId ||
                    serialNumberInput.trim().length < 3 ||
                    channelLabelInput.trim().length < 1
                  }
                  onClick={() => registerSerialMutation.mutate()}
                  className="w-full h-9 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs"
                >
                  Registrar S/N
                </Button>
              </div>
            </div>
          )}

          {/* Registered Serials Table */}
          {wo.installed_serials.length > 0 && (
            <div className="rounded-lg border border-slate-200 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50">
                    <TableHead>Número de Série (S/N)</TableHead>
                    <TableHead>Canal / Slot</TableHead>
                    <TableHead>Equipamento</TableHead>
                    <TableHead>Categoria</TableHead>
                    <TableHead>Garantia Cliente (12m)</TableHead>
                    <TableHead>Garantia Distribuidor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {wo.installed_serials.map((sn) => (
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
                      <TableCell className="text-xs text-slate-500">
                        {formatDatePtBr(sn.distributor_warranty_until)}
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
