# Project Caelum-EO

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-brightgreen.svg)](https://www.python.org/)
[![Kafka](https://img.shields.io/badge/Apache-Kafka-231F20.svg?logo=apache-kafka)](https://kafka.apache.org/)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.4-336791.svg?logo=postgresql)](https://postgis.net/)
[![Deck.gl](https://img.shields.io/badge/Deck.gl-9.0-black.svg)](https://deck.gl/)

> **Caelum** *(Latin: sky, the heavens)* — Continuous automated geospatial intelligence (GEOINT) pipeline for detecting, classifying, and mapping infrastructure build-out using Earth Observation AI foundation models.

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

*   **Message Broker & ETL:** Python 3.11, Apache Kafka, `pystac-client`, `rasterio`, `xarray`, `shapely`
*   **Machine Learning (Temporal Detection):** Hugging Face `ibm-nasa-geospatial/Prithvi-EO-2.0-300M` via PyTorch & MMSegmentation
*   **Machine Learning (Classification & Vectorization):** YOLOv8-OBB (Oriented Bounding Boxes), GeoSAM (Segment Anything for EO)
*   **Database:** PostgreSQL 16 with PostGIS extension (`GIST` indexed)
*   **Frontend / Visualization:** React, Deck.gl `GeoJsonLayer`, MapLibre GL
*   **Containerization:** Docker & Docker Compose

---

## 📁 Repository Structure

```
.
├── JOURNAL.md                      # Engineering journal & decision logs
├── README.md                       # Main project documentation
├── docker-compose.yml              # Multi-container orchestration (Kafka, PostGIS, Workers)
├── pyproject.toml                  # Python package configuration (3.11 target)
├── docs/                           # Architecture, specs & design documents
│   ├── architecture.md             # System design & data flow specification
│   ├── ingestion_pipeline.md       # STAC polling & Kafka messaging specification
│   └── data_dictionary.md          # Schema & tensor specifications
├── services/
│   ├── ingestion/                  # Component 1: STAC ETL & Kafka Ingestion Firehose
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── config.py               # Pydantic configuration & geofence definitions
│   │   ├── cdse_stac_client.py     # Copernicus Data Space STAC API client
│   │   ├── kafka_producer.py       # Resilient Kafka producer with retry mechanics
│   │   ├── poll_worker.py          # CLI runner & recurring poller
│   │   └── tests/                  # Pytest suite with mock STAC responses
│   ├── inference/                  # Components 2 & 3: Prithvi & YOLO/GeoSAM
│   └── database/                   # Component 4: PostGIS migrations & spatial indexes
└── web/                            # Component 5: React Deck.gl temporal dashboard
```

---

## 🚀 Quickstart & Verification

### 1. Launch Core Infrastructure
```bash
docker compose up -d zookeeper kafka postgis
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with Copernicus credentials or optional settings
```

### 3. Run Ingestion Tests
```bash
pytest services/ingestion/tests/ -v
```

### 4. Execute STAC Ingestion Poller
```bash
python -m services.ingestion.poll_worker --once
```

---

## 📜 License
Licensed under Apache 2.0. Maintained by [Franek Jemiolo](https://github.com/FranekJemiolo).
