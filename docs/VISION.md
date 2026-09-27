# Project Caelum-EO: Strategic Vision & Doctrine Document

**Namespace:** `github.com/FranekJemiolo/Caelum-EO`  
**Classification:** Strategic Defense Geospatial Intelligence (GEOINT) Doctrine  
**Document Version:** 1.0.0 (Master Vision)  

---

## 1. Operational Doctrine & Strategic Context

In 21st-century peer and near-peer competition, national security depends on **persistent, automated, and sovereign awareness** of adversarial military infrastructure developments. 

Traditional geospatial intelligence (GEOINT) workflows rely on manual photo-interpretation of commercial and national reconnaissance satellite imagery. This paradigm is fundamentally obsolete:
- **Data Deluge:** Constellations like Copernicus Sentinel, Landsat, Maxar, and Planet downlink terabytes of raw pixel data hourly.
- **Latency Vulnerability:** Human analyst triage queues introduce delays of days to weeks between an adversary breaking ground and strategic commanders receiving actionable target intelligence.
- **Adversarial Camouflage & Weather Denial:** Adversaries exploit cloud cover, seasonal weather windows, and rapid construction methods to erect hardened facilities (radar domes, missile revetments, logistics staging bases, runway taxiways) undetected.

**Project Caelum-EO** *(Caelum meaning 'the heavens / sky' in Latin)* was forged to eliminate this latency. It provides a fully autonomous, sovereign, zero-cloud GEOINT intelligence pipeline that monitors sovereign borders and strategic sectors, detects surface changes at the physical speed of spaceborne overpasses, categorizes tactical targets, and delivers high-priority alerts into military command and control systems.

---

## 2. Core Architectural Pillars

```
+---------------------------------------------------------------------------------------+
|                               CAELUM-EO STRATEGIC PILLARS                             |
+---------------------------------------------------------------------------------------+
|                                                                                       |
|   1. 100% SOVEREIGN & AIR-GAPPED BY DESIGN                                            |
|      Zero dependencies on commercial hyperscale clouds (No AWS, GCP, or Azure locks). |
|      Runs on on-premises bare-metal servers, secure command bunkers, and edge nodes. |
|                                                                                       |
|   2. MULTI-TEMPORAL FOUNDATION MODEL BACKBONE                                         |
|      Leverages NASA/IBM Prithvi-EO-2.0-300M 3D Vision Transformer MAE pre-trained     |
|      on planetary scales to distinguish true structural build-out from seasonal crops.|
|                                                                                       |
|   3. TWO-STAGE TARGET DISCRIMINATION (YOLOv8-OBB & GEOSAM)                            |
|      Combines rapid oriented bounding box categorization with zero-shot roofline       |
|      perimeter extraction, outputting sub-meter vector footprints into PostGIS.       |
|                                                                                       |
|   4. REAL-TIME TACTICAL WebGL / MVT TILE SERVING                                      |
|      Renders tens of thousands of 3D extruded footprints at smooth 60fps via Deck.gl   |
|      and Martin vector tiles with sub-10ms viewport response times.                   |
|                                                                                       |
|   5. CONTINUOUS HUMAN-IN-THE-LOOP (HITL) ACTIVE LEARNING                              |
|      Analyst verifications feed an automated audit trail that fine-tunes future        |
|      foundation model iterations via air-gapped Parameter-Efficient LoRA workers.     |
+---------------------------------------------------------------------------------------+
```

---

## 3. End-to-End Operational Lifecycle

```
[Spaceborne Sensors] (Sentinel-1 SAR / Sentinel-2 MSI)
         │
         ▼
[Zero-Download STAC Ingestion Engine] (Streaming windowed COG byte-range reads)
         │
         ▼
[Copernicus Band Alignment & Cloud Masking] (Bilinear resampling & SCL filtering)
         │
         ▼
[NASA/IBM Prithvi-EO-2.0 Foundation Model] (Temporal difference feature fusion)
         │
         ▼
[Single-Pass C-Accelerated Vectorizer] (Morphological labeling & affine transform)
         │
         ▼
[PostGIS 15 Spatial Intelligence Layer] (GIST indexed, zone attribution & priority)
         │
    ┌────┴──────────────────────────────┐
    ▼                                   ▼
[High-Priority SIEM Alerts]   [Deck.gl WebGL Tactical HUD]
(P > 0.85 Webhook Dispatch)   (MVT Vector Tiles & TiTiler Raster Streams)
                                        │
                                        ▼
                              [Analyst Verification & Review]
                              (Immutable Audit Log -> Automated LoRA Tuning)
```

---

## 4. Tactical Classification Taxonomy

Caelum-EO models categorize structural anomalies into six standardized military and industrial infrastructure classifications:

| Infrastructure Class | Tactical Significance | Visual Signature | Typical Surface Area |
| :--- | :--- | :--- | :--- |
| **`RADAR_DOME`** | Air defense, early warning, SIGINT tracking | High dielectric return, circular geometry, spherical shadow | $500 - 3,000 \text{ m}^2$ |
| **`RUNWAY_TAXIWAY`** | Forward airbase extension, UAV staging | High-aspect-ratio linear concrete slab, high spectral reflectance | $10,000 - 150,000 \text{ m}^2$ |
| **`DEFENSE_REVETMENT`** | Fortified ordnance bunker, missile battery berm | Earth-bermed horseshoe or polygonal embankments | $2,000 - 15,000 \text{ m}^2$ |
| **`LOGISTICS_DEPOT`** | Ammunition supply point, motor pool, railhead | Large rectangular footprint, heavy vehicle access tracks | $5,000 - 50,000 \text{ m}^2$ |
| **`INDUSTRIAL_BUILDING`** | Defense manufacturing, dual-use assembly | Large warehouse envelope, HVAC / industrial roof infrastructure | $3,000 - 30,000 \text{ m}^2$ |
| **`UNKNOWN_STRUCTURE`** | Uncategorized foundation excavation, new clearing | Soil disturbance, rectangular clearing, high change probability | Variable |

---

## 5. Security & Threat Modeling

1. **Air-Gapped Isolation:** Zero external telemetry or third-party tracking scripts.
2. **Defensive Role-Based Access Control (RBAC):**
   - `viewer`: Read-only map visualization and temporal trend inspection.
   - `analyst`: Full Human-in-the-Loop review, reclassification, and inspection tooling.
   - `admin`: User provisioning, zone policy tuning, and pipeline configuration.
3. **Immutable Review Audit Logging:** Every verification decision is permanently recorded in `review_audit_log` with analyst cryptographic identity, timestamp, and rationale.
4. **Hardened Network Boundary:** Production composition exposes only the WebGL frontend (port 3000) and API reverse proxy (port 8000). PostGIS, MinIO, and Redpanda communicate strictly across an isolated internal Docker bridge network.

---

## 6. Strategic Capability Roadmap

- **Phase 1 (Complete):** Core architecture, synthetic multi-band raster generator, decoupled metadata-first STAC ingestion.
- **Phase 2 (Complete):** Windowed COG streaming ETL, SCL cloud masking, MinIO/S3 object store abstraction with local filesystem fallback.
- **Phase 3 (Complete):** NASA/IBM Prithvi-EO-2.0 temporal change detection, YOLOv8-OBB categorization, single-pass vectorizer, PostGIS spatial database, and Deck.gl WebGL HUD with Carto Dark Matter basemap.
- **Phase 4 (Complete):** Defense-grade OAuth2 JWT RBAC, Martin MVT vector tile streaming, TiTiler dynamic COG previews, SIEM webhook alerting (`P > 0.85`), automated raster retention pruner, and bare-metal production Docker packaging with NVIDIA GPU passthrough.
- **Phase 5 (Version Two - Next Release):** 
  - Sentinel-1 SAR + Sentinel-2 optical multi-modal cross-attention fusion.
  - Horizontally sharded Citus PostGIS across MGRS grid zones ($50\text{M}+$ polygons).
  - Multi-node NVIDIA Triton Inference Server with GPUDirect Storage (GDS).
  - Closed-loop automated LoRA fine-tuning on analyst review logs.
  - Forward edge deployment on ruggedized NVIDIA Jetson AGX Orin appliances with low-bandwidth tactical mesh synchronization.
