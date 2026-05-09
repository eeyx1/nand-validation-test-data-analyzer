from fastapi.testclient import TestClient

from app.main import RECORDS, analyze_records, app, build_signoff_package


client = TestClient(app)


def test_analysis_contains_process_capability_and_signoff_controls():
    analysis = analyze_records(RECORDS)

    assert analysis["process_capability"]["read_latency"]["cpk"] is not None
    assert analysis["process_capability"]["write_latency"]["cpk"] is not None
    assert analysis["quality_gate_policy"] == "nand-validation-gate-v2"
    assert analysis["signoff_checklist"]


def test_signoff_package_tracks_approvers_and_release_risk():
    analysis = analyze_records(RECORDS)
    package = build_signoff_package(analysis)

    assert package["package_id"].startswith("SIGNOFF-")
    assert package["decision"] in {"approve", "conditional-approve", "hold"}
    assert "Firmware Lead" in package["required_approvers"]
    assert package["release_risk_register"]


def test_signoff_endpoint_returns_industrial_release_package():
    response = client.get("/api/signoff-package")

    assert response.status_code == 200
    payload = response.json()

    assert payload["quality_gate_policy"] == "nand-validation-gate-v2"
    assert payload["signoff_package"]["required_approvers"]
