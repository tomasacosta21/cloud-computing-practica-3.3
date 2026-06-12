import base64
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

try:
    from common.config import get_int_env, uploads_bucket_name
    from common.dynamodb import get_batch, put_batch_initial, query_invoices
    from common.responses import error_response, json_response
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2] / "layers/common/python"))
    from common.config import get_int_env, uploads_bucket_name
    from common.dynamodb import get_batch, put_batch_initial, query_invoices
    from common.responses import error_response, json_response

EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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

    upload_url = _s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": uploads_bucket_name(),
            "Key": s3_key,
            "ContentType": EXCEL_CONTENT_TYPE,
        },
        ExpiresIn=get_int_env("PRESIGNED_URL_EXPIRATION_SECONDS", 900) or 900,
        HttpMethod="PUT",
    )

    put_batch_initial(batch_id=batch_id, file_name=file_name, s3_key=s3_key)

    return json_response(
        {
            "batchId": batch_id,
            "s3Key": s3_key,
            "uploadUrl": upload_url,
            "uploadMethod": "PUT",
            "uploadHeaders": {
                "Content-Type": EXCEL_CONTENT_TYPE,
            },
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
    query_params = event.get("queryStringParameters") or {}
    status = query_params.get("status")
    limit = _optional_limit(query_params.get("limit"))
    result = query_invoices(
        batch_id,
        status=status,
        limit=limit,
        next_token=query_params.get("nextToken"),
    )
    invoices = result["items"]

    return json_response(
        {
            "batchId": batch_id,
            "items": invoices,
            "count": len(invoices),
            "nextToken": result.get("nextToken"),
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

    clean_name = os.path.basename(file_name.strip().replace("\\", "/"))
    clean_name = clean_name.replace("..", "")
    clean_name = re.sub(r"[^A-Za-z0-9._ -]", "_", clean_name).strip()

    if clean_name in {"", ".", ".."}:
        raise ValueError("fileName no es valido")

    if not clean_name.lower().endswith(".xlsx"):
        raise ValueError("fileName debe terminar en .xlsx")

    return clean_name


def _optional_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None

    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit debe ser un entero positivo") from exc

    if limit <= 0:
        raise ValueError("limit debe ser un entero positivo")

    return limit


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
