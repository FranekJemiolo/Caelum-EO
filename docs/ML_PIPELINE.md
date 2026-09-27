# Project Caelum-EO: Machine Learning Inference Pipeline Specification

**Repository Namespace:** `github.com/FranekJemiolo/Caelum-EO`
**Foundation Model:** `ibm-nasa-geospatial/Prithvi-EO-2.0-300M`
**Secondary ML Models:** YOLOv8-OBB & GeoSAM (Segment Anything Model for EO)

---

## 1. Multi-Stage Pipeline Architecture

```
[Copernicus STAC Streams]
         │
         ▼
[Temporal Pairing & Resampling (10m GSD)]
         │
         ▼ (2, 6, H, W) Tensor
[NASA/IBM Prithvi-EO-2.0 Foundation Model Backbone]
         │
         ▼ (H, W) Float32 Probability Map
[Binary Change Thresholding & Connected Components]
         │
         ▼ Bounding Boxes & Image Chips
┌────────────────────────┴────────────────────────┐
│                                                 │
▼                                                 ▼
[Stage 2a: YOLOv8-OBB]                [Stage 2b: GeoSAM Zero-Shot]
Infrastructure Classification         Perimeter & Roofline Polygons
(Logistics_Depot, Radar_Dome, etc.)   (EPSG:4326 GeoJSON Vectors)
└────────────────────────┬────────────────────────┘
                         │
                         ▼
           [PostGIS infrastructure_detections]
```

---

## 2. Prithvi-EO-2.0 Foundation Model Integration

### 2.1. Expected Input Tensor Structure

The foundation model accepts multi-temporal image stacks with exact band ordering and normalization:

| Dimension Index | Dimension Name     | Size / Range                   | Description                                                                |
| :-------------- | :----------------- | :----------------------------- | :------------------------------------------------------------------------- |
| `0`             | **Batch** ($B$)    | $\ge 1$                        | Batch size                                                                 |
| `1`             | **Time** ($T$)     | $2$                            | Index 0: Baseline reference ($T_0$); Index 1: Newly acquired scene ($T_1$) |
| `2`             | **Channels** ($C$) | $6$                            | The 6 optical & infrared Sentinel-2 bands                                  |
| `3`             | **Height** ($H$)   | Multiple of 16 (e.g. 256, 512) | Spatial height                                                             |
| `4`             | **Width** ($W$)    | Multiple of 16 (e.g. 256, 512) | Spatial width                                                              |

**Tensor Shape:** `(B, 2, 6, H, W)` or `(2, 6, H, W)` for a single observation pair.

### 2.2. Band Expectations & Order

The 6 bands must strictly match the Prithvi foundation model pre-training specification:

1. **Band 0 (`B02`):** Blue (Center: 490 nm, Res: 10m)
2. **Band 1 (`B03`):** Green (Center: 560 nm, Res: 10m)
3. **Band 2 (`B04`):** Red (Center: 665 nm, Res: 10m)
4. **Band 3 (`B8A`):** Narrow Near-Infrared / Vegetation Red Edge (Center: 865 nm, Res: 20m resampled to 10m)
5. **Band 4 (`B11`):** Short-Wave Infrared 1 (Center: 1610 nm, Res: 20m resampled to 10m)
6. **Band 5 (`B12`):** Short-Wave Infrared 2 (Center: 2190 nm, Res: 20m resampled to 10m)

### 2.3. Radiometric Normalization

Reflectance integers ($0 - 10000$) are converted to floating point and normalized via Copernicus Sentinel-2 Level-2A statistics:

- **Band Means:** `[0.134, 0.141, 0.158, 0.285, 0.178, 0.126]`
- **Band Standard Deviations:** `[0.082, 0.076, 0.088, 0.124, 0.091, 0.078]`

$$X_{norm} = \frac{X - \mu}{\sigma}$$

### 2.4. Processing Logic & Difference Decoder

- **Masked Autoencoder (MAE) Backbone:** Extracts spatio-temporal feature embeddings $F_0 = \text{Backbone}(T_0)$ and $F_1 = \text{Backbone}(T_1)$.
- **Temporal Difference Fusion:** Combines baseline features, newly acquired features, and absolute differential embeddings:
  $$\text{Fused} = \text{Concat}\big(F_0, F_1, |F_1 - F_0|\big)$$
- **Output:** A sigmoid activation produces a 2D change probability map $P \in [0.0, 1.0]^{H \times W}$.
- **Binary Mask:** Applying threshold $\tau \approx 0.60$ yields the binary change mask:
  $$M(x, y) = \begin{cases} 1 & \text{if } P(x, y) \ge \tau \\ 0 & \text{otherwise} \end{cases}$$

---

## 3. Secondary Vectorization & Classification Pipeline

### 3.1. Spatial Cluster Isolation

Connected component labeling on $M(x, y)$ isolates contiguous clusters of $1$s. Clusters smaller than $\text{min\_pixels} = 20$ are pruned as atmospheric or co-registration noise. Spatial bounding boxes and centroids are derived for each valid cluster.

### 3.2. YOLOv8-OBB Target Categorization

- Crops a context-padded chip from $T_1$ centered on the anomaly.
- Runs Oriented Bounding Box (OBB) inference to predict orientation angle $\theta$, width $w$, height $h$, and infrastructure class:
  - `Logistics_Depot`
  - `Radar_Dome`
  - `Airfield_Runway`
  - `SAM_Battery_Site`
  - `Hardened_Shelter`
  - `Naval_Pier_Berth`
  - `Fuel_Storage_Tank`
  - `Vehicle_Staging_Area`

### 3.3. GeoSAM Zero-Shot Perimeter Segmentation

- Uses the Segment Anything Model (SAM) prompted with the cluster centroid point and bounding box.
- Traces the zero-shot roofline/perimeter boundary into a closed contour.
- Applies Douglas-Peucker topological simplification ($\epsilon \approx 2\text{m}$) and validates polygon geometry via `shapely`.
- Reprojects polygon coordinates from raster pixel space to WGS 84 (`EPSG:4326`) for direct storage in PostGIS.
