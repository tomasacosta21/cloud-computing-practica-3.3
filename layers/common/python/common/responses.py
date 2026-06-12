import json
from decimal import Decimal
from typing import Any


DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT",
}


class DecimalJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def json_response(
    body: Any,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response_headers = dict(DEFAULT_HEADERS)
    if headers:
        response_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps(body, cls=DecimalJSONEncoder),
    }


def error_response(
    message: str,
    status_code: int = 500,
    *,
    error_code: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error": message}
    if error_code:
        body["errorCode"] = error_code
    return json_response(body, status_code)
