import type {
  CatalogCategory,
  QuoteStatus,
  UserRole,
  WorkOrderStatus,
} from "@/types/api";

const brlFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
});

/**
 * Format exact integer centavos (`_cents`) into a `pt-BR` BRL string (`R$ 1.499,90`).
 */
export function formatCentsToBrl(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) {
    return "R$ 0,00";
  }
  return brlFormatter.format(cents / 100);
}

/**
 * Format ISO timestamp into `dd/mm/aaaa, hh:mm` in `pt-BR`.
 */
export function formatDateTimePtBr(isoString: string | null | undefined): string {
  if (!isoString) {
    return "—";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return dateTimeFormatter.format(date);
}

/**
 * Format ISO date (`YYYY-MM-DD` or full ISO string) into `dd/mm/aaaa` in `pt-BR`.
 */
export function formatDatePtBr(dateString: string | null | undefined): string {
  if (!dateString) {
    return "—";
  }
  const normalized =
    dateString.length === 10 ? `${dateString}T12:00:00Z` : dateString;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return dateString;
  }
  return dateFormatter.format(date);
}

export const CATEGORY_LABELS_PT_BR: Readonly<Record<CatalogCategory, string>> = {
  DVR: "Gravador DVR / NVR",
  CAMERA_ANALOG: "Câmera Multi-HD (Analógica)",
  CAMERA_IP: "Câmera IP PoE",
  HDD: "HD de Vigilância (WD Purple)",
  POWER_SUPPLY: "Fonte de Alimentação 12V",
  POE_SWITCH: "Switch PoE",
  CABLE: "Cabeamento (UTP / Coaxial)",
  BALUN: "Vídeo Balun",
  CONNECTOR: "Conector (BNC / P4 / RJ45)",
  ACCESSORY: "Acessório / Caixa VBOX",
  SERVICE_LABOR: "Mão de Obra / Instalação",
};

export const QUOTE_STATUS_LABELS_PT_BR: Readonly<Record<QuoteStatus, string>> = {
  DRAFT: "Rascunho",
  SENT: "Enviado ao Cliente",
  APPROVED: "Aprovado (Estoque Reservado)",
  IN_PROGRESS: "Em Execução no Campo",
  COMPLETED: "Concluído & Garantido",
  CANCELED: "Cancelado",
  EXPIRED: "Expirado",
};

export const WORK_ORDER_STATUS_LABELS_PT_BR: Readonly<
  Record<WorkOrderStatus, string>
> = {
  PENDING: "Pendente de Agendamento",
  SCHEDULED: "Agendada",
  IN_FIELD: "Em Campo (Execução)",
  COMPLETED: "Concluída",
};

export const ROLE_LABELS_PT_BR: Readonly<Record<UserRole, string>> = {
  OWNER: "Proprietário / Gestor (Owner)",
  TECHNICIAN: "Técnico de Campo",
  PUBLIC_CLIENT: "Visão Pública do Cliente",
};
