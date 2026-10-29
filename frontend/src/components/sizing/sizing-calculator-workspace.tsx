"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  Bolt,
  Calculator,
  CheckCircle2,
  Cpu,
  FilePlus2,
  HardDrive,
  Network,
  Plus,
  Sparkles,
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
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  SIZING_DRAFT_STORAGE_KEY,
  quotesApi,
  sizingApi,
  toastProblemError,
} from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { CATEGORY_LABELS_PT_BR, formatCentsToBrl } from "@/lib/formatters";
import {
  type CablingMode,
  type CameraGroupRequest,
  type CameraTechnology,
  type Codec,
  type Fps,
  type Resolution,
  type SizingCalculateResponse,
  isSizingBomOwnerLine,
  isSizingOwnerResponse,
} from "@/types/api";

const INITIAL_GROUPS: CameraGroupRequest[] = [
  {
    group_label: "Perímetro Externo (Analógico Multi-HD)",
    technology: "ANALOG",
    count: 6,
    resolution: "1080p",
    fps: 20,
    codec: "H.265+",
    retention_days: 15,
    recording_hours_per_day: 24,
    cabling_mode: "BALUN_UTP",
    average_cable_meters: 40,
    form_factor: "BULLET",
  },
  {
    group_label: "Portaria & Hall Social (IP PoE)",
    technology: "IP",
    count: 2,
    resolution: "4MP",
    fps: 30,
    codec: "H.265+",
    retention_days: 15,
    recording_hours_per_day: 24,
    cabling_mode: "BALUN_UTP",
    average_cable_meters: 35,
    form_factor: "DOME",
  },
];

export interface SizingDraftSnapshot {
  readonly camera_groups: readonly CameraGroupRequest[];
  readonly calculation: SizingCalculateResponse;
  readonly saved_at: string;
}

export function SizingCalculatorWorkspace({
  mode = "standalone",
}: {
  readonly mode?: "standalone" | "quote-builder";
}): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isOwner = user?.role === "OWNER";

  const [groups, setGroups] = useState<CameraGroupRequest[]>(INITIAL_GROUPS);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  const [validDays, setValidDays] = useState<number>(15);
  const [calculationResult, setCalculationResult] =
    useState<SizingCalculateResponse | null>(null);

  const customersQuery = useQuery({
    queryKey: ["customers"],
    queryFn: () => quotesApi.listCustomers(),
    enabled: Boolean(user),
  });

  const activeCustomerId =
    selectedCustomerId || customersQuery.data?.[0]?.id || "";

  const calculateMutation = useMutation({
    mutationFn: (cameraGroups: readonly CameraGroupRequest[]) =>
      sizingApi.calculate({ camera_groups: cameraGroups }),
    onSuccess: (data) => {
      setCalculationResult(data);
    },
    onError: (err) => {
      toastProblemError(err, "Erro no cálculo de dimensionamento CFTV");
    },
  });

  const initialCalcTriggered = useRef(false);
  useEffect(() => {
    if (user && !initialCalcTriggered.current) {
      initialCalcTriggered.current = true;
      calculateMutation.mutate(INITIAL_GROUPS);
    }
  }, [user, calculateMutation]);

  const createQuoteMutation = useMutation({
    mutationFn: async () => {
      if (!calculationResult) {
        throw new Error("Execute o dimensionamento antes de criar o orçamento.");
      }
      if (!activeCustomerId) {
        throw new Error("Selecione um cliente para emitir o orçamento.");
      }
      return quotesApi.create({
        customer_id: activeCustomerId,
        valid_days: validDays,
        sizing_input_json: {
          camera_groups: groups,
          topology: calculationResult.topology,
          storage: calculationResult.storage,
          electrical: calculationResult.electrical,
        },
        items: calculationResult.bom_items.map((item) => ({
          catalog_item_id: item.catalog_item_id,
          quantity: item.quantity,
          unit_sale_cents: item.unit_sale_cents,
          is_auto_derived: item.is_auto_derived,
        })),
      });
    },
    onSuccess: async (createdQuote) => {
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      toast.success("Orçamento Comercial criado com sucesso!", {
        description: `Proposta para ${createdQuote.customer.name} no valor de ${formatCentsToBrl(createdQuote.total_sale_cents)}.`,
      });
      router.push(`/quotes/${createdQuote.id}`);
    },
    onError: (err) => {
      toastProblemError(err, "Falha ao criar orçamento a partir do dimensionamento");
    },
  });

  const handleOpenInQuoteBuilder = (): void => {
    if (!calculationResult) return;
    const snapshot: SizingDraftSnapshot = {
      camera_groups: groups,
      calculation: calculationResult,
      saved_at: new Date().toISOString(),
    };
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        SIZING_DRAFT_STORAGE_KEY,
        JSON.stringify(snapshot)
      );
    }
    toast.info("Dimensionamento carregado no Construtor de Propostas");
    router.push("/quotes/new?from=sizing");
  };

  const updateGroup = <K extends keyof CameraGroupRequest>(
    index: number,
    field: K,
    value: CameraGroupRequest[K]
  ): void => {
    setGroups((prev) =>
      prev.map((item, idx) =>
        idx === index ? { ...item, [field]: value } : item
      )
    );
  };

  const addGroup = (): void => {
    setGroups((prev) => [
      ...prev,
      {
        group_label: `Grupo de Câmeras #${prev.length + 1}`,
        technology: "ANALOG",
        count: 4,
        resolution: "1080p",
        fps: 20,
        codec: "H.265+",
        retention_days: 15,
        recording_hours_per_day: 24,
        cabling_mode: "BALUN_UTP",
        average_cable_meters: 35,
        form_factor: "BULLET",
      },
    ]);
  };

  const removeGroup = (index: number): void => {
    if (groups.length <= 1) return;
    setGroups((prev) => prev.filter((_, idx) => idx !== index));
  };

  const applyPresetScenario = (preset: "hybrid_mhdx" | "voltage_drop" | "high_retention"): void => {
    let nextGroups: CameraGroupRequest[];
    if (preset === "hybrid_mhdx") {
      nextGroups = [
        {
          group_label: "Estacionamento & Muros (7x Analógicas BNC)",
          technology: "ANALOG",
          count: 7,
          resolution: "1080p",
          fps: 20,
          codec: "H.265+",
          retention_days: 15,
          recording_hours_per_day: 24,
          cabling_mode: "BALUN_UTP",
          average_cable_meters: 35,
          form_factor: "BULLET",
        },
        {
          group_label: "Acessos & Portaria (3x IP PoE c/ Conversão BNC->IP)",
          technology: "IP",
          count: 3,
          resolution: "1080p",
          fps: 30,
          codec: "H.265+",
          retention_days: 15,
          recording_hours_per_day: 24,
          cabling_mode: "BALUN_UTP",
          average_cable_meters: 40,
          form_factor: "DOME",
        },
      ];
    } else if (preset === "voltage_drop") {
      nextGroups = [
        {
          group_label: "Galpão Logístico Distante (Cabo UTP 135m -> Alerta < 10.8V)",
          technology: "ANALOG",
          count: 8,
          resolution: "4MP",
          fps: 20,
          codec: "H.265+",
          retention_days: 15,
          recording_hours_per_day: 24,
          cabling_mode: "BALUN_UTP",
          average_cable_meters: 135,
          form_factor: "BULLET",
        },
      ];
    } else {
      nextGroups = [
        {
          group_label: "CFTV Industrial 4MP Alta Retenção (30 Dias -> 2 SATA)",
          technology: "ANALOG",
          count: 14,
          resolution: "4MP",
          fps: 30,
          codec: "H.265",
          retention_days: 30,
          recording_hours_per_day: 24,
          cabling_mode: "COAXIAL",
          average_cable_meters: 45,
          form_factor: "BULLET",
        },
      ];
    }
    setGroups(nextGroups);
    calculateMutation.mutate(nextGroups);
  };

  return (
    <div className="space-y-6">
      {/* Header & Presets */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {mode === "quote-builder"
              ? "Construtor de Proposta & Dimensionamento CFTV"
              : "Motor de Dimensionamento Técnico CFTV"}
          </h1>
          <p className="text-sm text-slate-600">
            Cálculo determinístico de armazenamento WD Purple, topologia híbrida
            Intelbras MHDX (conversão BNC→IP), carga elétrica 12V/PoE, queda de
            tensão em cobre e derivação automática de acessórios (BOM).
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-slate-500 mr-1 flex items-center gap-1">
            <Sparkles className="size-3.5 text-emerald-600" />
            Cenários Rápidos:
          </span>
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => applyPresetScenario("hybrid_mhdx")}
          >
            7 BNC + 3 IP (MHDX 1108 Híbrido)
          </Button>
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => applyPresetScenario("voltage_drop")}
          >
            Lance 135m (Alerta Queda de Tensão)
          </Button>
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => applyPresetScenario("high_retention")}
          >
            14x 4MP 30 Dias (Upgrade 2 SATA)
          </Button>
        </div>
      </div>

      {/* Camera Groups Builder */}
      <Card>
        <CardHeader className="pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base font-bold">
              1. Grupos de Câmeras & Parâmetros de Gravação
            </CardTitle>
            <CardDescription className="text-xs">
              Configure a tecnologia (Analógica Multi-HD ou IP PoE), resolução,
              taxa de quadros, codec H.265+, dias de retenção e metragem média de
              cabo.
            </CardDescription>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={addGroup}
              className="gap-1"
            >
              <Plus className="size-4" />
              Adicionar Grupo
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={calculateMutation.isPending}
              onClick={() => calculateMutation.mutate(groups)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
            >
              <Calculator className="size-4" />
              {calculateMutation.isPending
                ? "Calculando..."
                : "Recalcular Engenharia & BOM"}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {groups.map((group, idx) => (
            <div
              key={idx}
              className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 flex-1 min-w-[240px]">
                  <Badge className="bg-slate-900 text-white">
                    Grupo #{idx + 1}
                  </Badge>
                  <Input
                    value={group.group_label}
                    onChange={(e) =>
                      updateGroup(idx, "group_label", e.target.value)
                    }
                    className="h-8 bg-white font-medium text-sm max-w-md"
                    placeholder="Identificação do grupo de câmeras"
                  />
                </div>

                {groups.length > 1 && (
                  <Button
                    type="button"
                    size="xs"
                    variant="destructive"
                    onClick={() => removeGroup(idx)}
                  >
                    <Trash2 className="size-3.5 mr-1" />
                    Remover
                  </Button>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Tecnologia</Label>
                  <select
                    value={group.technology}
                    onChange={(e) =>
                      updateGroup(
                        idx,
                        "technology",
                        e.target.value as CameraTechnology
                      )
                    }
                    className="w-full h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-medium"
                  >
                    <option value="ANALOG">Analógica (BNC)</option>
                    <option value="IP">IP (PoE RJ45)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Qtd. Câmeras</Label>
                  <Input
                    type="number"
                    min={1}
                    max={64}
                    value={group.count}
                    onChange={(e) =>
                      updateGroup(
                        idx,
                        "count",
                        Math.max(1, Number(e.target.value) || 1)
                      )
                    }
                    className="h-8 bg-white text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Resolução</Label>
                  <select
                    value={group.resolution}
                    onChange={(e) =>
                      updateGroup(
                        idx,
                        "resolution",
                        e.target.value as Resolution
                      )
                    }
                    className="w-full h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-medium"
                  >
                    <option value="720p">720p (1 MP)</option>
                    <option value="1080p">1080p (2 MP Full HD)</option>
                    <option value="4MP">4MP (2K Quad HD)</option>
                    <option value="4K">4K (8 MP Ultra HD)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">FPS</Label>
                  <select
                    value={group.fps}
                    onChange={(e) =>
                      updateGroup(idx, "fps", Number(e.target.value) as Fps)
                    }
                    className="w-full h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-medium"
                  >
                    <option value={15}>15 FPS</option>
                    <option value={20}>20 FPS</option>
                    <option value={30}>30 FPS</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Codec</Label>
                  <select
                    value={group.codec}
                    onChange={(e) =>
                      updateGroup(idx, "codec", e.target.value as Codec)
                    }
                    className="w-full h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-medium"
                  >
                    <option value="H.265+">H.265+ Smart Codec</option>
                    <option value="H.265">H.265 Padrao</option>
                    <option value="H.264">H.264 Legado</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Retenção (Dias)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={365}
                    value={group.retention_days}
                    onChange={(e) =>
                      updateGroup(
                        idx,
                        "retention_days",
                        Math.max(1, Number(e.target.value) || 1)
                      )
                    }
                    className="h-8 bg-white text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Cabeamento</Label>
                  <select
                    value={group.cabling_mode}
                    onChange={(e) =>
                      updateGroup(
                        idx,
                        "cabling_mode",
                        e.target.value as CablingMode
                      )
                    }
                    disabled={group.technology === "IP"}
                    className="w-full h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs font-medium disabled:opacity-60"
                  >
                    <option value="BALUN_UTP">UTP Cat5e + Balun</option>
                    <option value="COAXIAL">Coaxial Bipolar 4mm</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Distância Média (m)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={500}
                    value={group.average_cable_meters}
                    onChange={(e) =>
                      updateGroup(
                        idx,
                        "average_cable_meters",
                        Math.max(1, Number(e.target.value) || 1)
                      )
                    }
                    className="h-8 bg-white text-xs"
                  />
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Engineering Results */}
      {calculationResult && (
        <>
          {/* Voltage Drop Warning Banner */}
          {calculationResult.electrical.voltage_drop_warnings.length > 0 && (
            <Card className="border-red-300 bg-red-50/70">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold text-red-900 flex items-center gap-2">
                  <AlertTriangle className="size-4 text-red-600" />
                  Alerta de Engenharia: Queda de Tensão Crítica Detectada (
                  {"< 10.8V DC"})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {calculationResult.electrical.voltage_drop_warnings.map(
                  (warn, i) => (
                    <div
                      key={i}
                      className="rounded-lg bg-white border border-red-200 p-3 text-xs space-y-1"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <strong className="text-red-900">
                          {warn.group_label} ({warn.distance_meters}m •{" "}
                          {warn.cabling_mode})
                        </strong>
                        <Badge variant="destructive">
                          Tensão na Câmera: {warn.voltage_at_load_volts.toFixed(2)}V
                          (Queda ΔV = {warn.voltage_drop_volts.toFixed(2)}V)
                        </Badge>
                      </div>
                      <p className="text-slate-700">{warn.recommendation_pt_br}</p>
                    </div>
                  )
                )}
              </CardContent>
            </Card>
          )}

          {/* 3-Card Technical Summary: Topology, Storage, Electrical */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Topology Card */}
            <Card className="border-emerald-200">
              <CardHeader className="pb-2">
                <CardDescription className="flex items-center justify-between text-xs">
                  <span>Topologia Intelbras MHDX / NVR</span>
                  <Cpu className="size-4 text-emerald-600" />
                </CardDescription>
                <CardTitle className="text-lg font-bold text-slate-900">
                  Gravador: {calculationResult.topology.selected_recorder_sku}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2.5 text-xs">
                <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-emerald-600 h-full transition-all"
                    style={{
                      width: `${Math.min(
                        100,
                        calculationResult.topology.channel_utilization_percent
                      )}%`,
                    }}
                  />
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>
                    Ocupação: {calculationResult.topology.total_cameras_count} /{" "}
                    {calculationResult.topology.total_supported_channels} canais
                  </span>
                  <span className="font-semibold text-emerald-700">
                    {calculationResult.topology.channel_utilization_percent.toFixed(
                      0
                    )}
                    %
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-1 text-slate-700">
                  <div className="rounded bg-slate-100 p-2">
                    <span className="block text-[10px] text-slate-500">
                      Portas BNC Usadas
                    </span>
                    <strong>
                      {calculationResult.topology.bnc_channels_used_by_analog} /{" "}
                      {calculationResult.topology.native_bnc_channels}
                    </strong>
                  </div>
                  <div className="rounded bg-emerald-50 p-2">
                    <span className="block text-[10px] text-emerald-700">
                      BNC Convertidos p/ IP
                    </span>
                    <strong className="text-emerald-900">
                      {calculationResult.topology.bnc_channels_converted_to_ip}{" "}
                      canal(is)
                    </strong>
                  </div>
                </div>
                <p className="text-slate-500">
                  Banda de Entrada:{" "}
                  <strong>
                    {calculationResult.topology.total_incoming_bandwidth_mbps.toFixed(
                      1
                    )}{" "}
                    Mbps
                  </strong>{" "}
                  (Máx: {calculationResult.topology.max_incoming_bandwidth_mbps}{" "}
                  Mbps)
                </p>
              </CardContent>
            </Card>

            {/* Storage Card */}
            <Card className="border-sky-200">
              <CardHeader className="pb-2">
                <CardDescription className="flex items-center justify-between text-xs">
                  <span>Armazenamento 24x7 (WD Purple)</span>
                  <HardDrive className="size-4 text-sky-600" />
                </CardDescription>
                <CardTitle className="text-lg font-bold text-slate-900">
                  {calculationResult.storage.total_selected_tb} TB Alocados (
                  {calculationResult.storage.sata_slots_used}x SATA)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-slate-700">
                <div className="flex justify-between">
                  <span>Volume Bruto de Vídeo:</span>
                  <strong>
                    {calculationResult.storage.raw_retention_gb.toFixed(1)} GB
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span>Com Margem de Formatação (+15%):</span>
                  <strong>
                    {calculationResult.storage.total_required_gb_with_margin.toFixed(
                      1
                    )}{" "}
                    GB ({calculationResult.storage.required_nominal_tb} TB
                    nominal)
                  </strong>
                </div>
                <div className="pt-1 space-y-1">
                  {calculationResult.storage.selected_hdds.map((hdd) => (
                    <div
                      key={hdd.sku}
                      className="flex items-center justify-between rounded bg-sky-50 px-2.5 py-1.5 text-sky-950"
                    >
                      <span className="font-medium">
                        {hdd.quantity}x {hdd.sku} ({hdd.capacity_tb}TB)
                      </span>
                      <strong>
                        {formatCentsToBrl(hdd.total_sale_price_cents)}
                      </strong>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Electrical & Cabling Card */}
            <Card className="border-amber-200">
              <CardHeader className="pb-2">
                <CardDescription className="flex items-center justify-between text-xs">
                  <span>Carga Elétrica 12V / PoE & Cabos</span>
                  <Bolt className="size-4 text-amber-600" />
                </CardDescription>
                <CardTitle className="text-lg font-bold text-slate-900">
                  {calculationResult.electrical.analog_required_current_amps_with_headroom.toFixed(
                    2
                  )}{" "}
                  A (12V) •{" "}
                  {calculationResult.electrical.ip_required_poe_watts_with_headroom.toFixed(
                    1
                  )}{" "}
                  W (PoE)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-slate-700">
                <div className="flex justify-between">
                  <span>Corrente IR Ativo (+30% folga):</span>
                  <strong>
                    {calculationResult.electrical.analog_required_current_amps_with_headroom.toFixed(
                      2
                    )}{" "}
                    A
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span>Orçamento PoE (+25% folga):</span>
                  <strong>
                    {calculationResult.electrical.ip_required_poe_watts_with_headroom.toFixed(
                      1
                    )}{" "}
                    W
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span>Cabo UTP Cat5e (+15% folga):</span>
                  <strong>
                    {calculationResult.electrical.utp_cable_meters_with_slack}m (
                    {calculationResult.electrical.utp_cable_boxes_305m} cx 305m)
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span>Cabo Coaxial 4mm (+15% folga):</span>
                  <strong>
                    {
                      calculationResult.electrical
                        .coaxial_cable_meters_with_slack
                    }
                    m ({calculationResult.electrical.coaxial_cable_rolls_100m}{" "}
                    rl 100m)
                  </strong>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Auto-Derived BOM Table & 1-Click Proposal Creation */}
          <Card>
            <CardHeader className="pb-3 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div>
                <CardTitle className="text-base font-bold flex items-center gap-2">
                  <Network className="size-4 text-emerald-600" />
                  2. Lista de Materiais Auto-Derivada (BOM) & Fechamento Comercial
                </CardTitle>
                <CardDescription className="text-xs">
                  Inclui gravador, HDs WD Purple, câmeras, fontes MCM/switches
                  PoE, baluns XBP 502, conectores BNC/P4/RJ45, caixas VBOX 1100E,
                  cabos e pontos de mão de obra.
                </CardDescription>
              </div>

              {/* Financial Summary Banner */}
              <div className="flex flex-wrap items-center gap-3 bg-slate-900 text-white px-4 py-2.5 rounded-xl">
                {isSizingOwnerResponse(calculationResult) && (
                  <>
                    <div>
                      <span className="text-[10px] text-slate-400 block uppercase">
                        Custo Total (Owner)
                      </span>
                      <span className="text-sm font-semibold text-slate-200">
                        {formatCentsToBrl(calculationResult.total_cost_cents)}
                      </span>
                    </div>
                    <div className="h-6 w-px bg-slate-700" />
                    <div>
                      <span className="text-[10px] text-emerald-400 block uppercase">
                        Margem Bruta
                      </span>
                      <span className="text-sm font-bold text-emerald-400">
                        {Number(calculationResult.margin_percent).toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-6 w-px bg-slate-700" />
                  </>
                )}
                <div>
                  <span className="text-[10px] text-amber-300 block uppercase">
                    Preço Total de Venda
                  </span>
                  <span className="text-lg font-bold text-white">
                    {formatCentsToBrl(calculationResult.total_sale_cents)}
                  </span>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-6">
              <div className="rounded-lg border border-slate-200 overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50">
                      <TableHead>SKU</TableHead>
                      <TableHead>Equipamento / Material (PT-BR)</TableHead>
                      <TableHead>Categoria</TableHead>
                      <TableHead className="text-center">Estoque Disp.</TableHead>
                      <TableHead className="text-right">Qtd.</TableHead>
                      {isOwner && (
                        <TableHead className="text-right">Custo Unit.</TableHead>
                      )}
                      <TableHead className="text-right">Venda Unit.</TableHead>
                      <TableHead className="text-right">Subtotal Venda</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {calculationResult.bom_items.map((line) => (
                      <TableRow key={`${line.role}-${line.sku}`}>
                        <TableCell className="font-mono text-xs font-semibold">
                          {line.sku}
                        </TableCell>
                        <TableCell>
                          <div className="font-medium text-xs text-slate-900">
                            {line.name_pt_br}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            {line.notes_pt_br}
                          </div>
                        </TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className="text-[10px]">
                            {CATEGORY_LABELS_PT_BR[line.category]}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center text-xs">
                          <Badge
                            variant="outline"
                            className={
                              line.available_stock_quantity >= line.quantity
                                ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                : "bg-red-50 text-red-800 border-red-200"
                            }
                          >
                            {line.available_stock_quantity} un.
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-bold text-xs">
                          {line.quantity}
                        </TableCell>
                        {isOwner && (
                          <TableCell className="text-right text-xs text-slate-500">
                            {isSizingBomOwnerLine(line)
                              ? formatCentsToBrl(line.unit_cost_cents)
                              : "—"}
                          </TableCell>
                        )}
                        <TableCell className="text-right text-xs">
                          {formatCentsToBrl(line.unit_sale_cents)}
                        </TableCell>
                        <TableCell className="text-right font-semibold text-xs text-slate-900">
                          {formatCentsToBrl(line.line_total_sale_cents)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Action Bar: Create Quote from Sizing */}
              <div className="rounded-xl bg-emerald-50/70 border border-emerald-200 p-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 flex-1 max-w-xl">
                  <div className="space-y-1">
                    <Label className="text-xs font-semibold text-slate-800">
                      Cliente Destinatário da Proposta
                    </Label>
                    <select
                      value={activeCustomerId}
                      onChange={(e) => setSelectedCustomerId(e.target.value)}
                      className="w-full h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium"
                    >
                      {(customersQuery.data ?? []).map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} ({c.document_cpf_cnpj})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1">
                    <Label className="text-xs font-semibold text-slate-800">
                      Validade Comercial (Dias)
                    </Label>
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

                <div className="flex flex-wrap items-center gap-2">
                  {mode === "standalone" && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleOpenInQuoteBuilder}
                      className="gap-1.5"
                    >
                      <FilePlus2 className="size-4" />
                      Personalizar no Construtor (/quotes/new)
                    </Button>
                  )}

                  {isOwner ? (
                    <Button
                      type="button"
                      disabled={
                        createQuoteMutation.isPending || !activeCustomerId
                      }
                      onClick={() => createQuoteMutation.mutate()}
                      className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold gap-1.5 h-9"
                    >
                      <CheckCircle2 className="size-4" />
                      {createQuoteMutation.isPending
                        ? "Emitindo Orçamento..."
                        : "Criar Orçamento a partir do Dimensionamento"}
                    </Button>
                  ) : (
                    <Badge variant="outline" className="py-1.5 px-3">
                      Alterne para a persona Proprietário (Owner) no topo para
                      emitir propostas comerciais
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
