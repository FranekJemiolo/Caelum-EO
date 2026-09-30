"""Telemetry Ingestion ETL for Project Caelum-EO — Version 5.

Ingests local AIS (Maritime) and ADS-B (Aviation) telemetry dumps from CSV/JSON
files into PostGIS trajectory tables. Implements "Dark Target" correlation to flag
transponder-off events near known EO infrastructure detections.

Data sources (air-gapped):
- AIS: CSV exports from a Receiver or external HDD (columns: MMSI, timestamp, lon, lat, …)
- ADS-B: JSON exports from a local dump1090 / OpenSky receiver

Repository: github.com/FranekJemiolo/Caelum-EO
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import psycopg2
import structlog
from psycopg2.extras import RealDictCursor, execute_values

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Database configuration (mirrors service.py env-var pattern)
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "caelum_geoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "caelum_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "caelum_secure_password")

# Dark-target correlation thresholds (configurable via system_configurations)
DEFAULT_AIS_DARK_RADIUS_KM: float = 50.0
DEFAULT_ADSB_DARK_RADIUS_KM: float = 30.0
DEFAULT_DARK_TIME_WINDOW_HOURS: int = 72


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------
@dataclass
class VesselTrackRecord:
    """Normalised AIS vessel position record."""

    mmsi: str
    timestamp: datetime
    lon: float
    lat: float
    vessel_name: Optional[str] = None
    vessel_type: Optional[str] = None
    flag: Optional[str] = None
    speed_knots: Optional[float] = None
    course_deg: Optional[float] = None
    heading_deg: Optional[float] = None
    draught_m: Optional[float] = None
    navigational_status: Optional[str] = None
    source_file: Optional[str] = None


@dataclass
class AircraftTrackRecord:
    """Normalised ADS-B aircraft position record."""

    icao24: str
    timestamp: datetime
    lon: float
    lat: float
    callsign: Optional[str] = None
    country_of_origin: Optional[str] = None
    aircraft_category: Optional[str] = None
    altitude_baro_m: Optional[float] = None
    altitude_geo_m: Optional[float] = None
    speed_ms: Optional[float] = None
    vertical_rate_ms: Optional[float] = None
    heading_deg: Optional[float] = None
    squawk: Optional[str] = None
    is_on_ground: bool = False
    source_file: Optional[str] = None


@dataclass
class DarkEventRecord:
    """Detected dark-target correlation event."""

    event_type: str  # "AIS" | "ADSB"
    entity_id: str
    entity_name: Optional[str]
    detection_id: str
    dark_start: datetime
    dark_end: Optional[datetime]
    duration_minutes: Optional[int]
    closest_approach_km: float
    threat_score: float


@dataclass
class IngestionStats:
    """Running statistics for an ingestion batch."""

    vessel_rows_parsed: int = 0
    vessel_rows_inserted: int = 0
    aircraft_rows_parsed: int = 0
    aircraft_rows_inserted: int = 0
    dark_events_detected: int = 0
    dark_events_inserted: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSV / JSON parsing helpers
# ---------------------------------------------------------------------------

_AIS_TIMESTAMP_FMTS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S.%f",
]

_ADSB_TIMESTAMP_FMTS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%fZ",
]


def _parse_dt(raw: str, fmts: List[str]) -> Optional[datetime]:
    """Try multiple datetime formats and return a UTC-aware datetime or None."""
    for fmt in fmts:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _to_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, returning None if conversion fails."""
    if val is None or str(val).strip() in ("", "None", "null", "N/A"):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_ais_csv(filepath: Path) -> Iterator[VesselTrackRecord]:
    """Parse AIS CSV file into VesselTrackRecord objects.

    Expected columns (case-insensitive): mmsi, timestamp, lon/longitude, lat/latitude,
    vessel_name, vessel_type, flag, speed, course, heading, draught, status.
    Extra columns are silently ignored.
    """
    source = str(filepath)
    with filepath.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return
        # Normalise header names
        headers = {h.strip().lower(): h for h in reader.fieldnames}

        def _get(row: Dict[str, str], *candidates: str) -> Optional[str]:
            for key in candidates:
                if key in headers:
                    val = row.get(headers[key], "").strip()
                    return val if val else None
            return None

        for row in reader:
            mmsi_raw = _get(row, "mmsi")
            ts_raw = _get(row, "timestamp", "time", "datetime", "date_time")
            lon_raw = _get(row, "lon", "longitude", "long")
            lat_raw = _get(row, "lat", "latitude")

            if not mmsi_raw or not ts_raw or lon_raw is None or lat_raw is None:
                continue

            ts = _parse_dt(ts_raw, _AIS_TIMESTAMP_FMTS)
            lon = _to_float(lon_raw)
            lat = _to_float(lat_raw)
            if ts is None or lon is None or lat is None:
                continue

            yield VesselTrackRecord(
                mmsi=mmsi_raw.strip()[:9],
                timestamp=ts,
                lon=lon,
                lat=lat,
                vessel_name=_get(row, "vessel_name", "shipname", "name"),
                vessel_type=_get(row, "vessel_type", "ship_type", "type"),
                flag=_get(row, "flag", "country", "flag_country"),
                speed_knots=_to_float(_get(row, "speed", "sog", "speed_over_ground")),
                course_deg=_to_float(_get(row, "course", "cog", "course_over_ground")),
                heading_deg=_to_float(_get(row, "heading", "true_heading")),
                draught_m=_to_float(_get(row, "draught", "draft")),
                navigational_status=_get(row, "status", "navigational_status", "nav_status"),
                source_file=source,
            )


def parse_adsb_json(filepath: Path) -> Iterator[AircraftTrackRecord]:
    """Parse ADS-B JSON file into AircraftTrackRecord objects.

    Supports OpenSky-style state vector dumps:
    Either a list of records or {"states": [[icao24, callsign, origin_country, ...]]} format.
    Also supports dump1090 line-delimited JSON.
    """
    source = str(filepath)
    raw = filepath.read_text(encoding="utf-8")

    records: List[Dict[str, Any]] = []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            if "states" in data:
                # OpenSky state vector list format
                keys = [
                    "icao24",
                    "callsign",
                    "origin_country",
                    "time_position",
                    "last_contact",
                    "longitude",
                    "latitude",
                    "baro_altitude",
                    "on_ground",
                    "velocity",
                    "true_track",
                    "vertical_rate",
                    "sensors",
                    "geo_altitude",
                    "squawk",
                    "spi",
                    "position_source",
                ]
                for sv in data["states"]:
                    if isinstance(sv, list) and len(sv) >= 7:
                        record = dict(zip(keys, sv, strict=False))
                        records.append(record)
            else:
                records = [data]
    except json.JSONDecodeError:
        # Try NDJSON (newline-delimited JSON)
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    for record in records:
        icao24 = str(record.get("icao24", "")).strip().lower()
        if not icao24:
            continue

        # Timestamp: accept Unix epoch float, or ISO string
        ts_raw = record.get("time_position") or record.get("timestamp") or record.get("time")
        ts: Optional[datetime] = None
        if isinstance(ts_raw, (int, float)):
            try:
                ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
            except (ValueError, OSError):
                pass
        elif isinstance(ts_raw, str):
            ts = _parse_dt(ts_raw, _ADSB_TIMESTAMP_FMTS)

        lon = _to_float(record.get("longitude") or record.get("lon"))
        lat = _to_float(record.get("latitude") or record.get("lat"))

        if ts is None or lon is None or lat is None:
            continue

        yield AircraftTrackRecord(
            icao24=icao24[:6],
            timestamp=ts,
            lon=lon,
            lat=lat,
            callsign=str(record.get("callsign", "") or "").strip()[:8] or None,
            country_of_origin=record.get("origin_country"),
            aircraft_category=record.get("category") or record.get("aircraft_category"),
            altitude_baro_m=_to_float(record.get("baro_altitude") or record.get("altitude")),
            altitude_geo_m=_to_float(record.get("geo_altitude")),
            speed_ms=_to_float(record.get("velocity") or record.get("speed_ms")),
            vertical_rate_ms=_to_float(record.get("vertical_rate")),
            heading_deg=_to_float(record.get("true_track") or record.get("heading_deg")),
            squawk=str(record.get("squawk", "") or "")[:4] or None,
            is_on_ground=bool(record.get("on_ground", False)),
            source_file=source,
        )


def parse_adsb_csv(filepath: Path) -> Iterator[AircraftTrackRecord]:
    """Parse ADS-B CSV file (dump1090 / ADS-B Exchange export format)."""
    source = str(filepath)
    with filepath.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return
        headers = {h.strip().lower(): h for h in reader.fieldnames}

        def _get(row: Dict[str, str], *candidates: str) -> Optional[str]:
            for key in candidates:
                if key in headers:
                    val = row.get(headers[key], "").strip()
                    return val if val else None
            return None

        for row in reader:
            icao24 = _get(row, "icao24", "hex", "transponder")
            ts_raw = _get(row, "timestamp", "time", "datetime")
            lon_raw = _get(row, "lon", "longitude", "long")
            lat_raw = _get(row, "lat", "latitude")

            if not icao24 or not ts_raw or lon_raw is None or lat_raw is None:
                continue

            ts = _parse_dt(ts_raw, _ADSB_TIMESTAMP_FMTS)
            lon = _to_float(lon_raw)
            lat = _to_float(lat_raw)
            if ts is None or lon is None or lat is None:
                continue

            yield AircraftTrackRecord(
                icao24=icao24.strip().lower()[:6],
                timestamp=ts,
                lon=lon,
                lat=lat,
                callsign=_get(row, "callsign", "flight"),
                country_of_origin=_get(row, "country", "origin_country"),
                aircraft_category=_get(row, "category", "aircraft_category", "type"),
                altitude_baro_m=_to_float(_get(row, "baro_altitude", "altitude", "alt_baro")),
                altitude_geo_m=_to_float(_get(row, "geo_altitude", "alt_geo")),
                speed_ms=_to_float(_get(row, "speed_ms", "velocity", "speed")),
                vertical_rate_ms=_to_float(_get(row, "vertical_rate", "vert_rate")),
                heading_deg=_to_float(_get(row, "heading_deg", "true_track", "track")),
                squawk=_get(row, "squawk"),
                is_on_ground=str(_get(row, "on_ground", "is_on_ground") or "").lower()
                in ("true", "1", "yes"),
                source_file=source,
            )


# ---------------------------------------------------------------------------
# Database persistence helpers
# ---------------------------------------------------------------------------


def _get_db_conn() -> psycopg2.extensions.connection:
    """Create a new PostGIS database connection."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=10,
    )


def _load_ais_dark_config(conn: psycopg2.extensions.connection) -> Tuple[float, int]:
    """Load dark-target thresholds from system_configurations table, with defaults."""
    radius_km = DEFAULT_AIS_DARK_RADIUS_KM
    time_window_h = DEFAULT_DARK_TIME_WINDOW_HOURS
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT key, value FROM system_configurations WHERE key IN (%s, %s)",
                ("ais_dark_radius_km", "ais_dark_time_window_hours"),
            )
            for row in cur.fetchall():
                if row[0] == "ais_dark_radius_km":
                    radius_km = float(row[1])
                elif row[0] == "ais_dark_time_window_hours":
                    time_window_h = int(row[1])
    except Exception:
        pass
    return radius_km, time_window_h


def _correlate_dark_ais(
    conn: psycopg2.extensions.connection,
    mmsi: str,
    vessel_name: Optional[str],
    dark_start: datetime,
    lon: float,
    lat: float,
    radius_km: float,
) -> Optional[DarkEventRecord]:
    """Spatiotemporal correlation: find nearest EO detection within radius & time window.

    Uses PostGIS ST_DWithin on the infrastructure_detections table to flag
    "dark" AIS events within dark_radius_km of a known detection.
    Returns a DarkEventRecord if a correlation is found, else None.
    """
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id::text,
                    ST_Distance(
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        centroid::geography
                    ) / 1000.0 AS distance_km
                FROM infrastructure_detections
                WHERE ST_DWithin(
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    centroid::geography,
                    %s
                )
                ORDER BY distance_km ASC
                LIMIT 1
                """,
                (lon, lat, lon, lat, radius_km * 1000),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("Dark AIS correlation query failed", error=str(exc))
        return None

    if row is None:
        return None

    dist_km: float = float(row["distance_km"])
    detection_id: str = row["id"]
    # Threat score: inverse exponential decay on distance (max 1.0 at 0 km)
    threat_score = round(max(0.0, 1.0 - (dist_km / radius_km) ** 0.5), 3)

    return DarkEventRecord(
        event_type="AIS",
        entity_id=mmsi,
        entity_name=vessel_name,
        detection_id=detection_id,
        dark_start=dark_start,
        dark_end=None,
        duration_minutes=None,
        closest_approach_km=dist_km,
        threat_score=threat_score,
    )


def _correlate_dark_adsb(
    conn: psycopg2.extensions.connection,
    icao24: str,
    callsign: Optional[str],
    dark_start: datetime,
    lon: float,
    lat: float,
    radius_km: float,
) -> Optional[DarkEventRecord]:
    """Spatiotemporal correlation for ADS-B dark events."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id::text,
                    ST_Distance(
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        centroid::geography
                    ) / 1000.0 AS distance_km
                FROM infrastructure_detections
                WHERE ST_DWithin(
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    centroid::geography,
                    %s
                )
                ORDER BY distance_km ASC
                LIMIT 1
                """,
                (lon, lat, lon, lat, radius_km * 1000),
            )
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("Dark ADS-B correlation query failed", error=str(exc))
        return None

    if row is None:
        return None

    dist_km = float(row["distance_km"])
    detection_id = row["id"]
    threat_score = round(max(0.0, 1.0 - (dist_km / radius_km) ** 0.5), 3)

    return DarkEventRecord(
        event_type="ADSB",
        entity_id=icao24,
        entity_name=callsign,
        detection_id=detection_id,
        dark_start=dark_start,
        dark_end=None,
        duration_minutes=None,
        closest_approach_km=dist_km,
        threat_score=threat_score,
    )


def _insert_vessel_tracks(
    conn: psycopg2.extensions.connection, records: List[VesselTrackRecord]
) -> int:
    """Bulk-insert vessel track records using execute_values for efficiency."""
    if not records:
        return 0
    rows = [
        (
            r.mmsi,
            r.vessel_name,
            r.vessel_type,
            r.flag,
            r.timestamp,
            r.lon,
            r.lat,
            r.speed_knots,
            r.course_deg,
            r.heading_deg,
            r.draught_m,
            r.navigational_status,
            False,  # is_dark (set by correlation pass)
            r.source_file,
        )
        for r in records
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO vessel_tracks (
                mmsi, vessel_name, vessel_type, flag, timestamp, lon, lat,
                speed_knots, course_deg, heading_deg, draught_m,
                navigational_status, is_dark, source_file
            ) VALUES %s
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
    conn.commit()
    return len(records)


def _insert_aircraft_tracks(
    conn: psycopg2.extensions.connection, records: List[AircraftTrackRecord]
) -> int:
    """Bulk-insert aircraft track records."""
    if not records:
        return 0
    rows = [
        (
            r.icao24,
            r.callsign,
            r.country_of_origin,
            r.aircraft_category,
            r.timestamp,
            r.lon,
            r.lat,
            r.altitude_baro_m,
            r.altitude_geo_m,
            r.speed_ms,
            r.vertical_rate_ms,
            r.heading_deg,
            r.squawk,
            r.is_on_ground,
            False,  # is_dark
            r.source_file,
        )
        for r in records
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO aircraft_tracks (
                icao24, callsign, country_of_origin, aircraft_category,
                timestamp, lon, lat, altitude_baro_m, altitude_geo_m,
                speed_ms, vertical_rate_ms, heading_deg, squawk,
                is_on_ground, is_dark, source_file
            ) VALUES %s
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
    conn.commit()
    return len(records)


def _insert_dark_events(conn: psycopg2.extensions.connection, events: List[DarkEventRecord]) -> int:
    """Insert detected dark-target correlation events."""
    if not events:
        return 0
    rows = [
        (
            e.event_type,
            e.entity_id,
            e.entity_name,
            e.detection_id,
            e.dark_start,
            e.dark_end,
            e.duration_minutes,
            e.closest_approach_km,
            e.threat_score,
        )
        for e in events
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO dark_target_events (
                event_type, entity_id, entity_name, detection_id,
                dark_start, dark_end, duration_minutes,
                closest_approach_km, threat_score
            ) VALUES %s
            """,
            rows,
        )
    conn.commit()
    return len(events)


# ---------------------------------------------------------------------------
# Dark-event detection by analysing gaps in consecutive track positions
# ---------------------------------------------------------------------------


def _detect_dark_gaps_ais(
    tracks: List[VesselTrackRecord],
    dark_threshold_minutes: int = 60,
) -> List[Tuple[VesselTrackRecord, VesselTrackRecord]]:
    """Detect gaps > threshold between consecutive AIS positions for same MMSI.

    Returns list of (track_before_dark, track_after_dark) tuples.
    """
    from itertools import groupby

    gaps: List[Tuple[VesselTrackRecord, VesselTrackRecord]] = []
    key = lambda r: r.mmsi  # noqa: E731
    for _mmsi, group in groupby(sorted(tracks, key=lambda r: (r.mmsi, r.timestamp)), key=key):
        track_list = list(group)
        for i in range(len(track_list) - 1):
            t0 = track_list[i]
            t1 = track_list[i + 1]
            delta = (t1.timestamp - t0.timestamp).total_seconds() / 60
            if delta >= dark_threshold_minutes:
                gaps.append((t0, t1))
    return gaps


def _detect_dark_gaps_adsb(
    tracks: List[AircraftTrackRecord],
    dark_threshold_minutes: int = 30,
) -> List[Tuple[AircraftTrackRecord, AircraftTrackRecord]]:
    """Detect gaps > threshold between consecutive ADS-B positions for same ICAO24."""
    from itertools import groupby

    gaps: List[Tuple[AircraftTrackRecord, AircraftTrackRecord]] = []
    key = lambda r: r.icao24  # noqa: E731
    for _icao, group in groupby(sorted(tracks, key=lambda r: (r.icao24, r.timestamp)), key=key):
        track_list = list(group)
        for i in range(len(track_list) - 1):
            t0 = track_list[i]
            t1 = track_list[i + 1]
            delta = (t1.timestamp - t0.timestamp).total_seconds() / 60
            if delta >= dark_threshold_minutes:
                gaps.append((t0, t1))
    return gaps


# ---------------------------------------------------------------------------
# Main ingestion orchestrator
# ---------------------------------------------------------------------------


class TelemetryIngestor:
    """Orchestrates local AIS/ADS-B telemetry ingest and dark-target correlation.

    Usage (CLI):
        from src.etl.telemetry_ingest import TelemetryIngestor
        ingestor = TelemetryIngestor()
        stats = ingestor.ingest_directory(Path("/mnt/external_hdd/telemetry"))
        print(stats)
    """

    def __init__(self, db_conn: Optional[psycopg2.extensions.connection] = None) -> None:
        self._external_conn = db_conn
        self._ais_radius_km = DEFAULT_AIS_DARK_RADIUS_KM
        self._adsb_radius_km = DEFAULT_ADSB_DARK_RADIUS_KM

    def _get_conn(self) -> psycopg2.extensions.connection:
        if self._external_conn is not None:
            return self._external_conn
        return _get_db_conn()

    def ingest_ais_csv(self, filepath: Path) -> IngestionStats:
        """Ingest a single AIS CSV file."""
        stats = IngestionStats()
        records: List[VesselTrackRecord] = []
        try:
            for rec in parse_ais_csv(filepath):
                records.append(rec)
                stats.vessel_rows_parsed += 1
        except Exception as exc:
            stats.errors.append(f"AIS parse error {filepath}: {exc}")
            logger.error("AIS CSV parse error", filepath=str(filepath), error=str(exc))
            return stats

        try:
            conn = self._get_conn()
            self._ais_radius_km, _ = _load_ais_dark_config(conn)
            stats.vessel_rows_inserted = _insert_vessel_tracks(conn, records)

            # Dark-event detection pass
            dark_gaps = _detect_dark_gaps_ais(records)
            dark_events: List[DarkEventRecord] = []
            for t0, t1 in dark_gaps:
                evt = _correlate_dark_ais(
                    conn,
                    t0.mmsi,
                    t0.vessel_name,
                    t0.timestamp,
                    t0.lon,
                    t0.lat,
                    self._ais_radius_km,
                )
                if evt is not None:
                    duration = int((t1.timestamp - t0.timestamp).total_seconds() / 60)
                    evt.dark_end = t1.timestamp
                    evt.duration_minutes = duration
                    dark_events.append(evt)

            stats.dark_events_detected = len(dark_events)
            stats.dark_events_inserted = _insert_dark_events(conn, dark_events)
        except Exception as exc:
            stats.errors.append(f"AIS DB error {filepath}: {exc}")
            logger.error("AIS DB insert error", filepath=str(filepath), error=str(exc))

        logger.info(
            "AIS CSV ingestion complete",
            filepath=str(filepath),
            parsed=stats.vessel_rows_parsed,
            inserted=stats.vessel_rows_inserted,
            dark_events=stats.dark_events_inserted,
        )
        return stats

    def ingest_adsb_file(self, filepath: Path) -> IngestionStats:
        """Ingest a single ADS-B file (JSON or CSV auto-detected by extension)."""
        stats = IngestionStats()
        records: List[AircraftTrackRecord] = []
        suffix = filepath.suffix.lower()
        try:
            if suffix == ".json" or suffix == ".ndjson":
                for rec in parse_adsb_json(filepath):
                    records.append(rec)
                    stats.aircraft_rows_parsed += 1
            elif suffix == ".csv":
                for rec in parse_adsb_csv(filepath):
                    records.append(rec)
                    stats.aircraft_rows_parsed += 1
            else:
                stats.errors.append(f"Unsupported ADS-B file extension: {suffix}")
                return stats
        except Exception as exc:
            stats.errors.append(f"ADS-B parse error {filepath}: {exc}")
            logger.error("ADS-B file parse error", filepath=str(filepath), error=str(exc))
            return stats

        try:
            conn = self._get_conn()
            stats.aircraft_rows_inserted = _insert_aircraft_tracks(conn, records)

            dark_gaps = _detect_dark_gaps_adsb(records)
            dark_events: List[DarkEventRecord] = []
            for t0, t1 in dark_gaps:
                evt = _correlate_dark_adsb(
                    conn,
                    t0.icao24,
                    t0.callsign,
                    t0.timestamp,
                    t0.lon,
                    t0.lat,
                    self._adsb_radius_km,
                )
                if evt is not None:
                    duration = int((t1.timestamp - t0.timestamp).total_seconds() / 60)
                    evt.dark_end = t1.timestamp
                    evt.duration_minutes = duration
                    dark_events.append(evt)

            stats.dark_events_detected = len(dark_events)
            stats.dark_events_inserted = _insert_dark_events(conn, dark_events)
        except Exception as exc:
            stats.errors.append(f"ADS-B DB error {filepath}: {exc}")
            logger.error("ADS-B DB insert error", filepath=str(filepath), error=str(exc))

        logger.info(
            "ADS-B file ingestion complete",
            filepath=str(filepath),
            parsed=stats.aircraft_rows_parsed,
            inserted=stats.aircraft_rows_inserted,
            dark_events=stats.dark_events_inserted,
        )
        return stats

    def ingest_directory(self, directory: Path) -> IngestionStats:
        """Recursively scan a directory and ingest all supported telemetry files.

        AIS: *.csv files with 'ais' or 'vessel' in name.
        ADS-B: *.json, *.ndjson, or *.csv files with 'adsb', 'aircraft', or 'flight' in name.
        """
        if not directory.is_dir():
            raise FileNotFoundError(f"Telemetry directory not found: {directory}")

        totals = IngestionStats()
        for fp in sorted(directory.rglob("*")):
            if not fp.is_file():
                continue
            name_lower = fp.stem.lower()
            suffix = fp.suffix.lower()

            # Route to appropriate parser by naming convention
            if suffix == ".csv" and any(kw in name_lower for kw in ("ais", "vessel", "mmsi")):
                stats = self.ingest_ais_csv(fp)
            elif suffix in (".json", ".ndjson") and any(
                kw in name_lower for kw in ("adsb", "aircraft", "flight", "opensky")
            ):
                stats = self.ingest_adsb_file(fp)
            elif suffix == ".csv" and any(
                kw in name_lower for kw in ("adsb", "aircraft", "flight")
            ):
                stats = self.ingest_adsb_file(fp)
            else:
                continue

            totals.vessel_rows_parsed += stats.vessel_rows_parsed
            totals.vessel_rows_inserted += stats.vessel_rows_inserted
            totals.aircraft_rows_parsed += stats.aircraft_rows_parsed
            totals.aircraft_rows_inserted += stats.aircraft_rows_inserted
            totals.dark_events_detected += stats.dark_events_detected
            totals.dark_events_inserted += stats.dark_events_inserted
            totals.errors.extend(stats.errors)

        logger.info(
            "Directory telemetry ingestion complete",
            directory=str(directory),
            vessel_parsed=totals.vessel_rows_parsed,
            vessel_inserted=totals.vessel_rows_inserted,
            aircraft_parsed=totals.aircraft_rows_parsed,
            aircraft_inserted=totals.aircraft_rows_inserted,
            dark_events=totals.dark_events_inserted,
            errors=len(totals.errors),
        )
        return totals


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
telemetry_ingestor = TelemetryIngestor()
