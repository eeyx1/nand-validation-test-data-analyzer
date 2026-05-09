# NAND Validation and Semiconductor Test Data Analyzer

This project is an industrial-style validation dashboard for NAND/controller test data. It helps engineers review yield, firmware versions, failing units, outliers, release gates, and validation action items.

## Industry Problem

Validation teams often receive CSV or Excel data from test stations. The data may include:

- unit ID
- lot ID
- firmware version
- pass/fail result
- bin code
- read and write latency
- ECC corrections
- bad block count
- timeout count
- failure category

Manual review is slow and can miss patterns. This project turns test data into release-readiness insight and an action queue.

## Who Would Use It

- NAND validation engineer
- SSD controller validation engineer
- product engineer
- test automation engineer
- firmware engineer comparing versions
- AI/software engineer building internal validation analytics tools

## Industrial Features

### 1. Overall Yield and Pass/Fail Summary

The dashboard calculates:

- total units
- passed units
- failed units
- overall yield

Why it helps industry:

- quickly shows whether a validation batch is healthy
- supports release-review meetings
- gives a simple KPI for engineering managers

### 2. Release Readiness Gate

The app labels the validation batch as:

- `candidate`
- `conditional`
- `hold`

The decision is based on yield and firmware-level risk.

Why it helps industry:

- test data becomes a release decision signal
- engineers can immediately see whether more analysis is required
- it mimics a real validation gate

### 3. Firmware Version Comparison

For each firmware version, the dashboard shows:

- unit count
- yield
- failure count
- average read latency
- average write latency
- release status
- recommended action

Why it helps industry:

- firmware regressions become easier to spot
- release candidates can be compared against weaker versions
- supports controller firmware validation workflows

### 4. Lot-Level Summary

The backend summarizes yield by lot and top failure category.

Why it helps industry:

- separates firmware issues from lot/process issues
- helps teams decide whether failures are isolated or systematic
- supports manufacturing and validation analysis

### 5. Failure Category and Bin Analysis

The app counts failure categories and bin codes.

Examples:

- ECC
- Timeout
- NAND
- Latency
- BIN1/BIN2/BIN3/BIN4

Why it helps industry:

- failure patterns become visible
- dominant failure modes can be prioritized
- supports root-cause triage

### 6. Outlier Detection

The app identifies risky units using:

- read latency z-score
- write latency z-score
- high ECC corrections
- high timeout count
- high bad block count
- failed result

Why it helps industry:

- outlier units can be reviewed before release
- subtle failures can be found even when pass/fail alone is not enough
- supports reliability review and sample selection

### 7. Validation Action Queue

Each high-risk unit receives a practical triage action.

Examples:

- ECC failures -> review NAND margin and read-retry counters
- Timeout failures -> inspect host timeout path and controller reset sequence
- NAND failures -> check bad-block growth and wear-leveling behavior
- Latency failures -> compare FTL garbage-collection pressure

Why it helps industry:

- turns analytics into action
- helps engineers decide what to inspect next
- makes the tool useful beyond charts

### 8. Automated Engineering Report

The app generates a concise validation report including:

- overall yield
- release readiness
- weakest firmware version
- dominant failure category
- recommended review direction

Why it helps industry:

- reduces manual report writing
- supports validation review documentation
- can be extended into PDF/email export

## Industrial v2 Upgrade

### 1. Process Capability Metrics

The analyzer now calculates process capability for read and write latency using configured spec limits. The API returns:

- mean
- sigma
- lower and upper spec limits
- Cp
- Cpk
- capability status

Why it helps industry:

- validation review can judge stability, not only pass/fail
- latency drift becomes measurable against a release specification
- it mirrors how semiconductor and manufacturing teams discuss process health

### 2. Quality Gate Policy

Each summary now includes `quality_gate_policy`: `nand-validation-gate-v2`.

Why it helps industry:

- release decisions can be tied to a named gate policy
- future threshold changes are easier to explain
- interviewers can see governance thinking, not only charting

### 3. Release Signoff Package

The new `/api/signoff-package` endpoint produces a release package with:

- package ID
- release decision
- required approvers
- signoff checklist
- release risk register
- evidence endpoints
- rollback plan
- next experiments

Why it helps industry:

- test analytics become a release decision workflow
- engineers know what evidence is missing before approval
- it connects validation, firmware, reliability, and product engineering teams

### 4. Industrial Delivery Readiness

The project now includes:

- automated tests for process capability, signoff package, and API behavior
- `Dockerfile` for containerized execution
- `.env.example` for model/API configuration
- GitHub Actions CI for repeatable test checks

## Tech Stack

- Python
- FastAPI
- CSV analysis
- Jinja2 templates
- HTML/CSS dashboard
- optional OpenAI Responses API

## Default Model

Default:

```text
gpt-5.4-mini
```

Why:

- calculations are handled locally
- the model is only used for engineering summary wording
- report generation is a repeated workflow where speed matters

For stronger technical synthesis:

```bash
OPENAI_MODEL=gpt-5.4
```

The app still works without an API key using deterministic report generation.

## Project Structure

```text
app/
  main.py                       validation analysis, release gates, report API
  templates/index.html          release-readiness dashboard
  static/styles.css             operational dashboard styling
data/
  nand_validation_sample.csv    sample NAND validation dataset
tests/
  test_industrial_features.py
Dockerfile                      container runtime
.github/workflows/ci.yml        GitHub Actions test workflow
.env.example                    environment variable template
requirements.txt                dependencies
requirements-dev.txt            test dependencies
README.md                       project guide
```

## API Endpoints

- `GET /` opens the dashboard
- `GET /api/summary` returns yield, firmware comparison, failures, outliers, gates, and action queue
- `GET /api/release-readiness` returns release gate result and blockers
- `GET /api/signoff-package` returns approvers, risks, rollback plan, and next experiments
- `GET /api/report` returns an engineering validation report
- `GET /api/units/{unit_id}` returns one unit record
- `GET /health` checks service status

## How To Run

```bash
cd "G:\Ai Project\nand-validation-test-data-analyzer"
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

Open:

```text
http://127.0.0.1:8002
```

If port `8002` is already used:

```bash
uvicorn app.main:app --reload --port 8003
```

Optional:

```bash
set OPENAI_API_KEY=your_key
set OPENAI_MODEL=gpt-5.4-mini
```

## Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests -q
```

## Docker

```bash
docker build -t nand-validation-analyzer .
docker run --rm -p 8002:8002 --env-file .env.example nand-validation-analyzer
```

## Demo Flow

1. Open the dashboard.
2. Show overall yield and release readiness.
3. Compare firmware versions and point out weaker groups.
4. Review failure categories and gating items.
5. Inspect the validation action queue.
6. Generate the validation report.

## Interview Explanation

Say this:

> This project simulates a NAND/controller validation dashboard. It analyzes test CSV data, compares firmware versions, calculates yield, detects outlier units, generates release-readiness gates, and produces an engineering report. The goal is to reduce manual Excel review and help validation teams focus on the units and firmware versions that need attention.

## Resume Bullet

Created a NAND validation test data analyzer using Python and FastAPI to calculate yield, compare firmware versions, detect outlier devices, evaluate release readiness, and generate automated engineering summaries for semiconductor validation workflows.

## Production Hardening Ideas

- add CSV upload for user datasets
- add persistent database storage
- add Plotly charts and control charts
- add firmware A/B regression comparison
- add pass/fail threshold configuration
- add exportable validation report
- persist signoff packages and approval history
