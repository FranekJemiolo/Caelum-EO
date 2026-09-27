# Project Caelum-EO: Machine Learning & Foundation Model Specification

**Repository Namespace:** `github.com/FranekJemiolo/Caelum-EO`
**Primary Foundation Model:** `ibm-nasa-geospatial/Prithvi-EO-2.0-300M`
**Secondary Detectors:** YOLOv8-OBB & GeoSAM

---

## 1. Deep Learning Pipeline Overview

```
[Windowed Copernicus STAC Reflectances]
                  │
                  ▼
[Bilinear Resampling & SCL Cloud Masking]
                  │
                  ▼
[Normalized Dual-Temporal Stack: (B, 6, 2, H, W)]
                  │
                  ▼
[NASA/IBM Prithvi-EO-2.0-300M MAE Backbone]
                  │
                  ▼
[Temporal Difference Decoder & Sigmoid Probability Map]
                  │
                  ▼
[Binary Thresholding (tau >= 0.60)]
                  │
                  ▼
[Connected Components Cluster & Bounding Box Extraction]
                  │
       ┌──────────┴──────────┐
       │                     │
       ▼                     ▼
[YOLOv8-OBB Classifier]    [GeoSAM Zero-Shot Perimeter]
(Class Label + Conf)      (EPSG:4326 GeoJSON Polygon)
       └──────────┬──────────┘
                  │
                  ▼
[PostGIS infrastructure_detections Persistence]
```

---

## 2. Tensor Layout & Band Normalization

### 2.1. Tensor Dimensions

Prithvi-EO-2.0 is designed as a temporal 3D Vision Transformer Masked Autoencoder. The input tensor is formatted as:
$$\mathbf{X} \in \mathbb{R}^{B \times C \times T \times H \times W}$$

- **$B$ (Batch Size):** Typically 1 during localized inference.
- **$C$ (Channels):** Exactly 6 Sentinel-2 optical bands.
- **$T$ (Time steps):** Exactly 2 ($T_0$ baseline reference, $T_1$ monitoring observation).
- **$H, W$ (Spatial Dimensions):** Multiples of 16 (default 256 or 512).

### 2.2. Band Index Mapping

1. `Channel 0`: `B02` (Blue - 490 nm)
2. `Channel 1`: `B03` (Green - 560 nm)
3. `Channel 2`: `B04` (Red - 665 nm)
4. `Channel 3`: `B8A` (Narrow NIR - 865 nm)
5. `Channel 4`: `B11` (SWIR 1 - 1610 nm)
6. `Channel 5`: `B12` (SWIR 2 - 2190 nm)

### 2.3. Radiometric Standardization

Input pixel values are converted from Level-2A surface reflectance integers ($0 - 10,000$) to float32 $[0.0, 1.0]$, and standardized using Copernicus Sentinel-2 L2A empirical stats:

- **Means:** $\mu = [0.134, 0.141, 0.158, 0.285, 0.178, 0.126]$
- **Std Devs:** $\sigma = [0.082, 0.076, 0.088, 0.124, 0.091, 0.078]$

$$\mathbf{X}_{norm} = \frac{\mathbf{X} - \mu}{\sigma}$$

---

## 3. Prithvi-EO-2.0 Inference & Difference Fusion

1. **Backbone Tokenization:** The 3D patch embedding projects $(C \times T \times P_H \times P_W)$ tubelet patches into embedding vectors.
2. **Temporal Difference Fusion:**
   $$F_0 = \text{Encoder}(T_0), \quad F_1 = \text{Encoder}(T_1)$$
   $$\text{Fused} = \text{Concat}\big(F_0, F_1, |F_1 - F_0|\big)$$
3. **Probability Activation:** Convolutional decoder layers project features to single-channel change probability $P(x, y) \in [0.0, 1.0]$.
4. **Binary Anomaly Mask:**
   $$M(x, y) = \begin{cases} 1 & \text{if } P(x, y) \ge 0.60 \\ 0 & \text{otherwise} \end{cases}$$
5. **Deterministic Fallback (Zero-Weights / CPU Mode):**
   When foundation model weights are not downloaded, the pipeline smoothly degrades to normalized spectral distance difference:
   $$\text{SpecDiff}(x, y) = \frac{1}{\sqrt{6}} \|\mathbf{X}(T_1, x, y) - \mathbf{X}(T_0, x, y)\|_2$$

---

## 4. Secondary Detectors: YOLOv8-OBB & GeoSAM

### 4.1. YOLOv8-OBB (Oriented Bounding Boxes)

- Categorizes anomalous clusters into tactical target classes:
  - `LOGISTICS_DEPOT`
  - `RUNWAY_TAXIWAY`
  - `RADAR_DOME`
  - `DEFENSE_REVETMENT`
  - `INDUSTRIAL_BUILDING`
  - `UNKNOWN_STRUCTURE`
- Predicts oriented bounding box parameters $(c_x, c_y, w, h, \theta)$.

### 4.2. GeoSAM Zero-Shot Perimeter Vectorization

- Prompted by the centroid and bounding box from Stage 2a.
- Segments crisp roofline contours.
- Applies Douglas-Peucker simplification ($\epsilon = 0.00002^\circ \approx 2\text{m}$) and validates polygon geometry (`shapely.validation.make_valid`).
- Reprojects pixel coordinates to WGS 84 (`EPSG:4326`).
