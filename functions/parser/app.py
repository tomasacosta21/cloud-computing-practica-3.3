import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

try:
    from common.responses import json_response
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2] / "layers/common/python"))
    from common.responses import json_response


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    parsed_records = []

    for record in event.get("Records", []):
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        key = unquote_plus(s3_info.get("object", {}).get("key", ""))
        batch_id = _batch_id_from_key(key)

        parsed_record = {
            "bucket": bucket,
            "key": key,
            "batchId": batch_id,
        }
        parsed_records.append(parsed_record)
        print(json.dumps(parsed_record))

        # TODO: leer el Excel desde S3, contar filas, actualizar el item BATCH
        # en DynamoDB y enviar una factura por mensaje a SQS.

    return json_response(
        {
            "message": "Evento S3 recibido",
            "records": parsed_records,
            "count": len(parsed_records),
        }
    )


def _batch_id_from_key(key: str) -> str | None:
    parts = key.split("/")
    if len(parts) >= 3 and parts[0] == "uploads":
        return parts[1]
    return None
