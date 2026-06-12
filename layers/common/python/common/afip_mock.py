import hashlib
import time
from decimal import Decimal, InvalidOperation
from typing import Any


def validate_invoice(
    invoice: dict[str, Any],
    *,
    batch_id: str = "",
    delay_seconds: float = 0,
) -> dict[str, Any]:
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    invoice_number = _text(invoice.get("invoiceNumber"))
    errors = []

    if not invoice_number or invoice_number.startswith("ROW#"):
        errors.append("Numero de factura faltante")

    if not _text(invoice.get("customerCUIT")):
        errors.append("CUIT invalido")

    if not _text(invoice.get("date")):
        errors.append("Fecha faltante")

    amount = _decimal(invoice.get("amount"))
    if amount is None or amount <= 0:
        errors.append("Monto invalido")

    if errors:
        return {
            "validated": False,
            "cae": None,
            "errorMessages": errors,
        }

    return {
        "validated": True,
        "cae": _cae(batch_id, invoice_number),
        "errorMessages": [],
    }


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _cae(batch_id: str, invoice_number: str) -> str:
    digest = hashlib.sha256(f"{batch_id}:{invoice_number}".encode("utf-8")).hexdigest()
    return f"CAE-{digest[:14].upper()}"
