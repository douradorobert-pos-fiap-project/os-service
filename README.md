# OS Service

Microsserviço proprietário da ordem de serviço, cliente/veículo, histórico e process manager da Saga. Persiste em PostgreSQL próprio e integra por Outbox/Inbox e SQS/ElasticMQ.

## Executar e validar

```bash
poetry install
poetry run uvicorn src.api.main:app --reload --port 8001
poetry run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
bash scripts/quality.sh
```

Swagger: `http://localhost:8001/docs`; OpenAPI: `/openapi.json`; health: `/health`. Principais rotas: `/api/v1/customers`, `/api/v1/vehicles` e `/api/v1/service-orders`.

Configuração e secrets devem vir do ambiente/Kubernetes; use `k8s/secret.example.yaml` apenas como modelo. O pipeline em `.github/workflows/pipeline.yml` bloqueia imagem/deploy se qualidade falhar e publica imagem imutável pelo SHA.
