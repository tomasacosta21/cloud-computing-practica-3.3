import base64
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from common.config import get_int_env, uploads_bucket_name
    from common.dynamodb import get_batch, put_item, query_invoices
    from common.responses import error_response, json_response
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2] / "layers/common/python"))
    from common.config import get_int_env, uploads_bucket_name
    from common.dynamodb import get_batch, put_item, query_invoices
    from common.responses import error_response, json_response

_S3_CLIENT = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = event.get("httpMethod", "")
    resource = event.get("resource") or event.get("path", "")

    try:
        if method == "OPTIONS":
            return json_response({})

        if method == "POST" and resource == "/batches/upload-url":
            return create_upload_url(event)

        if method == "GET" and resource == "/batches/{batchId}":
            return get_batch_response(event)

        if method == "GET" and resource == "/batches/{batchId}/invoices":
            return get_batch_invoices_response(event)

        return error_response("Ruta no encontrada", 404, error_code="NOT_FOUND")
    except ValueError as exc:
        return error_response(str(exc), 400, error_code="BAD_REQUEST")
    except Exception as exc:
        print("Error procesando request API:", exc)
        return error_response("Error interno del servidor", 500, error_code="INTERNAL_ERROR")


def create_upload_url(event: dict[str, Any]) -> dict[str, Any]:
    body = _json_body(event)
    file_name = _safe_file_name(body.get("fileName"))
    batch_id = str(uuid.uuid4())
    s3_key = f"uploads/{batch_id}/{file_name}"
    now = datetime.now(timezone.utc).isoformat()

    upload_url = _s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": uploads_bucket_name(),
            "Key": s3_key,
        },
        ExpiresIn=get_int_env("PRESIGNED_URL_EXPIRATION_SECONDS", 900) or 900,
        HttpMethod="PUT",
    )

    put_item(
        {
            "batchId": batch_id,
            "entityKey": "BATCH",
            "status": "WAITING_UPLOAD",
            "fileName": file_name,
            "s3Key": s3_key,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    return json_response(
        {
            "batchId": batch_id,
            "s3Key": s3_key,
            "uploadUrl": upload_url,
            "message": "URL de subida generada",
        },
        201,
    )


def get_batch_response(event: dict[str, Any]) -> dict[str, Any]:
    batch_id = _batch_id(event)
    batch = get_batch(batch_id)

    if not batch:
        return error_response("Lote no encontrado", 404, error_code="BATCH_NOT_FOUND")

    return json_response(batch)


def get_batch_invoices_response(event: dict[str, Any]) -> dict[str, Any]:
    batch_id = _batch_id(event)
    invoices = query_invoices(batch_id)

    return json_response(
        {
            "batchId": batch_id,
            "items": invoices,
            "count": len(invoices),
        }
    )


def _json_body(event: dict[str, Any]) -> dict[str, Any]:
    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("El body debe ser JSON valido") from exc

    if not isinstance(body, dict):
        raise ValueError("El body debe ser un objeto JSON")

    return body


def _safe_file_name(file_name: Any) -> str:
    if not isinstance(file_name, str) or not file_name.strip():
        raise ValueError("fileName es requerido")

    clean_name = os.path.basename(file_name.strip())
    if clean_name in {"", ".", ".."}:
        raise ValueError("fileName no es valido")

    return clean_name


def _batch_id(event: dict[str, Any]) -> str:
    path_parameters = event.get("pathParameters") or {}
    batch_id = path_parameters.get("batchId")

    if not batch_id:
        raise ValueError("batchId es requerido")

    return batch_id


def _s3_client():
    global _S3_CLIENT

    if _S3_CLIENT is None:
        import boto3

        _S3_CLIENT = boto3.client("s3")

    return _S3_CLIENT
