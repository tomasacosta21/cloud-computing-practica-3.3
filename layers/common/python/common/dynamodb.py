from typing import Any

from .config import get_env, table_name

_DYNAMODB_RESOURCE = None


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


def put_item(item: dict[str, Any], table=None) -> dict[str, Any]:
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


def query_invoices(batch_id: str, table=None) -> list[dict[str, Any]]:
    from boto3.dynamodb.conditions import Key

    selected_table = table or get_table()
    query_kwargs = {
        "KeyConditionExpression": Key("batchId").eq(batch_id)
        & Key("entityKey").begins_with("INVOICE#")
    }
    items: list[dict[str, Any]] = []

    while True:
        response = selected_table.query(**query_kwargs)
        items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return items

        query_kwargs["ExclusiveStartKey"] = last_key
