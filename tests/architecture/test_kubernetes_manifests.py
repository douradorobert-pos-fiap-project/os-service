from pathlib import Path

import yaml
from kubernetes_validate import validate

ROOT = Path(__file__).resolve().parents[2]
K8S = ROOT / "k8s"
SERVICE = "os-service"
EXPECTED_FILES = {
    "deployment.yaml",
    "service.yaml",
    "configmap.yaml",
    "hpa.yaml",
    "secret.example.yaml",
    "migration-job.yaml",
}


def documents(name):
    return list(yaml.safe_load_all((K8S / name).read_text()))


def test_required_manifests_exist_and_use_oficina_namespace():
    assert {path.name for path in K8S.glob("*.yaml")} == EXPECTED_FILES
    for name in EXPECTED_FILES:
        for document in documents(name):
            assert document["metadata"]["namespace"] == "oficina"


def test_manifests_match_bundled_kubernetes_schema():
    for name in EXPECTED_FILES:
        for document in documents(name):
            assert validate(document, desired_version="1.30.0", strict=True)


def test_deployment_is_immutable_non_root_and_operationally_bounded():
    deployment = documents("deployment.yaml")[0]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert "@sha256:" in container["image"]
    assert ":latest" not in container["image"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert container["resources"]["requests"].keys() == {"cpu", "memory"}
    assert container["resources"]["limits"].keys() == {"cpu", "memory"}
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"


def test_service_hpa_and_configuration_are_service_scoped():
    service = documents("service.yaml")[0]
    hpa = documents("hpa.yaml")[0]
    config = documents("configmap.yaml")[0]
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["selector"]["app.kubernetes.io/name"] == SERVICE
    assert hpa["spec"]["scaleTargetRef"]["name"] == SERVICE
    assert hpa["spec"]["minReplicas"] >= 2
    assert hpa["spec"]["maxReplicas"] >= hpa["spec"]["minReplicas"]
    assert not any(
        "SECRET" in key or "TOKEN" in key or "PASSWORD" in key for key in config["data"]
    )


def test_secret_example_contains_placeholders_only():
    secret = documents("secret.example.yaml")[0]
    assert secret["kind"] == "Secret"
    assert secret["stringData"]
    assert set(secret["stringData"].values()) == {"REPLACE_ME"}


def test_sql_service_has_isolated_migration_job():
    job = documents("migration-job.yaml")[0]
    assert job["kind"] == "Job"
    assert job["metadata"]["name"] == f"{SERVICE}-migration"
    assert job["spec"]["template"]["spec"]["restartPolicy"] == "Never"
    assert job["spec"]["template"]["spec"]["containers"][0]["args"] == [
        "alembic",
        "upgrade",
        "head",
    ]
