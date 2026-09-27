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
     - `web`: React + Deck.gl + MapLibre client with temporal timeline scrubber.
     - `docs`: Architecture diagrams, API specs, data dictionaries.
2. **Metadata-First Ingestion Pattern:**
   - Instead of downloading multi-hundred megabyte raw GeoTIFF tiles immediately upon STAC query, the pipeline decouples discovery from data acquisition.
   - Polling workers push lightweight JSON STAC metadata payloads to Kafka (`geoint-stac-ingest`).
   - Consumer workers download windowed sub-tiles or cloud-optimized GeoTIFFs (COGs) via range requests dynamically, drastically saving network bandwidth and IOPS.
3. **Kafka Broker Architecture:**
   - Standard Kafka 7.5 cluster with Zookeeper (or KRaft mode) to ensure distributed pub-sub decoupled processing for variable satellite revisit schedules.

---

## Entry 002 - STAC ETL Design & CDSE Poller Implementation
*Date: September 27, 2026*

### Technical Decisions
1. **STAC API Client:** Selected `pystac-client` combined with `requests` and Pydantic v2 schemas (`STACItemPayload`, `IngestConfig`).
2. **Copernicus Data Space Ecosystem (CDSE):**
   - CDSE endpoint: `https://catalogue.dataspace.copernicus.eu/stac`
   - Configurable collection identifiers: `SENTINEL-2` (L2A bottom-of-atmosphere reflectance) and `SENTINEL-1` (GRD backscatter).
3. **Resilience & Partitioning:**
   - STAC polling implements jittered exponential backoff via `tenacity`.
   - Kafka message keys use the MGRS tile or geopolitical geofence ID to preserve temporal ordering per spatial cell.
4. **Band Mapping for Prithvi:**
   - Sentinel-2 metadata maps assets B02 (Blue), B03 (Green), B04 (Red), B8A (Narrow NIR), B11 (SWIR 1), B12 (SWIR 2) required by Prithvi 6-band input specifications.
