# Project Caelum-EO

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-brightgreen.svg)](https://www.python.org/)
[![Kafka](https://img.shields.io/badge/Apache-Kafka-231F20.svg?logo=apache-kafka)](https://kafka.apache.org/)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.4-336791.svg?logo=postgresql)](https://postgis.net/)
[![Deck.gl](https://img.shields.io/badge/Deck.gl-9.0-black.svg)](https://deck.gl/)

> **Caelum** _(Latin: sky, the heavens)_ — Continuous automated geospatial intelligence (GEOINT) pipeline for detecting, classifying, and mapping infrastructure build-out using Earth Observation AI foundation models.

Repository: **`github.com/FranekJemiolo/Caelum-EO`**

---

## 🛰️ Architecture Overview

Project Caelum-EO automates the end-to-end intelligence cycle from spaceborne sensor ingest to interactive visual analyst tooling:

```mermaid
flowchart TD
    subgraph Spaceborne Sensoring
        S1[Sentinel-1 SAR GRD]
        S2[Sentinel-2 Optical L2A]
        CDSE[Copernicus Data Space STAC API]
        S1 --> CDSE
        S2 --> CDSE
    end

    subgraph Ingestion & ETL
        Poller[STAC Ingestion Worker]
        Kafka[Kafka Topic: geoint-stac-ingest]
        Consumer[Alignment & Masking Consumer]
        CDSE -->|Poll Geofences| Poller
        Poller -->|Stream Item Payloads| Kafka
        Kafka --> Consumer
        Consumer -->|Windowed COG Read & Reprojection| Align[Spatially Aligned 6-Band Tensors]
    end

    subgraph Two-Stage Neural Inference
        Prithvi[Stage 1: NASA/IBM Prithvi-EO-2.0 300M<br/>Temporal Change Detection]
        ChangeMask[Binary Change Mask<br/>1 = Structural Anomaly]
        ChipExtractor[Spatial Cluster & BBox Extractor]
        YOLO[Stage 2a: YOLOv8-OBB<br/>Infrastructure Classification]
        GeoSAM[Stage 2b: GeoSAM Zero-Shot<br/>Roofline & Perimeter Segmentation]

        Align --> Prithvi
        Prithvi --> ChangeMask
        ChangeMask --> ChipExtractor
        ChipExtractor --> YOLO
        ChipExtractor --> GeoSAM
    end

    subgraph Spatial Store & Analyst Presentation
        PostGIS[(PostgreSQL + PostGIS<br/>infrastructure_detections)]
        Web[Deck.gl + MapLibre React Frontend<br/>Temporal Timeline Scrubber]

        YOLO -->|Class & Confidence| PostGIS
        GeoSAM -->|GeoJSON Polygon EPSG:4326| PostGIS
        PostGIS -->|Tile Queries & Filtering| Web
    end
```

---

## 🛠️ Tech Stack

- **Message Broker & ETL:** Python 3.11, Apache Kafka, `pystac-client`, `rasterio`, `xarray`, `shapely`
- **Machine Learning (Temporal Detection):** Hugging Face `ibm-nasa-geospatial/Prithvi-EO-2.0-300M` via PyTorch & MMSegmentation
- **Machine Learning (Classification & Vectorization):** YOLOv8-OBB (Oriented Bounding Boxes), GeoSAM (Segment Anything for EO)
- **Database:** PostgreSQL 16 with PostGIS extension (`GIST` indexed)
- **Frontend / Visualization:** React, Deck.gl `GeoJsonLayer`, MapLibre GL
- **Containerization:** Docker & Docker Compose

---

## 📁 Repository Structure

```
.
├── JOURNAL.md                      # Engineering journal & decision logs
├── README.md                       # Main project documentation
├── docker-compose.yml              # Local orchestration (PostGIS, MinIO, Redpanda, Workers, Frontend)
├── pyproject.toml                  # Python package configuration (3.11 target, ruff, mypy)
├── .pre-commit-config.yaml         # Pre-commit quality gates (ruff, mypy, prettier, eslint)
├── .github/workflows/ci.yml        # GitHub Actions CI matrix
├── docs/                           # Architecture, specs & design documents
│   ├── ARCHITECTURE.md             # System design & data flow specification
│   ├── ETL_PIPELINE.md             # STAC windowed range reads & cloud masking
│   ├── STORAGE_TOPOLOGY.md         # MinIO / S3 bucket lifecycle
│   ├── ML_SPEC.md                  # Prithvi-EO-2.0, YOLOv8-OBB & GeoSAM tensor layouts
│   ├── DATA_MODEL.md               # PostGIS 15+ schema & spatial indexes
│   ├── CI_CD_PIPELINE.md           # Pre-commit & GitHub Actions specifications
│   ├── ANALYST_UI_SPEC.md          # Multi-Temporal Inspector & HITL review wireframes
│   └── API_REFERENCE.md            # OpenAPI schema & endpoint reference
├── scripts/
│   ├── generate_mock_data.py       # Deterministic multi-band GeoTIFF & chip generator
│   └── run_local.sh                # End-to-end local bootstrap runner
├── src/
│   ├── api/                        # FastAPI triage, zone aggregation & review service
│   ├── db/                         # PostGIS database migrations & seed fixtures
│   ├── etl/                        # Streaming COG range reader & raster alignment
│   ├── inference/                  # Prithvi MAE, YOLOv8 classifier & polygonizer
│   └── frontend/                   # React + TypeScript + Deck.gl + TailwindCSS UI
└── tests/                          # Automated Pytest suite (29 tests)
```

---

## 🚀 Quickstart & Local Execution

### 1. One-Command Local Bootstrap

Boots Docker infrastructure (PostGIS, MinIO, Redpanda), generates synthetic Sentinel-2 imagery, triggers ML vectorization, and launches the Deck.gl WebGL Analyst UI on `http://localhost:3000`:

```bash
./scripts/run_local.sh
```

To run in standalone headless verification mode without starting Docker:

```bash
./scripts/run_local.sh --skip-docker --no-dev
```

### 2. Run Quality Gates & Tests

```bash
# Run all pre-commit hooks (ruff, mypy, prettier, eslint)
pre-commit run --all-files

# Execute complete backend test suite (29 passed)
pytest tests/ services/ingestion/tests services/inference/tests -v

# Run frontend lint and production build
cd src/frontend && npm run lint && npm run build
```

### 3. Launch FastAPI Backend

```bash
python -m src.api.main
# Interactive OpenAPI Documentation: http://localhost:8000/docs
```

---

## 🛰️ Analyst UI & HITL Triage Features

- **Dual Map Modes:** High-resolution bounding boxes/roofline polygons (Deck.gl `GeoJsonLayer`) and Regional Zone Density / Hotspot choropleth layer.
- **Priority Triage Hotlist:** Collapsible right-hand drawer ranking anomalies by dynamic priority score ($P-0$ to $P-100$) with smooth `flyTo` camera transitions.
- **Multi-Temporal Swipe Inspector:** Side-by-side $T_0$ vs. $T_1$ comparison slider with instant AI change mask toggle (`M` key) and solar/cloud metadata badges.
- **Human-in-the-Loop Review Modal:** Fast triage with keyboard hotkeys:
  - `[V]` Verify Correct
  - `[M]` Reclassify infrastructure category
  - `[F]` Mark anomaly as False Positive
  - `[Space]` Next alert in queue
  - Commits to `PATCH /api/v1/detections/:id/review` and logs audit records to `review_audit_log`.

---

## 🔒 Security, Authentication & Role-Based Access Control (RBAC)

Project Caelum-EO enforces OAuth2 Password Flow with signed JWT Bearer tokens and strict role-based access control (RBAC).

### Default Operator Credentials

| Operator Username   | Default Passphrase     | Clearance Role | Permissions & Capabilities                                |
| :------------------ | :--------------------- | :------------- | :-------------------------------------------------------- |
| **`admin`**         | `caelum_admin_2026!`   | `admin`        | Full operational system control & review reclassification |
| **`analyst_viper`** | `caelum_analyst_2026!` | `analyst`      | Human-in-the-Loop triage verification (`PATCH /review`)   |
| **`viewer_01`**     | `caelum_viewer_2026!`  | `viewer`       | Read-only access to maps, zones, and intelligence queue   |

### API Security & RBAC Enforcement

- **Protected Endpoints:** All `/api/v1/detections`, `/api/v1/zones/summary`, `/api/v1/triage/queue`, and `/api/v1/detections/:id/imagery` require a valid JWT Bearer header (`Authorization: Bearer <token>`).
- **Review Restriction:** `PATCH /api/v1/detections/:id/review` is restricted strictly to `analyst` and `admin` roles. Requests from `viewer` roles are rejected with `HTTP 403 Forbidden`.
- **UI Interceptor:** The React portal automatically appends the Bearer token to all outgoing requests via `authFetch` and redirects unauthenticated users to the Login Portal.

---

## 🗺️ High-Performance Dynamic Tile Servers

To eliminate the GeoJSON browser bottleneck and avoid expensive disk-bound chip extraction, the Docker Compose stack includes specialized geospatial tile servers:

### 1. Vector Tile Server (`Martin` - Port 3001)

- Blazing-fast Rust-based tile server connected directly to PostGIS `infrastructure_detections`.
- Streams Mapbox Vector Tiles (MVT): `http://localhost:3001/tiles/infrastructure_detections/{z}/{x}/{y}.pbf`.
- Consumed by Deck.gl `MVTLayer` on the frontend, enabling smooth 60fps WebGL rendering of 100,000+ polygons.

### 2. Dynamic Raster Server (`TiTiler` - Port 8001)

- Dynamic Cloud-Optimized GeoTIFF (COG) tile server connected to MinIO/S3 (`caelum-raw`).
- Streams dynamic multi-resolution bounding box crops: `http://localhost:8001/cog/crop/{minx},{miny},{maxx},{maxy}.png?url=...`.
- Toggled directly in the Multi-Temporal Inspector to smoothly compare $T_0$ vs $T_1$ passes at any zoom level.

---

## 🚨 Proactive Observability & Data Lifecycle Management

### 1. High-Priority Webhook Alerting (`src/api/webhooks.py`)

- Automatically dispatches standardized SIEM JSON alert payloads whenever incoming ML detections exceed `priority_score > 0.85`.
- Configure comma-separated webhook destinations via environment variable:
  ```bash
  export WEBHOOK_URLS="https://siem.defense.internal/alerts,https://hooks.slack.com/services/..."
  ```

### 2. Data Lifecycle Retention Pruner (`src/etl/pruner.py`)

- Automatically prunes raw Sentinel GeoTIFF rasters older than 7 days from `caelum-raw` or local `data/raw/`, preventing disk exhaustion.
- Cropped anomaly chips (`data/chips/`) and PostGIS vector records are permanently retained.
- Run manually or schedule via cron:
  ```bash
  python -m src.etl.pruner --retention-days 7 --dir data/raw
  # Dry-run scan:
  python -m src.etl.pruner --dry-run
  ```

---

## 🛡️ Bare-Metal Production Deployment (100% On-Premises & Air-Gapped)

Project Caelum-EO is architected for **100% on-premises, fully local, or air-gapped bare-metal environments** with zero external cloud dependencies.

### Production Network Hardening (`docker-compose.prod.yml`)

The production Docker stack enforces strict network isolation:

- **Exposed Host Interfaces:** Only the WebGL Analyst Portal (`port 3000`) and FastAPI Gateway (`port 8000`) are accessible to operators on the local network.
- **Internalized Infrastructure:** PostGIS (`5432`), MinIO Object Storage (`9000/9001`), and Redpanda Event Streaming (`29092/9092`) have **no exposed host ports** and communicate strictly over the internal encrypted Docker bridge network (`caelum-net-prod`).
- **Local Tile Servers:** Martin MVT (`3001`) and TiTiler (`8001`) are bound to `127.0.0.1` loopback for local browser rendering.
- **Hardware-Accelerated GPU Passthrough:** The ML inference worker container utilizes `nvidia-container-toolkit` device reservations (`capabilities: [gpu]`) for direct bare-metal access to host NVIDIA GPUs (e.g. RTX 4090, A100, H100, L4, T4).

### One-Command Deployment Automation (`./deploy.sh`)

The `deploy.sh` script automates the complete bare-metal bootstrap process:

1. **GPU & Driver Validation:** Queries `nvidia-smi` to verify installed NVIDIA drivers and GPU capabilities.
2. **Cryptographic Secret Generation:** Automatically initializes a restricted `.env.prod` (`chmod 600`) with high-entropy random database passwords and JWT signing keys.
3. **Local Storage Initialization:** Creates host directories for raw rasters (`data/raw/`), anomaly chips (`data/chips/`), and model weights (`weights/`).
4. **Production Stack Launch:** Builds and starts the production container topology with health checks.

```bash
# Execute bare-metal production deployment:
./deploy.sh

# Monitor live production logs:
docker compose -f docker-compose.prod.yml logs -f

# Gracefully stop production stack:
docker compose -f docker-compose.prod.yml down
```

---

## 📜 License

Licensed under Apache 2.0. Maintained by [Franek Jemiolo](https://github.com/FranekJemiolo).
