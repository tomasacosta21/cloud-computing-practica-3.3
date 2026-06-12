import base64
import json
from datetime import datetime, timezone
from typing import Any

from .config import get_env, table_name

_DYNAMODB_RESOURCE = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dynamodb_resource():
    global _DYNAMODB_RESOURCE

    if _DYNAMODB_RESOURCE is None:
        import boto3

        region_name = get_env("AWS_REGION_NAME") or get_env("AWS_REGION")
        kwargs = {"region_name": region_name} if region_name else {}
        _DYNAMODB_RESOURCE = boto3.resource("dynamodb", **kwargs)

    return _DYNAMODB_RESOURCE


def get_table(name: str | None = None):
    return dynamodb_resource().Table(name or table_name())


def put_batch_initial(
    *,
    batch_id: str,
    file_name: str,
    s3_key: str,
    table=None,
) -> dict[str, Any]:
    now = utc_now()
    item = {
        "batchId": batch_id,
        "entityKey": "BATCH",
        "status": "WAITING_UPLOAD",
        "fileName": file_name,
        "s3Key": s3_key,
        "totalInvoices": 0,
        "queuedInvoices": 0,
        "processedInvoices": 0,
        "validatedInvoices": 0,
        "rejectedInvoices": 0,
        "errorInvoices": 0,
        "createdAt": now,
        "updatedAt": now,
        "completedAt": None,
    }
    selected_table = table or get_table()
    selected_table.put_item(Item=item)
    return item


def get_batch(batch_id: str, table=None) -> dict[str, Any] | None:
    selected_table = table or get_table()
    response = selected_table.get_item(
        Key={
            "batchId": batch_id,
            "entityKey": "BATCH",
        }
    )
    return response.get("Item")


def update_batch_processing(
    *,
    batch_id: str,
    file_name: str,
    s3_key: str,
    total_invoices: int,
    queued_invoices: int | None = None,
    table=None,
) -> dict[str, Any]:
    selected_table = table or get_table()
    now = utc_now()
    queued_value = total_invoices if queued_invoices is None else queued_invoices
    response = selected_table.update_item(
        Key={"batchId": batch_id, "entityKey": "BATCH"},
        UpdateExpression=(
            "SET #status = :status, fileName = :file_name, s3Key = :s3_key, "
            "createdAt = if_not_exists(createdAt, :created_at), "
            "totalInvoices = :total, queuedInvoices = :queued, "
            "processedInvoices = :zero, validatedInvoices = :zero, rejectedInvoices = :zero, "
            "errorInvoices = :zero, updatedAt = :updated_at, completedAt = :completed_at "
            "REMOVE errorMessage"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "PROCESSING",
            ":file_name": file_name,
            ":s3_key": s3_key,
            ":total": total_invoices,
            ":queued": queued_value,
            ":zero": 0,
            ":created_at": now,
            ":updated_at": now,
            ":completed_at": None,
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def mark_batch_failed(
    batch_id: str,
    message: str,
    *,
    file_name: str | None = None,
    s3_key: str | None = None,
    table=None,
) -> dict[str, Any]:
    selected_table = table or get_table()
    now = utc_now()
    update_parts = [
        "#status = :status",
        "errorMessage = :message",
        "createdAt = if_not_exists(createdAt, :created_at)",
        "updatedAt = :updated_at",
        "completedAt = :completed_at",
    ]
    expression_values: dict[str, Any] = {
        ":status": "FAILED",
        ":message": message,
        ":created_at": now,
        ":updated_at": now,
        ":completed_at": now,
    }
    if file_name is not None:
        update_parts.append("fileName = :file_name")
        expression_values[":file_name"] = file_name
    if s3_key is not None:
        update_parts.append("s3Key = :s3_key")
        expression_values[":s3_key"] = s3_key

    response = selected_table.update_item(
        Key={"batchId": batch_id, "entityKey": "BATCH"},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=expression_values,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def query_invoices(
    batch_id: str,
    *,
    status: str | None = None,
    limit: int | None = None,
    next_token: str | None = None,
    table=None,
) -> dict[str, Any]:
    selected_table = table or get_table()
    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": "batchId = :batch_id AND begins_with(entityKey, :invoice_prefix)",
        "ExpressionAttributeValues": {
            ":batch_id": batch_id,
            ":invoice_prefix": "INVOICE#",
        },
    }
    if limit:
        query_kwargs["Limit"] = limit
    if next_token:
        query_kwargs["ExclusiveStartKey"] = decode_page_token(next_token)

    items: list[dict[str, Any]] = []

    while True:
        response = selected_table.query(**query_kwargs)
        page_items = response.get("Items", [])
        if status:
            page_items = [item for item in page_items if item.get("status") == status]

        for item in page_items:
            items.append(item)
            if limit and len(items) >= limit:
                return {
                    "items": items,
                    "nextToken": encode_page_token(response.get("LastEvaluatedKey")),
                }

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return {
                "items": items,
                "nextToken": None,
            }

        query_kwargs["ExclusiveStartKey"] = last_key


def encode_page_token(last_evaluated_key: dict[str, Any] | None) -> str | None:
    if not last_evaluated_key:
        return None

    raw = json.dumps(last_evaluated_key, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_page_token(token: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("nextToken no es valido") from exc

    if not isinstance(decoded, dict):
        raise ValueError("nextToken no es valido")

    return decoded


def put_invoice_if_absent(invoice_item: dict[str, Any], table=None) -> bool:
    selected_table = table or get_table()

    try:
        selected_table.put_item(
            Item=invoice_item,
            ConditionExpression="attribute_not_exists(batchId) AND attribute_not_exists(entityKey)",
        )
        return True
    except Exception as exc:
        if _is_conditional_check_failed(exc):
            return False
        raise


def increment_batch_counters(batch_id: str, invoice_status: str, table=None) -> dict[str, Any]:
    selected_table = table or get_table()
    counter_name = {
        "VALIDATED": "validatedInvoices",
        "REJECTED": "rejectedInvoices",
        "ERROR": "errorInvoices",
    }.get(invoice_status)

    if not counter_name:
        raise ValueError(f"Unsupported invoice status: {invoice_status}")

    response = selected_table.update_item(
        Key={"batchId": batch_id, "entityKey": "BATCH"},
        UpdateExpression=(
            "SET updatedAt = :updated_at "
            "ADD processedInvoices :one, #counter :one"
        ),
        ExpressionAttributeNames={"#counter": counter_name},
        ExpressionAttributeValues={":one": 1, ":updated_at": utc_now()},
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def mark_batch_completed_if_needed(batch: dict[str, Any], table=None) -> dict[str, Any] | None:
    processed = int(batch.get("processedInvoices") or 0)
    total = int(batch.get("totalInvoices") or 0)

    if total <= 0 or processed < total:
        return None

    has_errors = int(batch.get("rejectedInvoices") or 0) > 0 or int(batch.get("errorInvoices") or 0) > 0
    status = "COMPLETED_WITH_ERRORS" if has_errors else "COMPLETED"
    selected_table = table or get_table()
    now = utc_now()
    response = selected_table.update_item(
        Key={"batchId": batch["batchId"], "entityKey": "BATCH"},
        UpdateExpression=(
            "SET #status = :status, updatedAt = :updated_at, completedAt = :completed_at"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":updated_at": now,
            ":completed_at": now,
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def _is_conditional_check_failed(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    return error.get("Code") == "ConditionalCheckFailedException"
