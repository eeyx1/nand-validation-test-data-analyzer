from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "nand_validation_sample.csv"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
QUALITY_GATE_POLICY = "nand-validation-gate-v2"
LATENCY_SPEC_LIMITS = {
    "read_latency_us": {"lower": 0.0, "upper": 125.0},
    "write_latency_us": {"lower": 0.0, "upper": 260.0},
}

app = FastAPI(title="NAND Validation Test Data Analyzer", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def to_float(value: str) -> float:
    return float(value.strip())


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            records.append(
                {
                    "unit_id": row["unit_id"],
                    "lot_id": row["lot_id"],
                    "firmware_version": row["firmware_version"],
                    "test_stage": row["test_stage"],
                    "temperature_c": to_float(row["temperature_c"]),
                    "read_latency_us": to_float(row["read_latency_us"]),
                    "write_latency_us": to_float(row["write_latency_us"]),
                    "ecc_corrections": int(row["ecc_corrections"]),
                    "bad_block_count": int(row["bad_block_count"]),
                    "timeout_count": int(row["timeout_count"]),
                    "bin_code": row["bin_code"],
                    "result": row["result"],
                    "failure_category": row["failure_category"],
                }
            )
    return records


RECORDS = load_records()


def pass_rate(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    passed = sum(1 for record in records if record["result"] == "PASS")
    return round(passed / len(records) * 100, 2)


def group_by(records: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record[key])].append(record)
    return dict(grouped)


def outlier_score(record: dict[str, Any], stats: dict[str, float]) -> float:
    read_z = 0.0
    write_z = 0.0
    if stats["read_std"] > 0:
        read_z = (record["read_latency_us"] - stats["read_mean"]) / stats["read_std"]
    if stats["write_std"] > 0:
        write_z = (record["write_latency_us"] - stats["write_mean"]) / stats["write_std"]

    score = max(read_z, write_z)
    score += 0.35 if record["ecc_corrections"] >= 170 else 0
    score += 0.30 if record["timeout_count"] >= 2 else 0
    score += 0.25 if record["bad_block_count"] >= 18 else 0
    return round(score, 2)


def triage_action(record: dict[str, Any]) -> str:
    category = record["failure_category"]
    if category == "ECC":
        return "Review NAND margin, read-retry counters, and ECC trend against lot baseline"
    if category == "Timeout":
        return "Inspect host timeout path, controller reset sequence, and workload timing"
    if category == "NAND":
        return "Check bad-block growth, erase-cycle distribution, and wear-leveling behavior"
    if category == "Latency":
        return "Compare FTL garbage-collection pressure and free-block availability"
    return "Keep unit in baseline review and compare against same firmware cohort"


def firmware_risk(item: dict[str, Any]) -> dict[str, Any]:
    if item["yield_percent"] >= 95 and item["failures"] == 0:
        status = "release-candidate"
        action = "Candidate for release review after regression checks"
    elif item["yield_percent"] >= 85:
        status = "conditional"
        action = "Review failures before release approval"
    else:
        status = "hold"
        action = "Hold release and run focused failure analysis"
    return {**item, "release_status": status, "recommended_action": action}


def process_capability(values: list[float], lower_spec: float, upper_spec: float) -> dict[str, Any]:
    avg = mean(values)
    sigma = pstdev(values) or 1.0
    cp = (upper_spec - lower_spec) / (6 * sigma)
    cpu = (upper_spec - avg) / (3 * sigma)
    cpl = (avg - lower_spec) / (3 * sigma)
    cpk = min(cpu, cpl)
    if cpk >= 1.33:
        status = "capable"
    elif cpk >= 1.0:
        status = "watch"
    else:
        status = "not-capable"
    return {
        "mean": round(avg, 2),
        "sigma": round(sigma, 2),
        "lower_spec": lower_spec,
        "upper_spec": upper_spec,
        "cp": round(cp, 2),
        "cpk": round(cpk, 2),
        "status": status,
    }


def build_signoff_checklist(summary: dict[str, Any]) -> list[dict[str, Any]]:
    hold_versions = [
        item["firmware_version"]
        for item in summary["firmware_summary"]
        if item["release_status"] == "hold"
    ]
    read_capable = summary["process_capability"]["read_latency"]["cpk"] >= 1.0
    write_capable = summary["process_capability"]["write_latency"]["cpk"] >= 1.0
    return [
        {
            "control": "Overall validation yield >= 90%",
            "status": "pass" if summary["overall_yield_percent"] >= 90 else "fail",
            "evidence": f"{summary['overall_yield_percent']}% yield",
        },
        {
            "control": "No firmware version in hold state",
            "status": "pass" if not hold_versions else "fail",
            "evidence": ", ".join(hold_versions) if hold_versions else "all firmware groups are releasable or conditional",
        },
        {
            "control": "Read latency process capability Cpk >= 1.0",
            "status": "pass" if read_capable else "fail",
            "evidence": f"Cpk {summary['process_capability']['read_latency']['cpk']}",
        },
        {
            "control": "Write latency process capability Cpk >= 1.0",
            "status": "pass" if write_capable else "fail",
            "evidence": f"Cpk {summary['process_capability']['write_latency']['cpk']}",
        },
        {
            "control": "Top outlier units assigned to validation action queue",
            "status": "pass" if summary["action_queue"] else "watch",
            "evidence": f"{len(summary['action_queue'])} queued unit(s)",
        },
    ]


def build_signoff_package(summary: dict[str, Any]) -> dict[str, Any]:
    decision = {
        "candidate": "approve",
        "conditional": "conditional-approve",
        "hold": "hold",
    }[summary["release_readiness"]]
    required_approvers = ["Firmware Lead", "NAND Validation Lead", "Reliability Engineer"]
    if decision != "approve":
        required_approvers.append("Product Engineering Manager")
    risk_register = [
        {
            "risk": item,
            "owner": "Validation Lead" if "yield" in item.lower() else "Firmware/NAND Joint Review",
            "mitigation": "Run focused A/B validation and attach evidence before release signoff.",
        }
        for item in summary["gating_items"]
    ]
    return {
        "package_id": f"SIGNOFF-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "release_readiness": summary["release_readiness"],
        "quality_gate_policy": QUALITY_GATE_POLICY,
        "required_approvers": required_approvers,
        "signoff_checklist": summary["signoff_checklist"],
        "release_risk_register": risk_register,
        "evidence_endpoints": ["/api/summary", "/api/release-readiness", "/api/report"],
        "rollback_plan": [
            "Keep previous firmware image available for affected lots.",
            "Block release if new validation data adds a hold firmware group.",
            "Require post-release telemetry watch for ECC, timeout, and latency drift.",
        ],
        "next_experiments": [
            "Re-run outlier units at hot and nominal temperature corners.",
            "Compare weakest firmware version against the current release candidate.",
            "Split failure review by NAND lot to separate firmware regression from lot effect.",
        ],
    }


def analyze_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    read_values = [record["read_latency_us"] for record in records]
    write_values = [record["write_latency_us"] for record in records]
    stats = {
        "read_mean": mean(read_values),
        "read_std": pstdev(read_values) or 1.0,
        "write_mean": mean(write_values),
        "write_std": pstdev(write_values) or 1.0,
    }

    firmware_summary = []
    for firmware, items in sorted(group_by(records, "firmware_version").items()):
        firmware_summary.append(
            firmware_risk(
                {
                    "firmware_version": firmware,
                    "units": len(items),
                    "yield_percent": pass_rate(items),
                    "failures": sum(1 for item in items if item["result"] == "FAIL"),
                    "avg_read_latency_us": round(mean(item["read_latency_us"] for item in items), 2),
                    "avg_write_latency_us": round(mean(item["write_latency_us"] for item in items), 2),
                }
            )
        )

    lot_summary = []
    for lot_id, items in sorted(group_by(records, "lot_id").items()):
        lot_summary.append(
            {
                "lot_id": lot_id,
                "units": len(items),
                "yield_percent": pass_rate(items),
                "top_failure": Counter(item["failure_category"] for item in items if item["result"] == "FAIL").most_common(1)[0][0]
                if any(item["result"] == "FAIL" for item in items)
                else "None",
            }
        )

    failure_counts = Counter(record["failure_category"] for record in records if record["result"] == "FAIL")
    bin_counts = Counter(record["bin_code"] for record in records)

    outliers = []
    for record in records:
        score = outlier_score(record, stats)
        if score >= 1.45 or record["result"] == "FAIL":
            outliers.append({**record, "outlier_score": score, "triage_action": triage_action(record)})
    outliers.sort(key=lambda item: item["outlier_score"], reverse=True)

    hold_firmware = [item for item in firmware_summary if item["release_status"] == "hold"]
    conditional_firmware = [item for item in firmware_summary if item["release_status"] == "conditional"]
    gating_items = []
    if pass_rate(records) < 90:
        gating_items.append("Overall yield is below 90% release threshold")
    if hold_firmware:
        gating_items.append("At least one firmware version is below release threshold")
    if len(outliers) >= 3:
        gating_items.append("Multiple high-risk outlier units require review")
    if failure_counts:
        top_failure = failure_counts.most_common(1)[0][0]
        gating_items.append(f"Dominant failure category is {top_failure}")

    release_readiness = "hold" if hold_firmware or pass_rate(records) < 90 else "conditional" if conditional_firmware else "candidate"

    summary = {
        "total_units": len(records),
        "overall_yield_percent": pass_rate(records),
        "passed_units": sum(1 for record in records if record["result"] == "PASS"),
        "failed_units": sum(1 for record in records if record["result"] == "FAIL"),
        "release_readiness": release_readiness,
        "quality_gate_policy": QUALITY_GATE_POLICY,
        "gating_items": gating_items or ["No major release blockers detected in this sample"],
        "control_limits": {
            "read_latency_upper_us": round(stats["read_mean"] + 2 * stats["read_std"], 2),
            "write_latency_upper_us": round(stats["write_mean"] + 2 * stats["write_std"], 2),
        },
        "process_capability": {
            "read_latency": process_capability(
                read_values,
                LATENCY_SPEC_LIMITS["read_latency_us"]["lower"],
                LATENCY_SPEC_LIMITS["read_latency_us"]["upper"],
            ),
            "write_latency": process_capability(
                write_values,
                LATENCY_SPEC_LIMITS["write_latency_us"]["lower"],
                LATENCY_SPEC_LIMITS["write_latency_us"]["upper"],
            ),
        },
        "firmware_summary": firmware_summary,
        "lot_summary": lot_summary,
        "failure_counts": dict(failure_counts),
        "bin_counts": dict(bin_counts),
        "outliers": outliers[:8],
        "action_queue": outliers[:5],
    }
    summary["signoff_checklist"] = build_signoff_checklist(summary)
    return summary


def get_openai_client() -> Any | None:
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return None
    return OpenAI()


def fallback_report(summary: dict[str, Any]) -> str:
    failures = summary["failure_counts"]
    top_failure = max(failures, key=failures.get) if failures else "None"
    weakest_fw = min(
        summary["firmware_summary"],
        key=lambda item: item["yield_percent"],
    )
    return (
        f"Overall validation yield is {summary['overall_yield_percent']}% across "
        f"{summary['total_units']} units. Release readiness is {summary['release_readiness']}. "
        f"The weakest firmware group is "
        f"{weakest_fw['firmware_version']} at {weakest_fw['yield_percent']}% yield. "
        f"The most frequent failure category is {top_failure}. Review the outlier units first, "
        "then compare latency and ECC behavior across firmware versions before approving release."
    )


def generate_report(summary: dict[str, Any]) -> str:
    client = get_openai_client()
    if client is None:
        return fallback_report(summary)

    prompt = {
        "task": (
            "Write a concise NAND validation engineering summary. Explain overall yield, "
            "weak firmware versions, main failure categories, and next validation actions. "
            "Do not invent data beyond the JSON."
        ),
        "summary": summary,
    }
    response = client.responses.create(model=DEFAULT_MODEL, input=json.dumps(prompt))
    return response.output_text.strip()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    summary = analyze_records(RECORDS)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"model_name": DEFAULT_MODEL, "unit_count": summary["total_units"]},
    )


@app.get("/api/summary")
async def summary() -> JSONResponse:
    analysis = analyze_records(RECORDS)
    return JSONResponse({"summary": analysis, "model_name": DEFAULT_MODEL})


@app.get("/api/release-readiness")
async def release_readiness() -> JSONResponse:
    analysis = analyze_records(RECORDS)
    return JSONResponse(
        {
            "release_readiness": analysis["release_readiness"],
            "gating_items": analysis["gating_items"],
            "firmware_summary": analysis["firmware_summary"],
            "action_queue": analysis["action_queue"],
        }
    )


@app.get("/api/signoff-package")
async def signoff_package() -> JSONResponse:
    analysis = analyze_records(RECORDS)
    return JSONResponse(
        {
            "quality_gate_policy": QUALITY_GATE_POLICY,
            "signoff_package": build_signoff_package(analysis),
        }
    )


@app.get("/api/report")
async def report() -> JSONResponse:
    analysis = analyze_records(RECORDS)
    return JSONResponse({"report": generate_report(analysis), "summary": analysis})


@app.get("/api/units/{unit_id}")
async def unit_detail(unit_id: str) -> JSONResponse:
    unit = next((record for record in RECORDS if record["unit_id"] == unit_id), None)
    if unit is None:
        return JSONResponse({"error": "Unit not found"}, status_code=404)
    return JSONResponse({"unit": unit})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "quality_gate_policy": QUALITY_GATE_POLICY}
