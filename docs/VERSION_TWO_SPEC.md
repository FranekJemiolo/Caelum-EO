# Project Caelum-EO: Version Two Architectural Specification

**Repository Namespace:** `github.com/FranekJemiolo/Caelum-EO`  
**Classification:** Strategic Defense-Grade Distributed Systems Roadmap  
**Target Release:** Caelum-EO v2.0  

---

## 1. Executive Summary & Vision

Project Caelum-EO Version One successfully established the end-to-end foundation for automated geospatial intelligence: zero-cloud local streaming ingestion of Copernicus Sentinel-2 Level-2A imagery, NASA/IBM Prithvi-EO-2.0 foundation model change inference, YOLOv8-OBB infrastructure classification, single-pass C-accelerated vectorization, PostGIS 15 spatial persistence, MVT/TiTiler dynamic rendering, and a reactive WebGL Deck.gl analyst triage console.

**Version Two** scales this pipeline from tactical regional monitoring to **continuous continental-scale planetary surveillance** within high-security, air-gapped on-premises data centers and forward-deployed tactical edge nodes.

```
+-----------------------------------------------------------------------------------------+
|                                CAELUM-EO VERSION TWO TOPOLOGY                           |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  [Multi-Constellation Sensor Feeds]                                                    |
|  +-------------------+  +-------------------+  +-------------------+                    |
|  | Sentinel-2 L2A    |  | Sentinel-1 SAR    |  | Commercial 30cm   |                    |
|  | (10m Optical)     |  | (IW/GRD Radar)    |  | (Maxar/Planet)    |                    |
|  +---------+---------+  +---------+---------+  +---------+---------+                    |
|            |                      |                      |                              |
|            +----------------------+----------------------+                              |
|                                   |                                                     |
|                                   v                                                     |
|  [Distributed Ingestion Fabric: Apache Arrow Flight / Ray Data]                         |
|  +-----------------------------------------------------------------------------------+  |
|  | - Parallel Tile Demultiplexing over 100GbE RoCEv2 Network Fabric                 |  |
|  | - Zero-Copy Shared Memory Inter-Process Buffers                                   |  |
|  +--------------------------------+--------------------------------------------------+  |
|                                   |                                                     |
|                                   v                                                     |
|  [Multi-Node GPU Inference Cluster: Triton Inference Server + GPUDirect Storage]       |
|  +-----------------------------------------------------------------------------------+  |
|  | - TensorRT-LLM / INT8 Quantized Prithvi-EO-2.0 MAE Backbone (20x Throughput)      |  |
|  | - SAR-Optical Coherence Cross-Attention Multi-Modal Fusion Module                 |  |
|  | - Dynamic Batching across 8x NVIDIA H100 / A100 Nodes                            |  |
|  +--------------------------------+--------------------------------------------------+  |
|                                   |                                                     |
|                                   v                                                     |
|  [Distributed Spatial Storage Tier: Citus Distributed PostGIS + Redis Vector Cache]    |
|  +-----------------------------------------------------------------------------------+  |
|  | - PostGIS Horizontally Sharded by MGRS Military Grid Zones (50M+ Polygons)       |  |
|  | - Martin Vector Tile Server with Pre-Warmed Tier-1 Redis MVT Cache (<5ms latency)  |  |
|  +--------------------------------+--------------------------------------------------+  |
|                                   |                                                     |
|                                   v                                                     |
|  [Analyst Interface & Continuous Active Learning Loop]                                  |
|  +-----------------------------------------------------------------------------------+  |
|  | - WebGPU / Deck.gl Tile Clusters with Dynamic LOD Pruning                         |  |
|  | - HITL Reclassifications -> Automated LoRA Parameter-Efficient Fine-Tuning        |  |
|  | - Tactical Edge Synchronization to Forward Jetson AGX Orin Units via Low-BW Mesh  |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Distributed Tiling & Inference at Scale

### 2.1. Apache Arrow Flight & Ray Compute Fabric
In Version One, raster fetching and tensor preparation run in discrete Python worker processes. Version Two introduces **Ray Data** and **Apache Arrow Flight** to orchestrate distributed processing:
- **Zero-Copy Memory Transport:** Multi-band rasters are decoded directly into Arrow Flight RecordBatches, eliminating serialization overhead between ETL workers and inference nodes.
- **Dynamic Bounding Box Sharding:** Full Copernicus MGRS tiles (109.8 km x 109.8 km) are partitioned into adaptive 512x512 windows with 32-pixel spatial overlap to prevent boundary clipping. Tasks are scheduled dynamically across worker nodes based on local GPU memory availability.

### 2.2. Triton Inference Server with GPUDirect Storage (GDS)
- **NVIDIA Triton Cluster:** Models are served through Triton Inference Server utilizing dynamic batching, concurrent model execution, and FP8/INT8 TensorRT optimization.
- **GPUDirect Storage (GDS):** COG imagery streams bypass CPU memory entirely, flowing directly from NVMe arrays over PCIe/NVLink into GPU VRAM, achieving >25 GB/s sustained throughput per inference node.
- **Throughput Target:** Process 1,000 full Sentinel-2 scenes (over 1 Petabyte of pixel data) per 24-hour cycle on an 8-GPU bare-metal cluster.

---

## 3. Multi-Modal SAR & Optical Fusion (Sentinel-1 + Sentinel-2)

### 3.1. Physical Rationale for Radar Integration
Optical sensors are blind at night and crippled by cloud cover, atmospheric haze, and camouflage netting. In Eastern and Northern European surveillance theaters, cloud obstruction exceeds 60% annually.

Version Two implements **hybrid multi-modal fusion** coupling Sentinel-2 optical surface reflectance with **Sentinel-1 C-Band Synthetic Aperture Radar (SAR)**:
- **Interferometric Coherence ($\gamma$):** Surface disturbance caused by soil clearing, foundation excavation, and vehicle movement destroys radar coherence even before concrete is poured.
- **Backscatter Cross-Section ($\sigma^0$):** Dual-polarization VV and VH backscatter detects corner-reflector signatures of metallic containers, fences, radar dishes, and reinforced hangars regardless of weather or time of day.

### 3.2. Cross-Attention Fusion Architecture
```
Sentinel-2 Optical (6 Bands, 10m)  ──► [Optical Spatial Encoder] ──┐
                                                                    ├──► [Cross-Attention Fusion] ──► [Fused Probability Map]
Sentinel-1 SAR (VV, VH, Coherence) ──► [Radar Polarimetric Encoder] ┘
```
The foundation model accepts an 8-channel fused tensor `[B02, B03, B04, B8A, B11, B12, SAR_VV, SAR_VH]`. Cross-attention heads dynamically weight optical versus radar features based on the optical scene cloud mask confidence.

---

## 4. Distributed Spatial Data Tier: Citus PostGIS & MVT Pre-Caching

### 4.1. Horizontal PostGIS Partitioning with Citus
Version One stores detections in a single PostgreSQL table. At continental scale ($10^7$ to $10^8$ detection records over a 3-year surveillance baseline), single-node GIST indexes degrade.

Version Two incorporates **Citus Data** to horizontally shard PostGIS:
- **Sharding Key:** `mgrs_tile_id` (Military Grid Reference System 6-degree zone).
- **Secondary Range Partitioning:** Partitioned by acquisition quarter (`YYYY-Qn`).
- **Parallel Distributed Queries:** Spatial intersections (`ST_Intersects`), zone aggregations, and spatial JOINs execute concurrently across worker nodes in sub-10 milliseconds.

### 4.2. Three-Tier MVT Caching Architecture
To guarantee smooth 60fps pan/zoom across 50,000,000 polygons:
1. **L1 (Client WebGPU Buffer):** Cached tiles stored directly in browser WebGL/WebGPU VRAM.
2. **L2 (Distributed Redis Tile Cache):** High-speed in-memory store caching generated `.pbf` vector tiles for active operational sectors.
3. **L3 (Martin MVT Generator over Read-Replicas):** Generates new vector tiles via `ST_TileEnvelope` and `ST_AsMVT` executed against PostGIS read replicas.

---

## 5. Continuous Active Learning & Automated Fine-Tuning

### 5.1. Closed-Loop Reclassification Pipeline
Every verification action taken by a human analyst (`VERIFIED`, `MISCLASSIFIED`, `FALSE_POSITIVE`) logged in `review_audit_log` serves as ground truth training data.

```mermaid
flowchart LR
    A[Analyst Triage UI] -->|PATCH Review| B[(review_audit_log)]
    B --> C[Dataset Curating Engine]
    C -->|Auto-Generated Hard Examples| D[Air-Gapped LoRA Fine-Tuning Worker]
    D -->|Parameter Delta Weights| E[Model Registry / MLflow]
    E -->|Automated Benchmark Gate| F[Triton Canary Deployment]
```

### 5.2. Parameter-Efficient Fine-Tuning (LoRA)
- Rather than full model retraining, the pipeline trains Low-Rank Adaptation (LoRA) matrices ($r=16, \alpha=32$) on the attention projection layers of the Prithvi ViT backbone.
- Automated weekly fine-tuning on newly verified hard negative examples drops the false positive rate on complex seasonal foliage by an estimated 80%.

---

## 6. Forward Tactical Edge Deployment (Disconnected / Air-Gapped)

### 6.1. Edge Appliance Profile
For mobile command posts, tactical operations centers (TOCs), and naval vessels:
- **Form Factor:** Ruggedized NVIDIA Jetson AGX Orin (64GB) or 2U rugged rack servers.
- **Optimized Model Footprint:** Quantized INT8 Prithvi student model (distilled from 300M parameters down to 65M) running locally on TensorRT.
- **Local Micro-Stack:** Single-container composition running SQLite with SpatiaLite / DuckDB Spatial and lightweight Martin tile server.

### 6.2. Tactical Delta Synchronization
When high-bandwidth connectivity is unavailable:
- Edge nodes process local satellite or tactical UAV feeds autonomously.
- Detections are serialized into compact protocol buffers containing compressed polygon deltas (< 2 KB per target).
- Deltas are transmitted over low-bandwidth tactical satellite communications (SATCOM / HF radio mesh) to headquarters, where they are merged into the central Citus PostGIS cluster.

---

## 7. Version Two Technical Milestones & Roadmap

| Quarter | Milestone | Key Deliverables |
| :--- | :--- | :--- |
| **v2.1** | **Multi-Modal SAR Ingestion** | Ingest Sentinel-1 GRD/IW products; cross-attention optical-radar fusion head; cloud-resilient change detection. |
| **v2.2** | **Distributed Inference Engine** | NVIDIA Triton Inference Server deployment; TensorRT FP8 optimization; GPUDirect Storage integration. |
| **v2.3** | **Citus PostGIS & Redis Cache** | Sharded PostGIS cluster across MGRS grid zones; 3-tier MVT tile caching; sub-5ms viewport rendering. |
| **v2.4** | **Automated Active Learning** | Automated LoRA fine-tuning worker; model registry validation gate; automated false-positive suppression. |
| **v2.5** | **Tactical Edge Distribution** | Jetson AGX Orin packaging; low-bandwidth delta synchronization; SPIFFE/SPIRE zero-trust mTLS encryption. |
