import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "layers/common/python"))

from functions.api import app as api_app
from functions.parser import app as parser_app
from functions.validator import app as validator_app


class FakeS3Client:
    def generate_presigned_url(self, **kwargs):
        return "https://uploads.example/presigned"


def test_create_upload_url(monkeypatch):
    stored_items = []

    monkeypatch.setenv("UPLOADS_BUCKET_NAME", "uploads-bucket")
    monkeypatch.setenv("PRESIGNED_URL_EXPIRATION_SECONDS", "900")
    monkeypatch.setattr(api_app, "_S3_CLIENT", FakeS3Client())
    monkeypatch.setattr(api_app, "put_item", lambda item: stored_items.append(item))

    response = api_app.lambda_handler(
        {
            "resource": "/batches/upload-url",
            "httpMethod": "POST",
            "body": json.dumps({"fileName": "lote.xlsx"}),
            "isBase64Encoded": False,
        },
        None,
    )

    body = json.loads(response["body"])

    assert response["statusCode"] == 201
    assert body["s3Key"] == f"uploads/{body['batchId']}/lote.xlsx"
    assert body["uploadUrl"] == "https://uploads.example/presigned"
    assert stored_items[0]["entityKey"] == "BATCH"
    assert stored_items[0]["status"] == "WAITING_UPLOAD"


def test_get_batch_invoices_uses_query_helper(monkeypatch):
    monkeypatch.setattr(
        api_app,
        "query_invoices",
        lambda batch_id: [{"batchId": batch_id, "entityKey": "INVOICE#0001-00000001"}],
    )

    response = api_app.lambda_handler(
        {
            "resource": "/batches/{batchId}/invoices",
            "httpMethod": "GET",
            "pathParameters": {"batchId": "batch-1"},
        },
        None,
    )
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["batchId"] == "batch-1"
    assert body["count"] == 1


def test_parser_extracts_batch_id_from_s3_key():
    response = parser_app.lambda_handler(
        {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "uploads-bucket"},
                        "object": {"key": "uploads/batch-1/lote.xlsx"},
                    }
                }
            ]
        },
        None,
    )
    body = json.loads(response["body"])

    assert body["records"][0]["batchId"] == "batch-1"


def test_validator_reports_partial_failures():
    response = validator_app.lambda_handler(
        {
            "Records": [
                {
                    "messageId": "ok-message",
                    "body": json.dumps({"invoiceNumber": "0001-00000001", "amount": 100}),
                },
                {
                    "messageId": "bad-message",
                    "body": "not-json",
                },
            ]
        },
        None,
    )

    assert response == {"batchItemFailures": [{"itemIdentifier": "bad-message"}]}
