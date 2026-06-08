# Práctica 3.3 — Flujo Serverless con AWS SAM CLI

**Cloud Computing — Licenciatura en Sistemas, UNRN**  
**Integrantes:** Acosta Tomás, Antrichipay Daniel, Cabeza Franco

---

## Descripción

Este proyecto replica el flujo de consulta de facturas implementado manualmente en la Práctica 3.2, utilizando AWS SAM CLI como herramienta de Infrastructure as Code (IaC). El objetivo es exponer una API REST que permita consultar las facturas procesadas almacenadas en la tabla DynamoDB `Invoices`.

## Arquitectura

```
Cliente HTTP → API Gateway (GET /facturas) → Lambda (consultar-facturas-sam) → DynamoDB (Invoices)
```

Los recursos desplegados por SAM son:

- **API Gateway** — Punto de entrada público para las solicitudes de consulta.
- **Lambda Function** — Ejecuta la lógica de consulta sobre DynamoDB usando boto3.
- **IAM** — La función utiliza el rol `LabRole` provisto por AWS Academy.

La tabla DynamoDB `Invoices` no es creada por este stack, sino referenciada desde la práctica anterior. La función accede a ella mediante la variable de entorno `TABLE_NAME`.

## Estructura del proyecto

```
.
├── consultar_facturas/
│   ├── app.py              # Handler de la Lambda
│   └── requirements.txt    # Dependencias Python
├── events/
│   └── event.json          # Evento de prueba para invocación local
├── layer/
│   └── python/             # Dependencias para Lambda Layer
├── tests/                  # Tests unitarios e integración
├── template.yaml           # Infraestructura como código (SAM/CloudFormation)
├── samconfig.toml          # Configuración persistente del deploy
└── README.md
```

## Requisitos previos

- AWS SAM CLI
- AWS CLI con credenciales configuradas (`aws configure`)
- Python 3.12
- Docker (para testing local)

## Comandos

### Instalar dependencias de la Layer

```bash
pip3 install -r consultar_facturas/requirements.txt -t layer/python
```

### Build

```bash
sam build
```

### Deploy

```bash
sam deploy --region us-east-1
```

### Testing local

```bash
sam local invoke ConsultarFacturasFunction --event events/event.json
```

```bash
sam local start-api
curl http://localhost:3000/facturas
```

### Verificar endpoint desplegado

```bash
curl https://m597hu6180.execute-api.us-east-1.amazonaws.com/prod/facturas
```

### Eliminar el stack

```bash
sam delete --stack-name fastapi33
```

## Ventajas de SAM CLI vs. configuración manual en consola

| Aspecto | Consola AWS (Práctica 3.2) | SAM CLI (Práctica 3.3) |
|---|---|---|
| Reproducibilidad | Manual, propensa a errores | Automatizada, idempotente |
| Versionado | No aplica | Código en Git |
| Velocidad de despliegue | Alto tiempo por configuración manual | `sam build && sam deploy` |
| Testing local | No disponible | `sam local invoke` / `sam local start-api` |
| Gestión de recursos | Individual por servicio | Declarativa en `template.yaml` |
| Rollback ante errores | Manual | Automático por CloudFormation |
