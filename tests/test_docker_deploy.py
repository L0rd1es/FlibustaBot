from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_pulls_ghcr_image_and_mounts_data():
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ghcr.io/crearec/crea-flibusta-bot" in compose
    assert "IMAGE_TAG" in compose
    assert "./data:/app/data" in compose
    assert "DATA_DIR" in compose
    assert "\n  build:" not in compose
    assert not any(line.strip().startswith("build:") for line in compose.splitlines())


def test_cicd_workflow_publishes_to_ghcr_and_deploys_over_ssh():
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(encoding="utf-8")

    assert "secrets.GHCR_USERNAME" in workflow
    assert "secrets.GHCR_TOKEN" in workflow
    assert "GITHUB_TOKEN" not in workflow
    assert "ghcr.io/crearec/crea-flibusta-bot" in workflow
    assert "tailscale/github-action" in workflow
    assert "tag:ci" in workflow
    assert "docker compose pull" in workflow
    assert "docker compose up -d" in workflow
    assert "docker-compose.yml" in workflow
    assert "scripts/deploy.sh" not in workflow
    assert "export IMAGE_TAG=" in workflow
