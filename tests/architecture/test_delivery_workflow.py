import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pipeline.yml"
SYNC = ROOT / "scripts" / "sync-k8s-secrets.sh"


def test_workflow_builds_prs_and_deploys_only_by_manual_dispatch() -> None:
    workflow = WORKFLOW.read_text()

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "environment: sandbox" in workflow
    assert "imageDigest" in workflow


def test_manual_delivery_orders_secret_migration_before_rollout() -> None:
    workflow = WORKFLOW.read_text()

    sync = workflow.index("scripts/sync-k8s-secrets.sh")
    migration = workflow.index("job/os-service-migration")
    wait = workflow.index("wait --for=condition=complete")
    deployment = workflow.index("k8s/deployment.yaml")
    assert sync < migration < wait < deployment


def test_secret_sync_percent_encodes_database_credentials(tmp_path: Path) -> None:
    log = tmp_path / "kubectl.log"
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\0' "$@" >> "${FAKE_KUBECTL_LOG}"
if [[ " $* " == *" create secret "* ]]; then
  printf '%s\\n' 'apiVersion: v1' 'kind: Secret' 'metadata: {name: fake}'
else
  cat >/dev/null
fi
"""
    )
    kubectl.chmod(0o755)
    password = "p@ss:word/%value"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_KUBECTL_LOG": str(log),
        "RDS_ENDPOINT": "sandbox.example.rds.amazonaws.com",
        "DB_PORT": "5432",
        "OS_DATABASE": "os_service_db",
        "OS_DATABASE_USERNAME": "os_service_user",
        "OS_DB_PASSWORD": password,
        "NEW_RELIC_LICENSE_KEY": "new-relic-test",
        "AWS_ACCESS_KEY_ID": "access-test",
        "AWS_SECRET_ACCESS_KEY": "secret-test",
        "AWS_SESSION_TOKEN": "session-test",
    }

    result = subprocess.run(
        ["bash", str(SYNC)], env=env, text=True, capture_output=True, check=False
    )
    arguments = log.read_bytes().split(b"\0")
    expected_url = (
        "postgresql+psycopg://os_service_user:"
        "p%40ss%3Aword%2F%25value@sandbox.example.rds.amazonaws.com:5432/"
        "os_service_db"
    )

    assert result.returncode == 0
    assert f"--from-literal=DATABASE_URL={expected_url}".encode() in arguments
    assert password not in result.stdout
    assert password not in result.stderr
