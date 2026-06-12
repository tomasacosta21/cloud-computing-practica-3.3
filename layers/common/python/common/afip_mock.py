import time
from datetime import datetime, timezone
from typing import Any


def validate_invoice(
    invoice: dict[str, Any],
    *,
    delay_seconds: float = 0,
) -> dict[str, Any]:
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    invoice_number = (
        invoice.get("invoiceNumber")
        or invoice.get("numero")
        or invoice.get("number")
        or invoice.get("id")
    )
    amount = invoice.get("amount", invoice.get("importe"))
    is_valid = bool(invoice_number) and _is_positive_amount(amount)

    return {
        "status": "VALID" if is_valid else "INVALID",
        "source": "AFIP_MOCK",
        "invoiceNumber": invoice_number,
        "message": "Mock AFIP validation completed",
        "validatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _is_positive_amount(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
