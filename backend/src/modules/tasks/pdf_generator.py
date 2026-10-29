"""WeasyPrint PT-BR PDF proposal & warranty certificate generator with QR Code and SHA-256."""

import base64
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import qrcode
import structlog
import weasyprint
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.broker import broker
from src.core.database import async_session_factory
from src.core.exceptions import ResourceNotFoundError
from src.core.storage import StorageClient
from src.modules.quotes.models import Quote, QuoteItem, QuoteStatus
from src.modules.tenants.models import Organization
from src.modules.work_orders.models import InstalledSerial, WorkOrder, WorkOrderStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

_QUOTE_STATUS_PT_BR: dict[QuoteStatus, str] = {
    QuoteStatus.DRAFT: "RASCUNHO",
    QuoteStatus.SENT: "PROPOSTA ENVIADA AO CLIENTE",
    QuoteStatus.APPROVED: "PROPOSTA APROVADA PELO CLIENTE",
    QuoteStatus.IN_PROGRESS: "INSTALAÇÃO EM EXECUÇÃO",
    QuoteStatus.COMPLETED: "INSTALAÇÃO CONCLUÍDA & GARANTIA ATIVA",
    QuoteStatus.CANCELED: "CANCELADA",
    QuoteStatus.EXPIRED: "EXPIRADA",
}

_WO_STATUS_PT_BR: dict[WorkOrderStatus, str] = {
    WorkOrderStatus.PENDING: "PENDENTE DE AGENDAMENTO",
    WorkOrderStatus.SCHEDULED: "TÉCNICO AGENDADO",
    WorkOrderStatus.IN_FIELD: "EM CAMPO (EXECUÇÃO)",
    WorkOrderStatus.COMPLETED: "CONCLUÍDA",
}


@dataclass(frozen=True)
class RenderedPdfResult:
    """Result returned after generating, hashing, and uploading a Quote PDF."""

    quote_id: UUID
    organization_id: UUID
    pdf_storage_key: str
    pdf_sha256_hash: str
    pdf_size_bytes: int


def format_brl_cents(cents: int) -> str:
    """Format integer centavos into Brazilian Real currency string (e.g., 'R$ 1.499,90')."""
    sign = "-" if cents < 0 else ""
    abs_cents = abs(cents)
    reais = abs_cents // 100
    centavos = abs_cents % 100
    reais_str = f"{reais:,}".replace(",", ".")
    return f"{sign}R$ {reais_str},{centavos:02d}"


def format_date_pt_br(dt_val: date | datetime | None) -> str:
    """Format a date or datetime in DD/MM/YYYY Brazilian format."""
    if dt_val is None:
        return "N/A"
    if isinstance(dt_val, datetime):
        return dt_val.strftime("%d/%m/%Y %H:%M UTC")
    return dt_val.strftime("%d/%m/%Y")


def format_address_pt_br(address_json: dict[str, object]) -> str:
    """Format a customer address_json dictionary into a single PT-BR line."""
    if not address_json:
        return "Endereço conforme cadastro do cliente"
    parts: list[str] = []
    street = str(address_json.get("street", "")).strip()
    number = str(address_json.get("number", "")).strip()
    complement = str(address_json.get("complement", "")).strip()
    district = str(address_json.get("district", "")).strip()
    city = str(address_json.get("city", "")).strip()
    state = str(address_json.get("state", "")).strip()
    zip_code = str(address_json.get("zip_code", "")).strip()

    if street:
        parts.append(f"{street}, {number}" if number else street)
    if complement:
        parts.append(complement)
    if district:
        parts.append(district)
    if city and state:
        parts.append(f"{city}/{state}")
    elif city:
        parts.append(city)
    if zip_code:
        parts.append(f"CEP {zip_code}")
    return " - ".join(parts) if parts else "Endereço conforme cadastro do cliente"


def generate_qr_code_base64(verification_data: str) -> str:
    """Generate a PNG QR Code for the verification URL and return it as a Base64 string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(verification_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def render_proposal_html(
    *,
    quote: Quote,
    organization: Organization,
    generated_at: datetime,
) -> str:
    """Render the PT-BR Jinja2 HTML proposal & warranty certificate (strictly omitting cost)."""
    template = _jinja_env.get_template("proposal_and_warranty.html")

    sizing_entries: list[dict[str, str]] = []
    if quote.sizing_input_json:
        label_map = {
            "scenario_label": "Cenário Técnico",
            "retention_days": "Retenção de Gravação (Dias)",
            "codec": "Compressão de Vídeo",
            "required_storage_gb": "Armazenamento Calculado (GB)",
            "required_storage_tb": "Capacidade Nominal HD (TB)",
            "selected_dvr_sku": "Gravador Selecionado",
        }
        for key, raw_val in quote.sizing_input_json.items():
            if isinstance(raw_val, (str, int, float, bool)):
                sizing_entries.append(
                    {
                        "label": label_map.get(key, key),
                        "value": str(raw_val),
                    }
                )

    bom_items: list[dict[str, object]] = []
    for line in quote.items:
        line_total = line.quantity * line.unit_sale_cents
        bom_items.append(
            {
                "sku": line.catalog_item.sku,
                "name_pt_br": line.catalog_item.name_pt_br,
                "quantity": line.quantity,
                "unit_sale_formatted": format_brl_cents(line.unit_sale_cents),
                "line_total_formatted": format_brl_cents(line_total),
            }
        )

    wo_context: dict[str, str | None] | None = None
    serial_rows: list[dict[str, str]] = []
    if quote.work_order is not None:
        wo = quote.work_order
        wo_context = {
            "id": str(wo.id),
            "status_label_pt_br": _WO_STATUS_PT_BR.get(wo.status, wo.status.value),
            "cloud_p2p_id": wo.cloud_p2p_id,
            "completed_at_formatted": (
                format_date_pt_br(wo.completed_at) if wo.completed_at else None
            ),
            "warranty_expires_formatted": (
                format_date_pt_br(wo.warranty_expires_at) if wo.warranty_expires_at else None
            ),
        }
        for serial in wo.installed_serials:
            serial_rows.append(
                {
                    "sku": serial.catalog_item.sku,
                    "name_pt_br": serial.catalog_item.name_pt_br,
                    "channel_or_slot_label": serial.channel_or_slot_label,
                    "serial_number": serial.serial_number,
                    "client_warranty_formatted": format_date_pt_br(serial.client_warranty_until),
                }
            )

    verification_url = f"https://bravo-erp.dev/public/quotes/{quote.public_token}"
    qr_payload = (
        f"{verification_url}|quote={quote.id}|status={quote.status.value}|v={quote.version}"
    )
    qr_code_b64 = generate_qr_code_base64(qr_payload)

    return template.render(
        organization_name=organization.name,
        organization_cnpj=organization.document_cnpj,
        quote_id=str(quote.id),
        quote_version=quote.version,
        status_label_pt_br=_QUOTE_STATUS_PT_BR.get(quote.status, quote.status.value),
        customer_name=quote.customer.name,
        customer_document=quote.customer.document_cpf_cnpj,
        customer_phone=quote.customer.phone_whatsapp,
        customer_email=quote.customer.email,
        customer_address_formatted=format_address_pt_br(quote.customer.address_json),
        valid_until_formatted=format_date_pt_br(quote.valid_until),
        sizing_entries=sizing_entries,
        items=bom_items,
        total_sale_formatted=format_brl_cents(quote.total_sale_cents),
        approved_at_formatted=(format_date_pt_br(quote.approved_at) if quote.approved_at else None),
        approved_by_ip=str(quote.approved_by_ip) if quote.approved_by_ip else "N/A",
        work_order=wo_context,
        installed_serials=serial_rows,
        qr_code_base64=qr_code_b64,
        public_token=str(quote.public_token),
        verification_url=verification_url,
        generated_at_iso=generated_at.isoformat(),
    )


def render_pdf_bytes_and_sha256(html_content: str) -> tuple[bytes, str]:
    """Render HTML string into PDF bytes via WeasyPrint and return (pdf_bytes, sha256_hex)."""
    raw_pdf: bytes | None = weasyprint.HTML(string=html_content).write_pdf()
    pdf_bytes = bytes(raw_pdf) if raw_pdf is not None else b""
    sha256_hex = hashlib.sha256(pdf_bytes).hexdigest()
    return pdf_bytes, sha256_hex


async def generate_and_store_quote_pdf(
    session: AsyncSession,
    quote_id: UUID,
    *,
    storage_client: StorageClient | None = None,
) -> RenderedPdfResult:
    """Load Quote + WorkOrder + Serials, render WeasyPrint PDF, upload to S3, and save SHA-256."""
    stmt = (
        select(Quote)
        .options(
            selectinload(Quote.customer),
            selectinload(Quote.items).selectinload(QuoteItem.catalog_item),
            selectinload(Quote.work_order)
            .selectinload(WorkOrder.installed_serials)
            .selectinload(InstalledSerial.catalog_item),
        )
        .where(Quote.id == quote_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    quote = await session.scalar(stmt)
    if quote is None:
        raise ResourceNotFoundError(
            detail=f"Quote '{quote_id}' was not found for PDF generation.",
            errors=[{"quote_id": str(quote_id)}],
        )

    org_stmt = select(Organization).where(Organization.id == quote.organization_id)
    organization = await session.scalar(org_stmt)
    if organization is None:  # pragma: no cover
        raise ResourceNotFoundError(detail="Organization not found for PDF generation.")

    generated_at = datetime.now(UTC)
    html_content = render_proposal_html(
        quote=quote,
        organization=organization,
        generated_at=generated_at,
    )
    pdf_bytes, pdf_sha256_hash = render_pdf_bytes_and_sha256(html_content)

    storage = storage_client or StorageClient()
    object_key = f"proposals/{quote.organization_id}/{quote.id}.pdf"
    await storage.upload_bytes(
        object_key=object_key,
        data=pdf_bytes,
        content_type="application/pdf",
    )

    quote.pdf_storage_key = object_key
    quote.pdf_sha256_hash = pdf_sha256_hash
    await session.flush()

    logger.info(
        "quote_pdf_generated_and_stored",
        quote_id=str(quote.id),
        organization_id=str(quote.organization_id),
        pdf_storage_key=object_key,
        pdf_sha256_hash=pdf_sha256_hash,
        pdf_size_bytes=len(pdf_bytes),
    )
    return RenderedPdfResult(
        quote_id=quote.id,
        organization_id=quote.organization_id,
        pdf_storage_key=object_key,
        pdf_sha256_hash=pdf_sha256_hash,
        pdf_size_bytes=len(pdf_bytes),
    )


@broker.task(task_name="tasks.generate_quote_pdf")
async def generate_quote_pdf_task(
    quote_id: str,
    correlation_id: str | None = None,
) -> dict[str, str | int]:
    """Taskiq background task that renders and uploads the Quote PDF and commits SHA-256."""
    if correlation_id:
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

    async with async_session_factory() as session:
        result = await generate_and_store_quote_pdf(session, UUID(quote_id))
        await session.commit()
        return {
            "quote_id": str(result.quote_id),
            "pdf_storage_key": result.pdf_storage_key,
            "pdf_sha256_hash": result.pdf_sha256_hash,
            "pdf_size_bytes": result.pdf_size_bytes,
        }
