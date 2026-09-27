# Ingestion Pipeline Specification: Copernicus STAC to Kafka

**Repository:** `github.com/FranekJemiolo/Caelum-EO`
**Component:** `services/ingestion`

---

## 1. Objective

Establish an asynchronous, event-driven pipeline that polls the Copernicus Data Space Ecosystem (CDSE) STAC API and pushes lightweight metadata items to Apache Kafka without blocking on heavy raster downloads.

---

## 2. STAC Endpoint & Collections

- **API Base:** `https://catalogue.dataspace.copernicus.eu/stac`
- **Collections:**
  - `SENTINEL-2`: Sentinel-2 Level-2A surface reflectance (10m - 20m resolution, 13 bands).
  - `SENTINEL-1`: Sentinel-1 Level-1 GRD (Ground Range Detected) SAR imagery (C-band, VV/VH polarizations).

---

## 3. Metadata Message Schema (`geoint-stac-ingest`)

```json
{
  "item_id": "S2A_MSIL2A_20260927T100031_N0500_R122_T33UUP_20260927T140000",
  "collection": "SENTINEL-2",
  "datetime": "2026-09-27T10:00:31.024Z",
  "bbox": [14.12, 52.31, 14.89, 52.95],
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [14.12, 52.31],
        [14.89, 52.31],
        [14.89, 52.95],
        [14.12, 52.95],
        [14.12, 52.31]
      ]
    ]
  },
  "cloud_cover": 4.12,
  "platform": "sentinel-2a",
  "constellation": "sentinel-2",
  "mgrs_tile": "33UUP",
  "geofence_id": "baltic-corridor-east",
  "assets": {
    "B02": {
      "href": "https://zipper.dataspace.copernicus.eu/...",
      "type": "image/tiff; application=geotiff"
    },
    "B03": {
      "href": "https://zipper.dataspace.copernicus.eu/...",
      "type": "image/tiff; application=geotiff"
    },
    "B04": {
      "href": "https://zipper.dataspace.copernicus.eu/...",
      "type": "image/tiff; application=geotiff"
    },
    "B8A": {
      "href": "https://zipper.dataspace.copernicus.eu/...",
      "type": "image/tiff; application=geotiff"
    },
    "B11": {
      "href": "https://zipper.dataspace.copernicus.eu/...",
      "type": "image/tiff; application=geotiff"
    },
    "B12": {
      "href": "https://zipper.dataspace.copernicus.eu/...",
      "type": "image/tiff; application=geotiff"
    }
  },
  "published_at": "2026-09-27T21:45:00.000Z"
}
```

---

## 4. Key Design Considerations

1. **Deduplication:** The STAC poller maintains a localized cache / state ledger of processed `item_id`s to avoid redundant Kafka message publication.
2. **Keyed Partitioning:** Kafka producer uses `mgrs_tile` or `geofence_id` as the message key. This guarantees that all imagery for a specific geographic tile arrives on the same partition in strictly chronological order.
3. **Graceful Degeneration:** When CDSE rate-limits or times out, the exponential backoff policy handles retries with random jitter up to 5 attempts before raising a dead-letter alert.
