# OpsCentral — Unified SOC Dashboard

<div align="center">
  <img src="assets/banner.svg" width="100%" />
</div>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-Python-00b4d8?style=flat-square" alt="FastAPI">
  <img src="https://img.shields.io/badge/Grafana-Dashboards-F46800?style=flat-square" alt="Grafana">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
</p>

Full-stack Security Operations Center dashboard aggregating security alerts from SIEM/Splunk and OCI infrastructure metrics into a unified Grafana visualization platform. One pane of glass across cloud posture, compliance, and active alerts.

## What It Does

- Aggregates alerts from multiple sources — SIEM, OCI, internal systems
- Monitors OCI infrastructure health: compute, network, storage
- Tracks compliance against CIS OCI Benchmark and NIST 800-53
- Visualizes cost trends and budget tracking in real time
- Delivers updates via Grafana dashboards with Prometheus metrics

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   OCI APIs      │     │  SIEM/Splunk    │     │ Internal Apps   │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         └───────────────┬───────┴───────────────────────┘
                         ▼
              ┌─────────────────────┐
              │   FastAPI Backend   │
              │   (Alert Aggregator)│
              └──────────┬──────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │PostgreSQL│   │  Redis   │   │Prometheus│
   │(History) │   │ (Cache)  │   │(Metrics) │
   └──────────┘   └──────────┘   └──────────┘
                         ▼
              ┌─────────────────────┐
              │  Grafana Dashboard  │
              └─────────────────────┘
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | FastAPI + Python 3.11 | Async REST API |
| Task Queue | Celery + Redis | Background collection |
| Database | PostgreSQL 15 | Alert/compliance history |
| Metrics | Prometheus | Time-series metrics |
| Visualization | Grafana OSS 10 | Dashboards and alerting |
| Container | Docker Compose | Deployment orchestration |
| Cloud | OCI SDK | Infrastructure monitoring |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OCI CLI configured (optional — uses mock data otherwise)
- 4GB RAM minimum

```bash
cd opscentral
cp .env.example .env
# Edit .env with your credentials

docker-compose up -d

# Verify
curl http://localhost:8000/api/v1/health
open http://localhost:3000  # Grafana (admin/admin)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Service health |
| `/api/v1/alerts` | GET | List alerts (paginated) |
| `/api/v1/alerts` | POST | Create alert |
| `/api/v1/alerts/{id}/acknowledge` | POST | Acknowledge alert |
| `/api/v1/alerts/summary` | GET | Alert counts by severity |
| `/api/v1/infrastructure/compute` | GET | OCI compute instances |
| `/api/v1/infrastructure/health` | GET | Overall health score |
| `/api/v1/compliance/score` | GET | Compliance percentage |
| `/api/v1/cost/summary` | GET | Current period costs |
| `/metrics` | GET | Prometheus metrics |

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | Required |
| `API_KEY` | API authentication key | Optional |
| `OCI_TENANCY_OCID` | OCI tenancy OCID | Optional |
| `OCI_COMPARTMENT_OCID` | OCI compartment to monitor | Optional |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | Required |
| `LOG_LEVEL` | Logging verbosity | INFO |

### OCI Authentication

1. **Config file** — Mount `~/.oci/config` into container
2. **Instance Principal** — Deploy on OCI compute with dynamic group
3. **Mock mode** — Leave OCI variables unset for demo data

## Dashboard Panels

1. **Infrastructure Health Score** — Gauge (0–100) based on instance availability
2. **Compliance Score** — CIS/NIST compliance percentage
3. **Open Alerts by Severity** — Critical/High/Medium/Low breakdown
4. **Current Month Cost** — OCI spend tracking
5. **CPU/Memory Utilization** — Time series by instance
6. **Recent Alerts Table** — Latest security events

## Deployment

```bash
# OCI Free Tier (VM.Standard.E4.Flex, 1 OCPU, 8GB)
# Install Docker, clone repo, configure Instance Principal auth
docker-compose up -d
```

Estimated cost: $0–43/month (Free Tier eligible)

## Security

- API key authentication on all endpoints
- No hardcoded credentials — env vars or Vault
- Network isolation via Docker networks
- CORS restricted to Grafana origin
- Input validation on all endpoints

## Development

```bash
pip install -r requirements.txt
uvicorn src.opscentral.main:app --reload
celery -A src.opscentral.tasks worker --loglevel=info
pytest tests/ -v
```

## Prometheus Metrics

| Metric | Description |
|--------|-------------|
| `opscentral_health_score` | Infrastructure health (0–100) |
| `opscentral_alerts_by_severity` | Open alert counts |
| `opscentral_compliance_score` | Compliance percentage |
| `opscentral_cost_current_month` | Current spend |

## License

MIT — see LICENSE for details.

## Author

**Daniel Gregg Jr** — Cloud Infrastructure Engineer
- Portfolio: [daniel-eportfolio.web.app](https://daniel-eportfolio.web.app)
- LinkedIn: [linkedin.com/in/daniel-sin-1881ske89](https://linkedin.com/in/daniel-sin-1881ske89)
