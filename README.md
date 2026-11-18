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

## Evidências de qualidade

Execução `workflow_dispatch` concluída com sucesso em 17/11/2026: [run 44119565683](https://github.com/douradorobert-pos-fiap-project/os-service/actions/runs/44119565683). O workflow reportou 67 testes aprovados e 93,18% de cobertura. O artifact `quality-reports-os-service` inclui `coverage.xml` e JUnit.

Configuração e secrets devem vir do ambiente/Kubernetes; use `k8s/secret.example.yaml` apenas como modelo. Pull requests executam qualidade e build Docker local, sem publicar ou acessar a AWS. O workflow publica a imagem por SHA e resolve seu digest, sincroniza o Secret, executa `alembic upgrade head` e somente então atualiza o Deployment quando iniciado manualmente por `workflow_dispatch` no environment `sandbox`.

## Configuração do sandbox

GitHub Variables:

```text
AWS_REGION
EKS_CLUSTER_NAME
RDS_ENDPOINT
DB_PORT
OS_DATABASE
OS_DATABASE_USERNAME
```

GitHub Secrets:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
OS_DB_PASSWORD
NEW_RELIC_LICENSE_KEY
```

`scripts/sync-k8s-secrets.sh` monta `DATABASE_URL` com usuário e senha percent-encoded e atualiza `os-service-secrets` sem gravar o manifesto renderizado. As credenciais temporárias AWS também são atualizadas no Secret para acesso a SQS. Nunca habilite `set -x` nesse fluxo.

O Job `k8s/migration-job.yaml` executa dentro do EKS e alcança o RDS privado. Em ambiente `sandbox`, Alembic rejeita a execução se `DATABASE_URL` não estiver presente; o endereço de desenvolvimento do `alembic.ini` permanece somente como conveniência local.
