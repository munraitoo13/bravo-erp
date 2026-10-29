import { toast } from "sonner";
import type {
  AuthMeResponse,
  AuthTokenResponse,
  CatalogCategory,
  CatalogItemCreateRequest,
  CatalogItemOwnerResponse,
  CatalogItemResponse,
  CatalogItemUpdateRequest,
  CustomerCreateRequest,
  CustomerResponse,
  DemoAuthResponse,
  DemoLoginRequest,
  DemoResetResponse,
  DocumentVerificationResponse,
  ExpiringWarrantyItemResponse,
  InstalledSerialCreateRequest,
  InstalledSerialResponse,
  LoginRequest,
  ProblemDetailErrorItem,
  ProblemDetails,
  PublicQuoteApproveRequest,
  QuoteCreateRequest,
  QuoteOwnerResponse,
  QuotePublicResponse,
  QuoteResponse,
  QuoteStatus,
  SizingCalculateRequest,
  SizingCalculateResponse,
  WorkOrderChecklistUpdateRequest,
  WorkOrderCompleteRequest,
  WorkOrderPhotoJsonUploadRequest,
  WorkOrderResponse,
  WorkOrderStatus,
} from "@/types/api";

export const TOKEN_STORAGE_KEY = "bravo_erp_access_token";
export const DEMO_STATE_STORAGE_KEY = "bravo_erp_demo_metadata";
export const SIZING_DRAFT_STORAGE_KEY = "bravo_erp_sizing_draft";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export function generateCorrelationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `req_${crypto.randomUUID().replace(/-/g, "").slice(0, 20)}`;
  }
  const randomHex = Math.random().toString(16).slice(2, 14);
  return `req_${Date.now().toString(16)}${randomHex}`;
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredAccessToken(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

/**
 * Custom Error wrapping RFC 7807 Problem Details (`application/problem+json`).
 */
export class ApiProblemError extends Error {
  public readonly problem: ProblemDetails;
  public readonly status: number;
  public readonly correlationId: string;

  constructor(problem: ProblemDetails) {
    super(problem.detail || problem.title);
    this.name = "ApiProblemError";
    this.problem = problem;
    this.status = problem.status;
    this.correlationId = problem.correlation_id;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseProblemDetails(
  payload: unknown,
  fallbackStatus: number,
  fallbackCorrelationId: string,
  instancePath: string
): ProblemDetails {
  if (isRecord(payload)) {
    const type =
      typeof payload.type === "string" ? payload.type : "about:blank";
    const title =
      typeof payload.title === "string"
        ? payload.title
        : `Erro HTTP ${fallbackStatus}`;
    const status =
      typeof payload.status === "number" ? payload.status : fallbackStatus;
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : "Não foi possível processar a requisição no servidor.";
    const instance =
      typeof payload.instance === "string" ? payload.instance : instancePath;
    const correlationId =
      typeof payload.correlation_id === "string"
        ? payload.correlation_id
        : fallbackCorrelationId;

    const rawErrors = Array.isArray(payload.errors) ? payload.errors : [];
    const errors: ProblemDetailErrorItem[] = rawErrors
      .filter(isRecord)
      .map((item) => ({
        field: typeof item.field === "string" ? item.field : undefined,
        message: typeof item.message === "string" ? item.message : undefined,
        reason: typeof item.reason === "string" ? item.reason : undefined,
        type: typeof item.type === "string" ? item.type : undefined,
        catalog_item_id:
          typeof item.catalog_item_id === "string"
            ? item.catalog_item_id
            : undefined,
        sku: typeof item.sku === "string" ? item.sku : undefined,
        name_pt_br:
          typeof item.name_pt_br === "string" ? item.name_pt_br : undefined,
        available_quantity:
          typeof item.available_quantity === "number"
            ? item.available_quantity
            : undefined,
        requested_quantity:
          typeof item.requested_quantity === "number"
            ? item.requested_quantity
            : undefined,
      }));

    return {
      type,
      title,
      status,
      detail,
      instance,
      correlation_id: correlationId,
      errors: errors.length > 0 ? errors : undefined,
    };
  }

  return {
    type: "about:blank",
    title: `Erro HTTP ${fallbackStatus}`,
    status: fallbackStatus,
    detail: "Erro inesperado ao comunicar com a API do Bravo ERP.",
    instance: instancePath,
    correlation_id: fallbackCorrelationId,
  };
}

/**
 * Display a rich PT-BR toast notification formatted from an RFC 7807 `ApiProblemError`.
 */
export function toastProblemError(
  error: unknown,
  fallbackTitle = "Falha na operação"
): void {
  if (error instanceof ApiProblemError) {
    const { problem } = error;
    const extraLines: string[] = [];
    if (problem.errors && problem.errors.length > 0) {
      for (const errItem of problem.errors.slice(0, 3)) {
        if (
          errItem.sku &&
          errItem.available_quantity !== undefined &&
          errItem.requested_quantity !== undefined
        ) {
          extraLines.push(
            `SKU ${errItem.sku}: disponível ${errItem.available_quantity} un. (solicitado ${errItem.requested_quantity} un.)`
          );
        } else if (errItem.field && errItem.message) {
          extraLines.push(`${errItem.field}: ${errItem.message}`);
        } else if (errItem.reason) {
          extraLines.push(errItem.reason);
        }
      }
    }
    const descriptionParts = [
      problem.detail,
      ...extraLines,
      `Trace ID: ${problem.correlation_id}`,
    ];
    toast.error(`${problem.title} (HTTP ${problem.status})`, {
      description: descriptionParts.join(" | "),
      duration: 6000,
    });
    return;
  }

  const message =
    error instanceof Error
      ? error.message
      : "Erro de conexão com o servidor. Verifique se o backend está ativo.";
  toast.error(fallbackTitle, {
    description: message,
  });
}

interface RequestOptions {
  readonly method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  readonly body?: unknown;
  readonly headers?: Readonly<Record<string, string>>;
  readonly skipAuth?: boolean;
}

export async function apiRequest<TResponse>(
  path: string,
  options: RequestOptions = {}
): Promise<TResponse> {
  const correlationId = generateCorrelationId();
  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {
    Accept: "application/json, application/problem+json",
    "X-Correlation-ID": correlationId,
    ...(options.headers ?? {}),
  };

  if (!options.skipAuth) {
    const token = getStoredAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  let fetchBody: BodyInit | undefined;
  if (options.body instanceof FormData) {
    fetchBody = options.body;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    fetchBody = JSON.stringify(options.body);
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: fetchBody,
  });

  const echoedCorrelationId =
    response.headers.get("X-Correlation-ID") ?? correlationId;

  if (!response.ok) {
    let errorPayload: unknown = null;
    try {
      errorPayload = await response.json();
    } catch {
      errorPayload = null;
    }
    const problem = parseProblemDetails(
      errorPayload,
      response.status,
      echoedCorrelationId,
      path
    );
    throw new ApiProblemError(problem);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

/**
 * Typed Domain API Modules
 */
export const authApi = {
  login: (payload: LoginRequest): Promise<AuthTokenResponse> =>
    apiRequest<AuthTokenResponse>("/auth/login", {
      method: "POST",
      body: payload,
      skipAuth: true,
    }),

  demoLogin: (payload: DemoLoginRequest): Promise<DemoAuthResponse> =>
    apiRequest<DemoAuthResponse>("/auth/demo-login", {
      method: "POST",
      body: payload,
      skipAuth: true,
    }),

  demoReset: (): Promise<DemoResetResponse> =>
    apiRequest<DemoResetResponse>("/auth/demo-reset", {
      method: "POST",
    }),

  me: (): Promise<AuthMeResponse> => apiRequest<AuthMeResponse>("/auth/me"),
};

export const catalogApi = {
  list: (category?: CatalogCategory): Promise<CatalogItemResponse[]> => {
    const query = category ? `?category=${encodeURIComponent(category)}` : "";
    return apiRequest<CatalogItemResponse[]>(`/catalog${query}`);
  },

  create: (
    payload: CatalogItemCreateRequest
  ): Promise<CatalogItemOwnerResponse> =>
    apiRequest<CatalogItemOwnerResponse>("/catalog", {
      method: "POST",
      body: payload,
    }),

  update: (
    itemId: string,
    payload: CatalogItemUpdateRequest
  ): Promise<CatalogItemOwnerResponse> =>
    apiRequest<CatalogItemOwnerResponse>(`/catalog/${itemId}`, {
      method: "PATCH",
      body: payload,
    }),

  delete: (itemId: string): Promise<void> =>
    apiRequest<void>(`/catalog/${itemId}`, {
      method: "DELETE",
    }),
};

export const sizingApi = {
  calculate: (
    payload: SizingCalculateRequest
  ): Promise<SizingCalculateResponse> =>
    apiRequest<SizingCalculateResponse>("/sizing/calculate", {
      method: "POST",
      body: payload,
    }),
};

export const quotesApi = {
  listCustomers: (): Promise<CustomerResponse[]> =>
    apiRequest<CustomerResponse[]>("/customers"),

  createCustomer: (payload: CustomerCreateRequest): Promise<CustomerResponse> =>
    apiRequest<CustomerResponse>("/customers", {
      method: "POST",
      body: payload,
    }),

  list: (status?: QuoteStatus): Promise<QuoteResponse[]> => {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiRequest<QuoteResponse[]>(`/quotes${query}`);
  },

  getById: (quoteId: string): Promise<QuoteResponse> =>
    apiRequest<QuoteResponse>(`/quotes/${quoteId}`),

  create: (payload: QuoteCreateRequest): Promise<QuoteOwnerResponse> =>
    apiRequest<QuoteOwnerResponse>("/quotes", {
      method: "POST",
      body: payload,
    }),

  send: (quoteId: string): Promise<QuoteOwnerResponse> =>
    apiRequest<QuoteOwnerResponse>(`/quotes/${quoteId}/send`, {
      method: "POST",
    }),

  approveByOwner: (quoteId: string): Promise<QuoteOwnerResponse> =>
    apiRequest<QuoteOwnerResponse>(`/quotes/${quoteId}/approve`, {
      method: "POST",
    }),

  cancel: (quoteId: string): Promise<QuoteOwnerResponse> =>
    apiRequest<QuoteOwnerResponse>(`/quotes/${quoteId}/cancel`, {
      method: "POST",
    }),

  getPublicQuote: (publicToken: string): Promise<QuotePublicResponse> =>
    apiRequest<QuotePublicResponse>(`/public/quotes/${publicToken}`, {
      skipAuth: true,
    }),

  approvePublicQuote: (
    publicToken: string,
    payload?: PublicQuoteApproveRequest
  ): Promise<QuotePublicResponse> =>
    apiRequest<QuotePublicResponse>(`/public/quotes/${publicToken}/approve`, {
      method: "POST",
      body: payload ?? { accepted_terms: true },
      skipAuth: true,
    }),
};

export const workOrdersApi = {
  list: (status?: WorkOrderStatus): Promise<WorkOrderResponse[]> => {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return apiRequest<WorkOrderResponse[]>(`/work-orders${query}`);
  },

  getById: (workOrderId: string): Promise<WorkOrderResponse> =>
    apiRequest<WorkOrderResponse>(`/work-orders/${workOrderId}`),

  start: (
    workOrderId: string,
    notes?: string
  ): Promise<WorkOrderResponse> =>
    apiRequest<WorkOrderResponse>(`/work-orders/${workOrderId}/start`, {
      method: "POST",
      body: notes ? { notes } : {},
    }),

  updateChecklist: (
    workOrderId: string,
    payload: WorkOrderChecklistUpdateRequest
  ): Promise<WorkOrderResponse> =>
    apiRequest<WorkOrderResponse>(`/work-orders/${workOrderId}/checklist`, {
      method: "PATCH",
      body: payload,
    }),

  uploadPhotoJson: (
    workOrderId: string,
    payload: WorkOrderPhotoJsonUploadRequest
  ): Promise<WorkOrderResponse> =>
    apiRequest<WorkOrderResponse>(`/work-orders/${workOrderId}/photos`, {
      method: "POST",
      body: payload,
    }),

  uploadPhotoFile: (
    workOrderId: string,
    file: File
  ): Promise<WorkOrderResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<WorkOrderResponse>(`/work-orders/${workOrderId}/photos`, {
      method: "POST",
      body: formData,
    });
  },

  registerSerial: (
    workOrderId: string,
    payload: InstalledSerialCreateRequest
  ): Promise<InstalledSerialResponse> =>
    apiRequest<InstalledSerialResponse>(`/work-orders/${workOrderId}/serials`, {
      method: "POST",
      body: payload,
    }),

  complete: (
    workOrderId: string,
    payload?: WorkOrderCompleteRequest
  ): Promise<WorkOrderResponse> =>
    apiRequest<WorkOrderResponse>(`/work-orders/${workOrderId}/complete`, {
      method: "POST",
      body: payload ?? {},
    }),

  listExpiringWarranties: (): Promise<ExpiringWarrantyItemResponse[]> =>
    apiRequest<ExpiringWarrantyItemResponse[]>("/warranties/expiring"),

  verifyBySha256: (
    pdfSha256Hash: string
  ): Promise<DocumentVerificationResponse> =>
    apiRequest<DocumentVerificationResponse>(`/verify/${pdfSha256Hash}`, {
      skipAuth: true,
    }),
};
