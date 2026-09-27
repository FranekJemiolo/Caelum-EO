# Machine Learning Architecture Specification

**Repository:** `github.com/FranekJemiolo/Caelum-EO`  
**Components:** `services/inference`

---

## 1. Two-Stage Inference Paradigm
Processing high-resolution satellite imagery directly through heavy segmentation networks across vast territorial swathes is computationally prohibitive. `Project Caelum-EO` implements an optimized two-stage pipeline:

```mermaid
flowchart LR
    A[Co-registered Temporal Pair<br/>Time A & Time B (6-band)] --> B[Stage 1: Prithvi-EO-2.0 MAE<br/>Change Probability Map]
    B --> C[Spatial Cluster Extractor<br/>BBox & Centroid Derivation]
    C --> D[Stage 2a: YOLOv8-OBB<br/>Target Categorization]
    C --> E[Stage 2b: GeoSAM<br/>Zero-Shot Boundary Vectorization]
    D --> F[PostGIS Ingestion Engine]
    E --> F
```

---

## 2. Stage 1: NASA/IBM Prithvi-EO-2.0 Foundation Model
- **Model Backbone:** `ibm-nasa-geospatial/Prithvi-EO-2.0-300M` (Vision Transformer Masked Autoencoder pre-trained on multi-temporal Copernicus Harmonized Landsat-Sentinel data).
- **Temporal Stacking:** Input tensor is structured as `(2, 6, H, W)` representing two observation times across 6 optical/infrared bands:
  1. `B02`: Blue (490 nm)
  2. `B03`: Green (560 nm)
  3. `B04`: Red (665 nm)
  4. `B8A`: Narrow Near-Infrared (865 nm)
  5. `B11`: Short-Wave Infrared 1 (1610 nm)
  6. `B12`: Short-Wave Infrared 2 (2190 nm)
- **Difference Head:** Features from Time A and Time B are combined with absolute spectral difference vectors: `Concat([f0, f1, |f1 - f0|])`.
- **Output:** Binary Change Mask where pixel value `1` denotes artificial structural anomalies, filtering out seasonal crop cycles and weather phenology.

---

## 3. Stage 2a: YOLOv8-OBB (Oriented Bounding Boxes)
- **Rationale:** Traditional axis-aligned bounding boxes fail to capture elongated, angled tactical installations (e.g. runways, revetted trench lines, piers). YOLOv8-OBB outputs `(cx, cy, w, h, angle)`.
- **Target Vocabulary:**
  - `Logistics_Depot`
  - `Radar_Dome`
  - `Airfield_Runway`
  - `SAM_Battery_Site`
  - `Hardened_Shelter`
  - `Naval_Pier_Berth`
  - `Fuel_Storage_Tank`
  - `Vehicle_Staging_Area`

---

## 4. Stage 2b: GeoSAM Zero-Shot Perimeter Vectorization
- **Rationale:** Deep learning segmentation heads on low-resolution satellite imagery often produce blurry pixel blobs. GeoSAM takes the centroid point and bounding box from Stage 2a as visual prompts to segment the crisp physical roofline and perimeter.
- **Topological Cleanup:** Douglas-Peucker simplification is applied to reduce vertex bloat while retaining high-fidelity geometric contours. Polygons are reprojected into WGS84 (`EPSG:4326`) and validated via `shapely.validation.make_valid`.
