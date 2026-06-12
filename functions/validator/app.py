import json
import sys
from pathlib import Path
from typing import Any

try:
    from common.afip_mock import validate_invoice
    from common.config import get_float_env
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2] / "layers/common/python"))
    from common.afip_mock import validate_invoice
    from common.config import get_float_env


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    delay_seconds = get_float_env("AFIP_MOCK_DELAY_SECONDS", 0) or 0

    for record in event.get("Records", []):
        message_id = record.get("messageId")

        try:
            payload = _message_body(record)
            validation = validate_invoice(payload, delay_seconds=delay_seconds)
            print(
                json.dumps(
                    {
                        "messageId": message_id,
                        "payload": payload,
                        "validation": validation,
                    }
                )
            )

            # TODO: guardar el resultado de validacion en DynamoDB y actualizar
            # contadores del lote cuando se implemente el procesamiento real.
        except Exception as exc:
            print(f"Error procesando mensaje {message_id}: {exc}")
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}


def _message_body(record: dict[str, Any]) -> dict[str, Any]:
    body = record.get("body") or "{}"
    parsed = json.loads(body)

    if not isinstance(parsed, dict):
        raise ValueError("El mensaje SQS debe contener un objeto JSON")

    return parsed
