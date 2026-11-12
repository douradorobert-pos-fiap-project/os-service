import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {
    "billing_service",
    "execution_service",
    "tech_challenge_fiap_billing",
    "tech_challenge_fiap_execution",
}
SECRET_NAMES = {
    "access_token",
    "api_key",
    "aws_secret_access_key",
    "license_key",
    "password",
    "secret",
}


def python_files():
    return sorted((ROOT / "src").rglob("*.py"))


def test_service_does_not_import_other_bounded_contexts():
    violations = []
    for path in python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        imports += [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        if any(
            forbidden in imported for forbidden in FORBIDDEN for imported in imports
        ):
            violations.append(path.relative_to(ROOT))
    assert violations == []


def test_source_does_not_contain_hardcoded_credentials():
    violations = []
    for path in python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Assign)
                or not isinstance(node.value, ast.Constant)
                or not isinstance(node.value.value, str)
            ):
                continue
            names = [
                target.id.lower()
                for target in node.targets
                if isinstance(target, ast.Name)
            ]
            if any(name in SECRET_NAMES for name in names) and node.value.value.strip():
                violations.append(path.relative_to(ROOT))
    assert violations == []


def test_delivery_files_enforce_non_root_image_and_blocking_quality():
    dockerfile = (ROOT / "Dockerfile").read_text()
    workflow = (ROOT / ".github/workflows/pipeline.yml").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "USER 10001" in dockerfile
    assert "bash scripts/quality.sh" in workflow
    assert "needs: quality" in workflow
    assert "docker build" in workflow
    assert "id-token: write" not in workflow
