# Servicio validador de facturas

**Cloud Computing - Licenciatura en Sistemas, UNRN**<br>
**Integrantes:** Acosta Tomas, Antrichipay Daniel, Cabeza Franco

Este repositorio contiene una aplicacion serverless definida con AWS SAM para cargar lotes de facturas, subir el archivo Excel directo a S3 mediante URL prefirmada y procesar las facturas de forma asincronica.

## Arquitectura objetivo

```text
Web S3 -> API Gateway -> ApiFunction -> S3 uploads
                                 |
                                 v
                         DynamoDB FacturasTable

S3 uploads -> ParserFunction -> SQS InvoicesQueue -> ValidatorFunction -> DynamoDB FacturasTable
                                      |
                                      v
                                  InvoicesDLQ
```

No se implementan SNS, notificaciones ni LocalStack en esta etapa.

## Primera etapa implementada

- Estructura separada por Lambda en `functions/api`, `functions/parser` y `functions/validator`.
- `POST /batches/upload-url` genera `batchId`, `s3Key` y una URL prefirmada real para subir el Excel al bucket privado.
- `GET /batches/{batchId}` consulta el item `BATCH` con `GetItem`.
- `GET /batches/{batchId}/invoices` consulta facturas con `Query` y `begins_with(entityKey, 'INVOICE#')`; no usa `Scan`.
- Bucket privado para uploads con CORS y evento S3 hacia la Lambda parser.
- Bucket S3 para sitio estatico en `web/`.
- Cola SQS principal con DLQ y `maxReceiveCount: 3`.
- Lambda validator conectada a SQS con `ReportBatchItemFailures`.
- Layer comun con codigo propio en `layers/common/python/common/`.
- Rol Lambda parametrizado con `LambdaRoleName`, default `LabRole`.

## Pendiente para la segunda etapa

- Leer el Excel real con `openpyxl`.
- Dividir el lote en mensajes SQS, una factura por mensaje.
- Completar la validacion AFIP mockeada.
- Guardar resultados finales de facturas en DynamoDB.
- Actualizar contadores y estados del lote.

## Modelo DynamoDB

Se usa una sola tabla con clave compuesta:

```text
PK: batchId
SK: entityKey
```

Ejemplos:

```text
batchId = <uuid>
entityKey = BATCH
```

```text
batchId = <uuid>
entityKey = INVOICE#0001-00000001
```

Las consultas por lote deben usar `Query`; evitar `Scan` para este flujo.

## Estructura

```text
.
├── template.yaml
├── samconfig.toml
├── README.md
├── functions/
│   ├── api/
│   │   ├── app.py
│   │   └── requirements.txt
│   ├── parser/
│   │   ├── app.py
│   │   └── requirements.txt
│   └── validator/
│       ├── app.py
│       └── requirements.txt
├── layers/
│   └── common/
│       └── python/
│           └── common/
│               ├── __init__.py
│               ├── config.py
│               ├── dynamodb.py
│               ├── responses.py
│               └── afip_mock.py
├── web/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── events/
│   ├── api-create-upload-url.json
│   ├── api-get-batch.json
│   ├── api-get-invoices.json
│   ├── s3-object-created.json
│   └── sqs-invoice-batch.json
└── scripts/
    ├── deploy.sh
    └── sync-web.sh
```

La carpeta heredada `layer/python/` no se reutiliza: contenia dependencias vendorizadas como `boto3`, `botocore`, `requests` y `urllib3`. La capa nueva contiene solo codigo propio compartido.

## Requisitos

- AWS SAM CLI
- AWS CLI con credenciales configuradas
- Python 3.12, o Docker para compilar con el runtime correcto
- Docker para `sam build --use-container` y ejecucion local con SAM

## Comandos

Build:

```bash
sam build
```

Si no tenes Python 3.12 instalado localmente, usá Docker con SAM:

```bash
sam build --use-container
```

Deploy guiado:

```bash
sam deploy --guided
```

El script de deploy ya compila con Docker:

```bash
./scripts/deploy.sh
```

## Pruebas locales

Verificar que Docker este corriendo:

```bash
docker ps
```

Validar el template:

```bash
sam validate
```

Compilar usando contenedor SAM:

```bash
sam build --use-container
```

Invoke local de la API:

```bash
sam local invoke ApiFunction -e events/api-create-upload-url.json
sam local invoke ApiFunction --event events/api-get-batch.json
sam local invoke ApiFunction --event events/api-get-invoices.json
```

Invoke local de eventos asincronicos:

```bash
sam local invoke ParserFunction --event events/s3-object-created.json
sam local invoke ValidatorFunction --event events/sqs-invoice-batch.json
```

Levantar API local:

```bash
sam local start-api
curl -X POST http://localhost:3000/batches/upload-url \
  -H 'Content-Type: application/json' \
  -d '{"fileName":"lote-facturas-afip.xlsx"}'
```

`sam local` ejecuta las Lambdas en Docker, pero no crea S3, SQS ni DynamoDB localmente. Para probar esos servicios sin AWS real haria falta LocalStack, que no vamos a implementar por ahora.

Sincronizar el sitio estatico luego del deploy:

```bash
./scripts/sync-web.sh <web-bucket-name>
```

El Excel no pasa por API Gateway: el frontend pide una URL prefirmada y sube el archivo directo al bucket privado de uploads.
