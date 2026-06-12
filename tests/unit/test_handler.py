import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "layers/common/python"))

from common.afip_mock import validate_invoice
from functions.api import app as api_app
from functions.parser import app as parser_app
from functions.validator import app as validator_app


class FakeS3Client:
    def generate_presigned_url(self, **kwargs):
        self.kwargs = kwargs
        return "https://uploads.example/presigned"


def test_create_upload_url(monkeypatch):
    fake_s3 = FakeS3Client()

    monkeypatch.setenv("UPLOADS_BUCKET_NAME", "uploads-bucket")
    monkeypatch.setenv("PRESIGNED_URL_EXPIRATION_SECONDS", "900")
    monkeypatch.setattr(api_app, "_S3_CLIENT", fake_s3)

    response = api_app.lambda_handler(
        {
            "resource": "/batches/upload-url",
            "httpMethod": "POST",
            "body": json.dumps({"fileName": "../lote.xlsx"}),
            "isBase64Encoded": False,
        },
        None,
    )

    body = json.loads(response["body"])

    assert response["statusCode"] == 201
    assert body["s3Key"] == f"uploads/{body['batchId']}/lote.xlsx"
    assert body["uploadUrl"] == "https://uploads.example/presigned"
    assert body["uploadMethod"] == "PUT"
    assert body["uploadHeaders"]["Content-Type"] == api_app.EXCEL_CONTENT_TYPE
    assert fake_s3.kwargs["Params"]["ContentType"] == api_app.EXCEL_CONTENT_TYPE


def test_create_upload_url_rejects_non_xlsx():
    response = api_app.lambda_handler(
        {
            "resource": "/batches/upload-url",
            "httpMethod": "POST",
            "body": json.dumps({"fileName": "lote.csv"}),
            "isBase64Encoded": False,
        },
        None,
    )

    assert response["statusCode"] == 400


def test_get_batch_invoices_uses_query_helper(monkeypatch):
    monkeypatch.setattr(
        api_app,
        "query_invoices",
        lambda batch_id, status=None, limit=None, next_token=None: {
            "items": [{"batchId": batch_id, "entityKey": "INVOICE#0001-00000001", "status": status}][
                :limit
            ],
            "nextToken": "next-page",
        },
    )

    response = api_app.lambda_handler(
        {
            "resource": "/batches/{batchId}/invoices",
            "httpMethod": "GET",
            "pathParameters": {"batchId": "batch-1"},
            "queryStringParameters": {"status": "VALIDATED", "limit": "1"},
        },
        None,
    )
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["batchId"] == "batch-1"
    assert body["count"] == 1
    assert body["nextToken"] == "next-page"
    assert body["items"][0]["status"] == "VALIDATED"


def test_afip_mock_validates_and_rejects():
    valid = validate_invoice(
        {
            "invoiceNumber": "0001-00000001",
            "date": "2025-05-12",
            "customerCUIT": "20-12345678-9",
            "amount": "1000.00",
        },
        batch_id="batch-1",
    )
    invalid = validate_invoice({"invoiceNumber": "ROW#2", "amount": "0"}, batch_id="batch-1")

    assert valid["validated"] is True
    assert valid["cae"].startswith("CAE-")
    assert invalid["validated"] is False
    assert "Numero de factura faltante" in invalid["errorMessages"]
    assert "Monto invalido" in invalid["errorMessages"]


def test_parser_normalizes_row():
    headers = (
        "InvoiceNumber",
        "Date",
        "CustomerCUIT",
        "CustomerName",
        "CustomerAddress",
        "Amount",
        "TaxCode",
        "Description",
        "Quantity",
        "UnitPrice",
        "IVA",
    )
    row = (
        "0001-00000001",
        "2025-05-12",
        "20-12345678-9",
        "Cliente S.A.",
        "Calle Falsa 123",
        1000.0,
        21,
        "Producto A",
        2,
        500.0,
        "21%",
    )

    invoice = parser_app._invoice_from_row(row, parser_app._header_map(headers))

    assert invoice["invoiceNumber"] == "0001-00000001"
    assert invoice["amount"] == "1000.0"
    assert invoice["unitPrice"] == "500.0"
    assert invoice["customerName"] == "Cliente S.A."


def test_parser_creates_batch_metadata_before_queueing(monkeypatch):
    calls = []
    parsed_messages = [{"batchId": "batch-1", "rowNumber": 2, "invoice": {"invoiceNumber": "A-1"}}]

    monkeypatch.setattr(parser_app, "_download_object", lambda bucket, key: b"excel")
    monkeypatch.setattr(parser_app, "parse_excel", lambda content, batch_id: parsed_messages)
    monkeypatch.setattr(
        parser_app,
        "update_batch_processing",
        lambda **kwargs: calls.append(("update", kwargs)),
    )
    monkeypatch.setattr(
        parser_app,
        "_send_messages",
        lambda messages: calls.append(("send", messages)) or len(messages),
    )

    summary = parser_app.process_object(
        bucket="uploads-bucket",
        key="uploads/batch-1/lote.xlsx",
        batch_id="batch-1",
    )

    assert calls[0][0] == "update"
    assert calls[0][1]["batch_id"] == "batch-1"
    assert calls[0][1]["file_name"] == "lote.xlsx"
    assert calls[0][1]["s3_key"] == "uploads/batch-1/lote.xlsx"
    assert calls[0][1]["total_invoices"] == 1
    assert calls[1] == ("send", parsed_messages)
    assert summary["queuedInvoices"] == 1


def test_validator_process_message_updates_counters(monkeypatch):
    saved_items = []
    updated_statuses = []

    monkeypatch.setattr(
        validator_app,
        "put_invoice_if_absent",
        lambda item: saved_items.append(item) or True,
    )
    monkeypatch.setattr(
        validator_app,
        "increment_batch_counters",
        lambda batch_id, status: updated_statuses.append(status)
        or {
            "batchId": batch_id,
            "totalInvoices": 1,
            "processedInvoices": 1,
            "rejectedInvoices": 0,
            "errorInvoices": 0,
        },
    )
    monkeypatch.setattr(validator_app, "mark_batch_completed_if_needed", lambda batch: batch)

    result = validator_app.process_message(
        {
            "batchId": "batch-1",
            "rowNumber": 2,
            "invoice": {
                "invoiceNumber": "0001-00000001",
                "date": "2025-05-12",
                "customerCUIT": "20-12345678-9",
                "amount": "1000.00",
            },
        }
    )

    assert result["inserted"] is True
    assert saved_items[0]["entityKey"] == "INVOICE#0001-00000001"
    assert saved_items[0]["status"] == "VALIDATED"
    assert updated_statuses == ["VALIDATED"]


def test_validator_reports_partial_failures(monkeypatch):
    monkeypatch.setattr(validator_app, "process_message", lambda payload, delay_seconds=0: None)

    response = validator_app.lambda_handler(
        {
            "Records": [
                {
                    "messageId": "ok-message",
                    "body": json.dumps({"batchId": "batch-1", "rowNumber": 2, "invoice": {}}),
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
