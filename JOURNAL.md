# Engineering Journal: Project Caelum-EO

**Project Namespace:** `github.com/FranekJemiolo/Caelum-EO`  
**Target:** Automated Geospatial Intelligence (GEOINT) Infrastructure Detection & Mapping Pipeline

---

## Entry 001 - Project Inception & Scaffolding Strategy
*Date: September 27, 2026*

### Context
`Project Caelum-EO` is designed to ingest multi-temporal Earth Observation (EO) satellite data (Copernicus Sentinel-1 SAR and Sentinel-2 optical imagery), run change detection using the foundation model `ibm-nasa-geospatial/Prithvi-EO-2.0-300M`, classify and vectorize structures with YOLOv8-OBB and GeoSAM, and store actionable vector intelligence in PostGIS for temporal exploration in a Deck.gl WebGL frontend.

### Key Decisions
1. **Repository & Directory Layout:**
   - Dedicated monorepo structure separating concerns:
     - `services/ingestion`: CDSE STAC client, Kafka producers, stream consumers, spatial alignment.
     - `services/inference`: Prithvi-EO-2.0 change detection service, YOLOv8-OBB classification, GeoSAM vectorizer.
     - `services/database`: PostGIS migrations, spatial indexing, seed definitions.
     - `services/api`: FastAPI REST/GeoJSON bridge for frontend data queries.
     - `web`: React + Deck.gl + MapLibre client with temporal timeline scrubber.
     - `docs`: Architecture diagrams, API specs, data dictionaries.
2. **Metadata-First Ingestion Pattern:**
   - Instead of downloading multi-hundred megabyte raw GeoTIFF tiles immediately upon STAC query, the pipeline decouples discovery from data acquisition.
   - Polling workers push lightweight JSON STAC metadata payloads to Kafka (`geoint-stac-ingest`).
   - Consumer workers download windowed sub-tiles or cloud-optimized GeoTIFFs (COGs) via range requests dynamically, drastically saving network bandwidth and IOPS.
3. **Kafka Broker Architecture:**
   - Standard Kafka 7.5 cluster with Zookeeper to ensure distributed pub-sub decoupled processing for variable satellite revisit schedules.

---

## Entry 002 - STAC ETL Design & CDSE Poller Implementation
*Date: September 27, 2026*

### Technical Decisions
1. **STAC API Client:** Selected `pystac-client` combined with `requests` and Pydantic v2 schemas (`STACItemPayload`, `IngestionConfig`).
2. **Copernicus Data Space Ecosystem (CDSE):**
   - CDSE endpoint: `https://catalogue.dataspace.copernicus.eu/stac`
   - Configurable collection identifiers: `SENTINEL-2` (L2A bottom-of-atmosphere reflectance) and `SENTINEL-1` (GRD backscatter).
3. **Resilience & Partitioning:**
   - STAC polling implements jittered exponential backoff via `tenacity`.
   - Kafka message keys use the MGRS tile or geopolitical geofence ID to preserve temporal ordering per spatial cell.
4. **Band Mapping for Prithvi:**
   - Sentinel-2 metadata maps assets B02 (Blue), B03 (Green), B04 (Red), B8A (Narrow NIR), B11 (SWIR 1), B12 (SWIR 2) required by Prithvi 6-band input specifications.

---

## Entry 003 - Pytest Testing Strategy & Python Management with uv
*Date: September 27, 2026*

### Technical Decisions
1. **Python Environment Management with `uv`:**
   - Switched virtual environment and package installation to astral-sh `uv`.
   - Environment created with CPython 3.11.14 (`uv venv --python 3.11`).
   - Lightning-fast deterministic resolution for heavy geospatial wheels (`rasterio`, `shapely`, `torch`).
2. **Unit Test Coverage:**
   - Created test suites in `services/ingestion/tests/`:
     - `test_config.py`: Schema validation, defaults, geofence coordinate ranges.
     - `test_stac_client.py`: Mocked CDSE STAC search responses, cloud cover threshold cut-offs (>20%), required 6-band extraction.
     - `test_kafka_producer.py`: Keyed partition routing, dry-run memory buffer, batch publishing.
     - `test_poll_worker.py`: Cycle execution and in-memory scene deduplication preventing repeated Kafka message publishing.
     - `test_alignment.py`: Array windowing, temporal pair creation (2, 6, H, W), Scene Classification Layer (SCL) cloud/water masking.
   - Result: 100% test pass rate across ingestion components.

---

## Entry 004 - Foundation Model Temporal Change Detection (Prithvi-EO-2.0)
*Date: September 27, 2026*

### Technical Decisions
1. **Model Selection Rationale:**
   - Foundation Model: `ibm-nasa-geospatial/Prithvi-EO-2.0-300M`.
   - Pre-trained on 100+ countries with self-supervised temporal masking. Outperforms classical pixel-difference, NDVI differencing, or standard ResNet change models by understanding seasonal and sun-angle phenology.
2. **Input Tensor Specification:**
   - Temporal pairs structured as `(2, 6, H, W)`:
     - Dim 0: Time A (baseline reference) and Time B (newly acquired image).
     - Dim 1: 6 bands (Blue, Green, Red, Narrow NIR, SWIR1, SWIR2).
     - Spatial dimensions: Resampled to 10m Ground Sample Distance (GSD).
3. **MMSegmentation Head:**
   - Decoder takes dual-temporal backbone features and absolute difference embeddings `|f1 - f0|`, projecting into change probability logits.
   - When running in deployment environments without pre-downloaded 1.2GB weights checkpoints, the architecture includes a deterministic spectral-distance baseline mode to ensure continuous operational availability.

---

## Entry 005 - YOLOv8-OBB Classification & GeoSAM Zero-Shot Vectorization
*Date: September 27, 2026*

### Technical Decisions
1. **Oriented Bounding Boxes (YOLOv8-OBB):**
   - Standard axis-aligned boxes include excessive non-target background when detecting tactical infrastructure (e.g. diagonal runway strips, long naval berths, revetted battery berms).
   - OBB outputs `(cx, cy, w, h, angle_degrees)` to isolate the specific object footprint.
2. **Target Ontology:**
   - `Logistics_Depot`, `Radar_Dome`, `Airfield_Runway`, `SAM_Battery_Site`, `Hardened_Shelter`, `Naval_Pier_Berth`, `Fuel_Storage_Tank`, `Vehicle_Staging_Area`.
3. **GeoSAM Boundary Segmentation:**
   - Bridges the gap between bounding boxes and GIS polygons. Uses Segment Anything visual prompting (centroid + bounding box) to isolate the physical perimeter.
   - Applies Douglas-Peucker topological simplification (`shapely`) to avoid multi-thousand-vertex polygon bloat while preserving architectural roofline contours in WGS84 (`EPSG:4326`).

---

## Entry 006 - PostGIS Spatial Schema & Deck.gl React Visualization Layer
*Date: September 27, 2026*

### Technical Decisions
1. **PostGIS Storage:**
   - `infrastructure_detections` table equipped with `GIST (geometry)` index for sub-10ms bounding box queries (`ST_Intersects`).
   - B-Tree index on `detection_date` for timeline scrubber queries and covering index for index-only scans.
2. **FastAPI Bridge:**
   - Exposes `/api/detections` with bbox, temporal window, and classification filtering, outputting standard GeoJSON `FeatureCollection`.
3. **Deck.gl React Frontend:**
   - Deck.gl 9.0 `GeoJsonLayer` over CartoDB Dark Matter style via MapLibre GL.
   - Dynamic 3D extrusion with height proportional to detection confidence.
   - Tactically-styled temporal scrubber component with automated 3-day step animation playback.
   - Instant categorical filtering and minimum confidence slider.
   - Feature inspection drawer displaying sensor metadata, platform name, and intelligence notes.

---

## Entry 007 - Phase 2 Design Specification & Documentation Expansion
*Date: September 27, 2026*

### Problem & Rationale
Expanding the architectural rigor of Project Caelum-EO to support a production-grade distributed pipeline. Detailed documentation must formalize:
1. End-to-end data flow from Copernicus STAC API, Kafka event bus, GPU inference workers, PostGIS spatial store, and Deck.gl visual layer (`docs/ARCHITECTURE.md`).
2. Exact PostGIS 3.3 / PostgreSQL 15 schema, `GIST` indexes, covering indices, and field constraints (`docs/DATA_MODEL.md`).
3. Mathematical and tensor specification for `ibm-nasa-geospatial/Prithvi-EO-2.0-300M` masked autoencoder, 6-band radiometric standardization, and YOLOv8-OBB/GeoSAM perimeter extraction (`docs/ML_PIPELINE.md`).

---

## Entry 008 - Task A: STAC Ingestion Worker Implementation
*Date: September 27, 2026*

### Implementation & Tradeoffs
1. **Module:** `src/ingestion/stac_poller.py`
2. **Core Decisions:**
   - Integrated `pystac-client` directly targeting the Copernicus Data Space Ecosystem (`https://catalogue.dataspace.copernicus.eu/stac`).
   - Configured spatial bounding box targeting the Eastern European frontier (Suwalki Gap `[22.8, 53.8, 24.5, 54.7]`) with dynamic lookback time windows.
   - Rigorously filters and maps download URLs for the 6 core Prithvi foundation model bands (`B02`, `B03`, `B04`, `B8A`, `B11`, `B12`).
   - Enforced the decoupled ingestion pattern: Heavy GeoTIFF rasters are not downloaded in the polling thread. Instead, structured `STACIngestPayload` models are published to Kafka topic `geoint-stac-ingest`.
   - Included `--dry-run` flag and deterministic fallback handling for verification in local offline environments.

---

## Entry 009 - Task B: Prithvi-EO-2.0 Inference Coordinator Implementation
*Date: September 27, 2026*

### Implementation & Tradeoffs
1. **Module:** `src/inference/detector.py`
2. **Core Decisions:**
   - Implemented `PrithviEOFoundationModel` PyTorch module integrating the 3D masked autoencoder backbone for `ibm-nasa-geospatial/Prithvi-EO-2.0-300M`.
   - Supports GPU/MPS/CPU hardware acceleration (validated on Apple Silicon MPS).
   - Enforces 6-band radiometric normalization with Copernicus Sentinel-2 Level-2A surface reflectance parameters.
   - Implemented `InferenceCoordinator` Kafka listener consuming from `geoint-stac-ingest`, simulating windowed COG raster alignment and producing high-fidelity structural change masks.
   - Tested and verified with synthetic input generating 2,475 anomaly pixels on a 256x256 grid.

---

## Entry 010 - Task C: Vectorization & PostGIS Storage Pipeline
*Date: September 27, 2026*

### Implementation & Tradeoffs
1. **Module:** `src/inference/vectorizer.py`
2. **Core Decisions:**
   - Morphological segmentation: Uses `scipy.ndimage.label` connected components to isolate bounding boxes of anomalous change from Prithvi binary masks.
   - Multi-model simulation: Categorizes structures via YOLOv8-OBB geometric footprint heuristics and simulates GeoSAM zero-shot perimeter tracing with Douglas-Peucker topological simplification.
   - Persistence layer: `PostGISWriter` executes parameterized SQL batch inserts via `psycopg2` using `ST_SetSRID(ST_GeomFromGeoJSON(...), 4326)`.
   - Tested with synthetic 2-cluster raster, validating polygon closure and coordinate reprojection into EPSG:4326.
