import json
import sys
from pathlib import Path
from typing import Any

try:
    from common.afip_mock import validate_invoice
    from common.config import get_float_env
    from common.dynamodb import (
        increment_batch_counters,
        mark_batch_completed_if_needed,
        put_invoice_if_absent,
        utc_now,
    )
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2] / "layers/common/python"))
    from common.afip_mock import validate_invoice
    from common.config import get_float_env
    from common.dynamodb import (
        increment_batch_counters,
        mark_batch_completed_if_needed,
        put_invoice_if_absent,
        utc_now,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    delay_seconds = get_float_env("AFIP_MOCK_DELAY_SECONDS", 0) or 0

    for record in event.get("Records", []):
        message_id = record.get("messageId")

        try:
            payload = _message_body(record)
            process_message(payload, delay_seconds=delay_seconds)
        except Exception as exc:
            print(f"Error tecnico procesando mensaje {message_id}: {exc}")
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}


def process_message(payload: dict[str, Any], *, delay_seconds: float = 0) -> dict[str, Any]:
    batch_id = _required_text(payload.get("batchId"), "batchId")
    row_number = int(payload.get("rowNumber") or 0)
    invoice = payload.get("invoice")

    if not isinstance(invoice, dict):
        raise ValueError("invoice debe ser un objeto")

    validation = validate_invoice(invoice, batch_id=batch_id, delay_seconds=delay_seconds)
    invoice_item = _invoice_item(
        batch_id=batch_id,
        row_number=row_number,
        invoice=invoice,
        validation=validation,
    )

    inserted = put_invoice_if_absent(invoice_item)
    if not inserted:
        print(
            json.dumps(
                {
                    "message": "Factura ya procesada; no se incrementan contadores",
                    "batchId": batch_id,
                    "entityKey": invoice_item["entityKey"],
                }
            )
        )
        return {"inserted": False, "item": invoice_item}

    batch = increment_batch_counters(batch_id, invoice_item["status"])
    completed = mark_batch_completed_if_needed(batch)

    print(
        json.dumps(
            {
                "message": "Factura procesada",
                "batchId": batch_id,
                "entityKey": invoice_item["entityKey"],
                "status": invoice_item["status"],
                "completedBatch": completed is not None,
            }
        )
    )
    return {"inserted": True, "item": invoice_item}


def _invoice_item(
    *,
    batch_id: str,
    row_number: int,
    invoice: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    invoice_number = _invoice_number(invoice, row_number)
    status = "VALIDATED" if validation.get("validated") else "REJECTED"

    return {
        "batchId": batch_id,
        "entityKey": f"INVOICE#{invoice_number}",
        "invoiceNumber": invoice_number,
        "rowNumber": row_number,
        "status": status,
        "validated": bool(validation.get("validated")),
        "cae": validation.get("cae"),
        "errorMessages": validation.get("errorMessages", []),
        "date": _text(invoice.get("date")),
        "customerCUIT": _text(invoice.get("customerCUIT")),
        "customerName": _text(invoice.get("customerName")),
        "customerAddress": _text(invoice.get("customerAddress")),
        "amount": _text(invoice.get("amount")),
        "taxCode": _text(invoice.get("taxCode")),
        "description": _text(invoice.get("description")),
        "quantity": _text(invoice.get("quantity")),
        "unitPrice": _text(invoice.get("unitPrice")),
        "iva": _text(invoice.get("iva")),
        "createdAt": now,
        "processedAt": now,
    }


def _invoice_number(invoice: dict[str, Any], row_number: int) -> str:
    invoice_number = _text(invoice.get("invoiceNumber"))
    if invoice_number:
        return invoice_number
    return f"ROW#{row_number}"


def _message_body(record: dict[str, Any]) -> dict[str, Any]:
    body = record.get("body") or "{}"
    parsed = json.loads(body)

    if not isinstance(parsed, dict):
        raise ValueError("El mensaje SQS debe contener un objeto JSON")

    return parsed


def _required_text(value: Any, field_name: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{field_name} es requerido")
    return text


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
