/**
 * Strict TypeScript domain & API contracts matching backend Pydantic v2 schemas.
 * Zero `any` types permitted. All monetary values are integer centavos (`_cents`).
 */

export type UserRole = "OWNER" | "TECHNICIAN" | "PUBLIC_CLIENT";

export type CatalogCategory =
  | "DVR"
  | "CAMERA_ANALOG"
  | "CAMERA_IP"
  | "HDD"
  | "POWER_SUPPLY"
  | "POE_SWITCH"
  | "CABLE"
  | "BALUN"
  | "CONNECTOR"
  | "ACCESSORY"
  | "SERVICE_LABOR";

export type QuoteStatus =
  | "DRAFT"
  | "SENT"
  | "APPROVED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELED"
  | "EXPIRED";

export type WorkOrderStatus =
  | "PENDING"
  | "SCHEDULED"
  | "IN_FIELD"
  | "COMPLETED"
  | "CANCELED";

export type CameraTechnology = "ANALOG" | "IP";
export type Resolution = "720p" | "1080p" | "4MP" | "4K";
export type Fps = 15 | 20 | 30;
export type Codec = "H.264" | "H.265" | "H.265+";
export type CablingMode = "BALUN_UTP" | "COAXIAL";
export type FormFactor = "BULLET" | "DOME" | "SPEED_DOME";

export type BomRole =
  | "RECORDER"
  | "HDD"
  | "CAMERA_ANALOG"
  | "CAMERA_IP"
  | "POWER_SUPPLY"
  | "POE_SWITCH"
  | "CABLE_COAXIAL"
  | "CABLE_UTP"
  | "BALUN"
  | "CONNECTOR_BNC"
  | "CONNECTOR_P4"
  | "CONNECTOR_RJ45"
  | "JUNCTION_BOX"
  | "SERVICE_LABOR";

/**
 * RFC 7807 Problem Details contract returned by FastAPI exception handlers.
 */
export interface ProblemDetailErrorItem {
  readonly field?: string;
  readonly message?: string;
  readonly reason?: string;
  readonly type?: string;
  readonly catalog_item_id?: string;
  readonly sku?: string;
  readonly name_pt_br?: string;
  readonly available_quantity?: number;
  readonly requested_quantity?: number;
}

export interface ProblemDetails {
  readonly type: string;
  readonly title: string;
  readonly status: number;
  readonly detail: string;
  readonly instance: string;
  readonly correlation_id: string;
  readonly errors?: readonly ProblemDetailErrorItem[];
}

/**
 * Tenants & Authentication DTOs
 */
export interface OrganizationResponse {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly document_cnpj: string;
  readonly is_demo: boolean;
  readonly created_at: string;
}

export interface UserResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly email: string;
  readonly full_name: string;
  readonly role: UserRole;
  readonly is_active: boolean;
  readonly created_at: string;
}

export interface LoginRequest {
  readonly email: string;
  readonly password: string;
  readonly organization_slug?: string | null;
}

export interface AuthTokenResponse {
  readonly access_token: string;
  readonly token_type: "bearer";
  readonly persona: UserRole;
  readonly user: UserResponse;
  readonly organization: OrganizationResponse;
}

export interface DemoLoginRequest {
  readonly persona: UserRole;
}

export interface DemoAuthResponse {
  readonly persona: UserRole;
  readonly access_token: string | null;
  readonly token_type: "bearer";
  readonly user: UserResponse | null;
  readonly organization: OrganizationResponse;
  readonly demo_public_quote_token: string;
  readonly demo_active_work_order_id: string;
  readonly redirect_path: string;
}

export interface DemoResetResponse {
  readonly status: "reset_completed";
  readonly organization_id: string;
  readonly catalog_items_restored: number;
  readonly quotes_restored: number;
  readonly demo_public_quote_token: string;
  readonly demo_active_work_order_id: string;
}

export interface AuthMeResponse {
  readonly user: UserResponse;
  readonly organization: OrganizationResponse;
}

/**
 * Equipment Catalog DTOs (Role-Segregated)
 */
export interface CatalogItemTechnicianResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly sku: string;
  readonly name_pt_br: string;
  readonly category: CatalogCategory;
  readonly brand: string;
  readonly sale_price_cents: number;
  readonly stock_quantity: number;
  readonly reserved_quantity: number;
  readonly available_quantity: number;
  readonly specs: Readonly<Record<string, unknown>>;
  readonly is_seed_protected: boolean;
  readonly is_active: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CatalogItemOwnerResponse extends CatalogItemTechnicianResponse {
  readonly cost_price_cents: number;
}

export type CatalogItemResponse =
  | CatalogItemOwnerResponse
  | CatalogItemTechnicianResponse;

export function isCatalogOwnerItem(
  item: CatalogItemResponse
): item is CatalogItemOwnerResponse {
  return "cost_price_cents" in item && typeof item.cost_price_cents === "number";
}

export interface CatalogItemCreateRequest {
  readonly sku: string;
  readonly name_pt_br: string;
  readonly category: CatalogCategory;
  readonly brand: string;
  readonly cost_price_cents: number;
  readonly sale_price_cents: number;
  readonly stock_quantity: number;
  readonly specs: Readonly<Record<string, unknown>>;
  readonly is_active?: boolean;
}

export interface CatalogItemUpdateRequest {
  readonly name_pt_br?: string;
  readonly brand?: string;
  readonly cost_price_cents?: number;
  readonly sale_price_cents?: number;
  readonly stock_quantity?: number;
  readonly specs?: Readonly<Record<string, unknown>>;
  readonly is_active?: boolean;
}

/**
 * CCTV Engineering & Sizing Engine DTOs
 */
export interface CameraGroupRequest {
  readonly group_label: string;
  readonly technology: CameraTechnology;
  readonly count: number;
  readonly resolution: Resolution;
  readonly fps: Fps;
  readonly codec: Codec;
  readonly retention_days: number;
  readonly recording_hours_per_day: number;
  readonly cabling_mode: CablingMode;
  readonly average_cable_meters: number;
  readonly form_factor: FormFactor;
  readonly ir_current_draw_ma?: number | null;
  readonly poe_power_watts?: number | null;
}

export interface SizingCalculateRequest {
  readonly camera_groups: readonly CameraGroupRequest[];
}

export interface GroupStorageBreakdownResponse {
  readonly group_label: string;
  readonly camera_count: number;
  readonly bitrate_kbps_per_camera: number;
  readonly daily_gb_per_camera: number;
  readonly group_retention_gb: number;
  readonly group_bandwidth_mbps: number;
}

export interface SelectedHddAllocationResponse {
  readonly sku: string;
  readonly capacity_tb: number;
  readonly quantity: number;
  readonly total_capacity_tb: number;
  readonly total_sale_price_cents: number;
}

export interface StorageSummaryResponse {
  readonly group_breakdowns: readonly GroupStorageBreakdownResponse[];
  readonly raw_retention_gb: number;
  readonly total_required_gb_with_margin: number;
  readonly required_nominal_tb: number;
  readonly selected_hdds: readonly SelectedHddAllocationResponse[];
  readonly total_selected_tb: number;
  readonly sata_slots_used: number;
}

export interface TopologySummaryResponse {
  readonly selected_recorder_sku: string;
  readonly is_pure_nvr: boolean;
  readonly analog_cameras_count: number;
  readonly ip_cameras_count: number;
  readonly total_cameras_count: number;
  readonly native_bnc_channels: number;
  readonly extra_ip_channels: number;
  readonly bnc_channels_used_by_analog: number;
  readonly bnc_channels_converted_to_ip: number;
  readonly total_supported_channels: number;
  readonly channel_utilization_percent: number;
  readonly total_incoming_bandwidth_mbps: number;
  readonly max_incoming_bandwidth_mbps: number;
  readonly max_sata_slots: number;
  readonly max_tb_per_slot: number;
}

export interface VoltageDropWarningResponse {
  readonly group_label: string;
  readonly cabling_mode: CablingMode;
  readonly distance_meters: number;
  readonly current_amps: number;
  readonly resistance_ohm_per_meter: number;
  readonly voltage_drop_volts: number;
  readonly voltage_at_load_volts: number;
  readonly min_operating_voltage_volts: number;
  readonly recommendation_pt_br: string;
}

export interface ElectricalSummaryResponse {
  readonly analog_raw_current_amps: number;
  readonly analog_required_current_amps_with_headroom: number;
  readonly ip_raw_power_watts: number;
  readonly ip_required_poe_watts_with_headroom: number;
  readonly coaxial_cable_meters_with_slack: number;
  readonly coaxial_cable_rolls_100m: number;
  readonly utp_cable_meters_with_slack: number;
  readonly utp_cable_boxes_305m: number;
  readonly voltage_drop_warnings: readonly VoltageDropWarningResponse[];
}

export interface SizingBomLineTechnicianResponse {
  readonly role: BomRole;
  readonly catalog_item_id: string;
  readonly sku: string;
  readonly name_pt_br: string;
  readonly category: CatalogCategory;
  readonly brand: string;
  readonly quantity: number;
  readonly unit_sale_cents: number;
  readonly line_total_sale_cents: number;
  readonly available_stock_quantity: number;
  readonly is_auto_derived: boolean;
  readonly notes_pt_br: string;
}

export interface SizingBomLineOwnerResponse extends SizingBomLineTechnicianResponse {
  readonly unit_cost_cents: number;
  readonly line_total_cost_cents: number;
}

export type SizingBomLineResponse =
  | SizingBomLineOwnerResponse
  | SizingBomLineTechnicianResponse;

export function isSizingBomOwnerLine(
  line: SizingBomLineResponse
): line is SizingBomLineOwnerResponse {
  return "unit_cost_cents" in line && typeof line.unit_cost_cents === "number";
}

export interface SizingCalculateTechnicianResponse {
  readonly topology: TopologySummaryResponse;
  readonly storage: StorageSummaryResponse;
  readonly electrical: ElectricalSummaryResponse;
  readonly bom_items: readonly SizingBomLineTechnicianResponse[];
  readonly total_sale_cents: number;
}

export interface SizingCalculateOwnerResponse {
  readonly topology: TopologySummaryResponse;
  readonly storage: StorageSummaryResponse;
  readonly electrical: ElectricalSummaryResponse;
  readonly bom_items: readonly SizingBomLineOwnerResponse[];
  readonly total_cost_cents: number;
  readonly total_sale_cents: number;
  readonly margin_percent: string | number;
}

export type SizingCalculateResponse =
  | SizingCalculateOwnerResponse
  | SizingCalculateTechnicianResponse;

export function isSizingOwnerResponse(
  res: SizingCalculateResponse
): res is SizingCalculateOwnerResponse {
  return "total_cost_cents" in res && typeof res.total_cost_cents === "number";
}

/**
 * Customers & Quotes DTOs (Role-Segregated)
 */
export interface CustomerCreateRequest {
  readonly name: string;
  readonly document_cpf_cnpj: string;
  readonly phone_whatsapp: string;
  readonly email: string;
  readonly address_json?: Readonly<Record<string, unknown>>;
}

export interface CustomerResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly name: string;
  readonly document_cpf_cnpj: string;
  readonly phone_whatsapp: string;
  readonly email: string;
  readonly address_json: Readonly<Record<string, unknown>>;
  readonly created_at: string;
}

export interface AuditLogResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly entity_type: string;
  readonly entity_id: string;
  readonly action: string;
  readonly actor_user_id: string | null;
  readonly actor_ip: string | null;
  readonly previous_state: Readonly<Record<string, unknown>> | null;
  readonly new_state: Readonly<Record<string, unknown>>;
  readonly created_at: string;
}

export interface QuoteItemCreateInput {
  readonly catalog_item_id: string;
  readonly quantity: number;
  readonly unit_sale_cents?: number | null;
  readonly is_auto_derived?: boolean;
}

export interface QuoteCreateRequest {
  readonly customer_id: string;
  readonly valid_days?: number;
  readonly valid_until?: string | null;
  readonly sizing_input_json?: Readonly<Record<string, unknown>> | null;
  readonly items: readonly QuoteItemCreateInput[];
}

export interface PublicQuoteApproveRequest {
  readonly accepted_terms?: boolean;
  readonly client_notes?: string | null;
}

export interface QuoteItemPublicResponse {
  readonly id: string;
  readonly catalog_item_id: string;
  readonly sku: string;
  readonly name_pt_br: string;
  readonly category: CatalogCategory;
  readonly quantity: number;
  readonly unit_sale_cents: number;
  readonly line_total_sale_cents: number;
  readonly is_auto_derived: boolean;
}

export type QuoteItemTechnicianResponse = QuoteItemPublicResponse;

export interface QuoteItemOwnerResponse extends QuoteItemPublicResponse {
  readonly unit_cost_cents: number;
  readonly line_total_cost_cents: number;
}

export type QuoteItemResponse =
  | QuoteItemOwnerResponse
  | QuoteItemTechnicianResponse;

export function isQuoteOwnerItem(
  item: QuoteItemResponse
): item is QuoteItemOwnerResponse {
  return "unit_cost_cents" in item && typeof item.unit_cost_cents === "number";
}

export interface QuotePublicResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly customer_id: string;
  readonly customer: CustomerResponse;
  readonly public_token: string;
  readonly status: QuoteStatus;
  readonly sizing_input_json: Readonly<Record<string, unknown>> | null;
  readonly total_sale_cents: number;
  readonly valid_until: string;
  readonly approved_at: string | null;
  readonly pdf_download_url: string | null;
  readonly pdf_sha256_hash: string | null;
  readonly work_order_id: string | null;
  readonly version: number;
  readonly items: readonly QuoteItemPublicResponse[];
  readonly created_at: string;
  readonly updated_at: string;
}

export interface QuoteTechnicianResponse extends QuotePublicResponse {
  readonly audit_logs: readonly AuditLogResponse[];
}

export interface QuoteOwnerResponse extends QuoteTechnicianResponse {
  readonly total_cost_cents: number;
  readonly margin_percent: string | number;
  readonly approved_by_ip: string | null;
  readonly items: readonly QuoteItemOwnerResponse[];
}

export type QuoteResponse = QuoteOwnerResponse | QuoteTechnicianResponse;

export function isQuoteOwnerResponse(
  quote: QuoteResponse | QuotePublicResponse
): quote is QuoteOwnerResponse {
  return (
    "total_cost_cents" in quote && typeof quote.total_cost_cents === "number"
  );
}

/**
 * Work Orders, Serial Vault, Expiring Warranties & Cryptographic Verification DTOs
 */
export interface ChecklistStepItem {
  readonly step_id: string;
  readonly label_pt_br: string;
  readonly is_checked: boolean;
  readonly checked_at: string | null;
}

export interface WorkOrderChecklistUpdateRequest {
  readonly step_id?: string | null;
  readonly is_checked?: boolean | null;
  readonly steps?: readonly { readonly step_id: string; readonly is_checked: boolean }[] | null;
  readonly cloud_p2p_id?: string | null;
  readonly notes?: string | null;
}

export interface WorkOrderPhotoJsonUploadRequest {
  readonly filename?: string;
  readonly content_base64?: string | null;
  readonly content_type?: string;
  readonly photo_key?: string | null;
}

export interface InstalledSerialCreateRequest {
  readonly catalog_item_id: string;
  readonly serial_number: string;
  readonly channel_or_slot_label: string;
  readonly distributor_warranty_until?: string | null;
  readonly client_warranty_until?: string | null;
}

export interface InstalledSerialResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly work_order_id: string;
  readonly catalog_item_id: string;
  readonly sku: string;
  readonly name_pt_br: string;
  readonly category: CatalogCategory;
  readonly serial_number: string;
  readonly channel_or_slot_label: string;
  readonly distributor_warranty_until: string;
  readonly client_warranty_until: string;
  readonly created_at: string;
}

export interface RequiredSerialItemSummary {
  readonly catalog_item_id: string;
  readonly sku: string;
  readonly name_pt_br: string;
  readonly category: CatalogCategory;
  readonly required_quantity: number;
  readonly registered_quantity: number;
  readonly is_satisfied: boolean;
}

export interface WorkOrderCompleteRequest {
  readonly cloud_p2p_id?: string | null;
  readonly notes?: string | null;
}

export interface WorkOrderResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly quote_id: string;
  readonly quote_status: QuoteStatus;
  readonly customer: CustomerResponse;
  readonly assigned_technician_id: string | null;
  readonly assigned_technician_name: string | null;
  readonly status: WorkOrderStatus;
  readonly checklist_json: readonly ChecklistStepItem[];
  readonly installation_photos_keys: readonly string[];
  readonly installation_photo_urls: readonly string[];
  readonly cloud_p2p_id: string | null;
  readonly notes: string | null;
  readonly completed_at: string | null;
  readonly warranty_expires_at: string | null;
  readonly preventive_maintenance_alert_sent: boolean;
  readonly installed_serials: readonly InstalledSerialResponse[];
  readonly required_serials_summary: readonly RequiredSerialItemSummary[];
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ExpiringWarrantyItemResponse {
  readonly work_order_id: string;
  readonly quote_id: string;
  readonly organization_id: string;
  readonly customer_id: string;
  readonly customer_name: string;
  readonly customer_phone_whatsapp: string;
  readonly customer_email: string;
  readonly completed_at: string | null;
  readonly warranty_expires_at: string;
  readonly days_until_expiration: number;
  readonly preventive_maintenance_alert_sent: boolean;
  readonly cloud_p2p_id: string | null;
  readonly installed_serials_count: number;
  readonly installed_serials: readonly InstalledSerialResponse[];
}

export interface DocumentVerificationResponse {
  readonly verified: boolean;
  readonly pdf_sha256_hash: string;
  readonly organization_name: string;
  readonly organization_cnpj: string;
  readonly quote_id: string;
  readonly quote_status: QuoteStatus;
  readonly quote_version: number;
  readonly customer_name: string;
  readonly customer_document_masked: string;
  readonly total_sale_cents: number;
  readonly approved_at: string | null;
  readonly approved_by_ip: string | null;
  readonly work_order_id: string | null;
  readonly work_order_status: WorkOrderStatus | null;
  readonly completed_at: string | null;
  readonly cloud_p2p_id: string | null;
  readonly warranty_expires_at: string | null;
  readonly is_warranty_active: boolean;
  readonly installed_serials: readonly InstalledSerialResponse[];
}
