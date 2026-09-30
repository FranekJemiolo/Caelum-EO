#!/usr/bin/env python3
"""Export curated static GEOINT demo data for Project Caelum-EO GitHub Pages demo.

Connects to local PostGIS database if available; otherwise deterministically
synthesizes high-fidelity intelligence payloads:
- detections.geojson (Infrastructure detections in Suwalki Corridor)
- analytics.json (Logistics network graph, velocity time-series, zones, SITREPs, audit trails, dark events)
- imagery/*.webp (T0 baseline, T1 monitoring, and change mask image chips)

Project Caelum-EO (github.com/FranekJemiolo/Caelum-EO)
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA_DIR = REPO_ROOT / "src" / "frontend" / "public" / "demo-data"
IMAGERY_DIR = DEMO_DATA_DIR / "imagery"

# Base coordinates: Strategic Suwalki Corridor (Eastern Europe)
CENTER_LON = 23.225
CENTER_LAT = 54.155

BASE_TIME = datetime(2026, 9, 15, 10, 30, 0, tzinfo=timezone.utc)


def ensure_directories() -> None:
    DEMO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGERY_DIR.mkdir(parents=True, exist_ok=True)


def generate_curated_detections() -> Dict[str, Any]:
    """Generate high-fidelity GeoJSON FeatureCollection of GEOINT detections."""
    features = [
        {
            "id": "det-radar-001",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.1812, 54.1610],
                        [23.1888, 54.1610],
                        [23.1888, 54.1690],
                        [23.1812, 54.1690],
                        [23.1812, 54.1610],
                    ]
                ],
            },
            "properties": {
                "id": "det-radar-001",
                "classification": "RADAR_DOME",
                "confidence": 0.94,
                "priority_score": 0.96,
                "review_status": "VERIFIED",
                "analyst_notes": "Confirmed early-warning phased array radar dome on elevated terrain. Reinforced concrete perimeter wall identified.",
                "zone_id": "ZONE-ALPHA",
                "created_at": (BASE_TIME - timedelta(days=2)).isoformat(),
                "t0_timestamp": "2026-06-01T10:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 1420.0,
                "centroid": [23.1850, 54.1650],
                "elevation_m": 242.0,
                "bbox": [23.1812, 54.1610, 23.1888, 54.1690],
            },
        },
        {
            "id": "det-runway-002",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.2050, 54.1180],
                        [23.2350, 54.1180],
                        [23.2350, 54.1240],
                        [23.2050, 54.1240],
                        [23.2050, 54.1180],
                    ]
                ],
            },
            "properties": {
                "id": "det-runway-002",
                "classification": "RUNWAY_TAXIWAY",
                "confidence": 0.91,
                "priority_score": 0.89,
                "review_status": "PENDING",
                "analyst_notes": "450m tactical runway extension with heavy asphalt overlay and parallel taxiway apron. Rapid construction over 45 days.",
                "zone_id": "ZONE-ALPHA",
                "created_at": (BASE_TIME - timedelta(days=1)).isoformat(),
                "t0_timestamp": "2026-06-01T10:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 18500.0,
                "centroid": [23.2200, 54.1210],
                "elevation_m": 165.0,
                "bbox": [23.2050, 54.1180, 23.2350, 54.1240],
            },
        },
        {
            "id": "det-depot-003",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.2680, 54.1910],
                        [23.2820, 54.1910],
                        [23.2820, 54.2010],
                        [23.2680, 54.2010],
                        [23.2680, 54.1910],
                    ]
                ],
            },
            "properties": {
                "id": "det-depot-003",
                "classification": "LOGISTICS_DEPOT",
                "confidence": 0.88,
                "priority_score": 0.84,
                "review_status": "VERIFIED",
                "analyst_notes": "Forward ammunition and fuel distribution hub with 6 hardened storage bunkers and dual rail siding spurs.",
                "zone_id": "ZONE-BRAVO",
                "created_at": (BASE_TIME - timedelta(days=5)).isoformat(),
                "t0_timestamp": "2026-05-15T11:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 9600.0,
                "centroid": [23.2750, 54.1960],
                "elevation_m": 178.0,
                "bbox": [23.2680, 54.1910, 23.2820, 54.2010],
            },
        },
        {
            "id": "det-sam-004",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.1340, 54.2050],
                        [23.1460, 54.2050],
                        [23.1460, 54.2150],
                        [23.1340, 54.2150],
                        [23.1340, 54.2050],
                    ]
                ],
            },
            "properties": {
                "id": "det-sam-004",
                "classification": "DEFENSE_REVETMENT",
                "confidence": 0.86,
                "priority_score": 0.82,
                "review_status": "PENDING",
                "analyst_notes": "Hexagonal surface-to-air missile revetment battery with central guidance radar pad and four launcher positions.",
                "zone_id": "ZONE-BRAVO",
                "created_at": (BASE_TIME - timedelta(days=3)).isoformat(),
                "t0_timestamp": "2026-06-01T10:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 4300.0,
                "centroid": [23.1400, 54.2100],
                "elevation_m": 215.0,
                "bbox": [23.1340, 54.2050, 23.1460, 54.2150],
            },
        },
        {
            "id": "det-bunker-005",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.3040, 54.0810],
                        [23.3160, 54.0810],
                        [23.3160, 54.0890],
                        [23.3040, 54.0890],
                        [23.3040, 54.0810],
                    ]
                ],
            },
            "properties": {
                "id": "det-bunker-005",
                "classification": "COMMAND_BUNKER",
                "confidence": 0.82,
                "priority_score": 0.77,
                "review_status": "PENDING",
                "analyst_notes": "Sub-surface command and communications bunker excavation. Buried cable trenches connect to southern microwave relay.",
                "zone_id": "ZONE-CHARLIE",
                "created_at": (BASE_TIME - timedelta(days=4)).isoformat(),
                "t0_timestamp": "2026-06-01T10:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 2100.0,
                "centroid": [23.3100, 54.0850],
                "elevation_m": 190.0,
                "bbox": [23.3040, 54.0810, 23.3160, 54.0890],
            },
        },
        {
            "id": "det-depot-006",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.1620, 54.0950],
                        [23.1740, 54.0950],
                        [23.1740, 54.1050],
                        [23.1620, 54.1050],
                        [23.1620, 54.0950],
                    ]
                ],
            },
            "properties": {
                "id": "det-depot-006",
                "classification": "LOGISTICS_DEPOT",
                "confidence": 0.79,
                "priority_score": 0.71,
                "review_status": "VERIFIED",
                "analyst_notes": "Vehicle maintenance workshop and heavy equipment staging park.",
                "zone_id": "ZONE-ALPHA",
                "created_at": (BASE_TIME - timedelta(days=8)).isoformat(),
                "t0_timestamp": "2026-05-15T11:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 5800.0,
                "centroid": [23.1680, 54.1000],
                "elevation_m": 155.0,
                "bbox": [23.1620, 54.0950, 23.1740, 54.1050],
            },
        },
        {
            "id": "det-revetment-007",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.2380, 54.1680],
                        [23.2480, 54.1680],
                        [23.2480, 54.1760],
                        [23.2380, 54.1760],
                        [23.2380, 54.1680],
                    ]
                ],
            },
            "properties": {
                "id": "det-revetment-007",
                "classification": "DEFENSE_REVETMENT",
                "confidence": 0.75,
                "priority_score": 0.68,
                "review_status": "REJECTED",
                "analyst_notes": "False positive: Civilian gravel quarry excavation confirmed by high-res commercial imagery.",
                "zone_id": "ZONE-BRAVO",
                "created_at": (BASE_TIME - timedelta(days=6)).isoformat(),
                "t0_timestamp": "2026-06-01T10:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 3100.0,
                "centroid": [23.2430, 54.1720],
                "elevation_m": 168.0,
                "bbox": [23.2380, 54.1680, 23.2480, 54.1760],
            },
        },
        {
            "id": "det-radar-008",
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.3320, 54.1520],
                        [23.3420, 54.1520],
                        [23.3420, 54.1600],
                        [23.3320, 54.1600],
                        [23.3320, 54.1520],
                    ]
                ],
            },
            "properties": {
                "id": "det-radar-008",
                "classification": "RADAR_DOME",
                "confidence": 0.89,
                "priority_score": 0.85,
                "review_status": "PENDING",
                "analyst_notes": "Secondary counter-battery radar mast and generator trailer cluster.",
                "zone_id": "ZONE-CHARLIE",
                "created_at": (BASE_TIME - timedelta(hours=18)).isoformat(),
                "t0_timestamp": "2026-06-01T10:00:00Z",
                "t1_timestamp": "2026-09-15T10:30:00Z",
                "area_sq_meters": 820.0,
                "centroid": [23.3370, 54.1560],
                "elevation_m": 228.0,
                "bbox": [23.3320, 54.1520, 23.3420, 54.1600],
            },
        },
    ]

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def generate_curated_analytics(geojson: Dict[str, Any]) -> Dict[str, Any]:
    """Generate static analytics payload: network graph, velocity, zones, sitreps, and audit."""
    nodes = []
    node_ids = []
    for f in geojson["features"]:
        props = f["properties"]
        node_ids.append(props["id"])
        nodes.append(
            {
                "id": props["id"],
                "classification": props["classification"],
                "lon": props["centroid"][0],
                "lat": props["centroid"][1],
                "priority_score": props["priority_score"],
                "threat_score": round(props["priority_score"] * 0.9, 2),
                "dark_event_count": 3 if "radar" in props["id"] or "depot" in props["id"] else 1,
                "zone_id": props["zone_id"],
                "area_sq_m": props["area_sq_meters"],
            }
        )

    links = [
        {
            "source": "det-radar-001",
            "target": "det-runway-002",
            "flow_count": 8,
            "mean_dark_threat": 0.85,
            "distance_km": 5.4,
            "entity_type": "ADSB",
        },
        {
            "source": "det-depot-003",
            "target": "det-runway-002",
            "flow_count": 14,
            "mean_dark_threat": 0.78,
            "distance_km": 9.1,
            "entity_type": "AIS",
        },
        {
            "source": "det-radar-001",
            "target": "det-sam-004",
            "flow_count": 6,
            "mean_dark_threat": 0.91,
            "distance_km": 5.8,
            "entity_type": "ADSB",
        },
        {
            "source": "det-depot-003",
            "target": "det-sam-004",
            "flow_count": 5,
            "mean_dark_threat": 0.65,
            "distance_km": 11.2,
            "entity_type": "AIS",
        },
        {
            "source": "det-runway-002",
            "target": "det-bunker-005",
            "flow_count": 9,
            "mean_dark_threat": 0.72,
            "distance_km": 7.3,
            "entity_type": "ADSB",
        },
        {
            "source": "det-depot-006",
            "target": "det-radar-001",
            "flow_count": 4,
            "mean_dark_threat": 0.55,
            "distance_km": 7.5,
            "entity_type": "AIS",
        },
        {
            "source": "det-radar-008",
            "target": "det-bunker-005",
            "flow_count": 7,
            "mean_dark_threat": 0.81,
            "distance_km": 8.2,
            "entity_type": "ADSB",
        },
        {
            "source": "det-depot-003",
            "target": "det-radar-008",
            "flow_count": 6,
            "mean_dark_threat": 0.69,
            "distance_km": 6.3,
            "entity_type": "AIS",
        },
    ]

    centrality_scores = {
        "det-radar-001": 0.68,
        "det-depot-003": 0.82,
        "det-runway-002": 0.75,
        "det-sam-004": 0.44,
        "det-bunker-005": 0.51,
        "det-depot-006": 0.28,
        "det-revetment-007": 0.05,
        "det-radar-008": 0.39,
    }

    threat_flow_scores = {
        "det-radar-001": 4.12,
        "det-depot-003": 5.86,
        "det-runway-002": 4.95,
        "det-sam-004": 3.10,
        "det-bunker-005": 2.85,
        "det-depot-006": 1.45,
        "det-revetment-007": 0.15,
        "det-radar-008": 2.65,
    }

    network_snapshot = {
        "id": "snap-demo-v5",
        "snapshot_label": "DEMO-TACTICAL-SNAPSHOT-SUWALKI",
        "computation_timestamp": BASE_TIME.isoformat(),
        "node_count": len(nodes),
        "edge_count": len(links),
        "critical_node_ids": ["det-depot-003", "det-runway-002", "det-radar-001"],
        "predicted_expansion_ids": ["det-bunker-005", "det-sam-004"],
        "centrality_scores": centrality_scores,
        "threat_flow_scores": threat_flow_scores,
        "rl_episode_rewards": [0.12, 0.25, 0.41, 0.58, 0.72, 0.85, 0.91, 0.96],
        "created_at": BASE_TIME.isoformat(),
        "nodes": nodes,
        "links": links,
        "edges": links,
    }

    # Velocity time-series
    months = [
        "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"
    ]
    velocity_time_series = [
        {"month": "2025-10", "area_built_sqm": 450, "new_detections_count": 0, "mean_velocity": 15.0},
        {"month": "2025-11", "area_built_sqm": 800, "new_detections_count": 0, "mean_velocity": 26.6},
        {"month": "2025-12", "area_built_sqm": 620, "new_detections_count": 0, "mean_velocity": 20.0},
        {"month": "2026-01", "area_built_sqm": 1200, "new_detections_count": 1, "mean_velocity": 38.7},
        {"month": "2026-02", "area_built_sqm": 1950, "new_detections_count": 1, "mean_velocity": 69.6},
        {"month": "2026-03", "area_built_sqm": 3100, "new_detections_count": 1, "mean_velocity": 100.0},
        {"month": "2026-04", "area_built_sqm": 4800, "new_detections_count": 2, "mean_velocity": 160.0},
        {"month": "2026-05", "area_built_sqm": 7200, "new_detections_count": 3, "mean_velocity": 232.2},
        {"month": "2026-06", "area_built_sqm": 9400, "new_detections_count": 4, "mean_velocity": 313.3},
        {"month": "2026-07", "area_built_sqm": 12800, "new_detections_count": 5, "mean_velocity": 412.9},
        {"month": "2026-08", "area_built_sqm": 16400, "new_detections_count": 6, "mean_velocity": 529.0},
        {"month": "2026-09", "area_built_sqm": 21850, "new_detections_count": 8, "mean_velocity": 728.3},
    ]

    zones_summary = [
        {
            "zone_id": "ZONE-ALPHA",
            "name": "Suwalki Northern Ridge",
            "total_detections": 3,
            "verified_count": 2,
            "pending_count": 1,
            "rejected_count": 0,
            "total_area_sqm": 25720.0,
            "threat_level": "CRITICAL",
            "highest_priority": 0.96,
        },
        {
            "zone_id": "ZONE-BRAVO",
            "name": "Druskininkai Rail Corridor",
            "total_detections": 3,
            "verified_count": 1,
            "pending_count": 1,
            "rejected_count": 1,
            "total_area_sqm": 17000.0,
            "threat_level": "ELEVATED",
            "highest_priority": 0.84,
        },
        {
            "zone_id": "ZONE-CHARLIE",
            "name": "Augustow Forest Sector",
            "total_detections": 2,
            "verified_count": 0,
            "pending_count": 2,
            "rejected_count": 0,
            "total_area_sqm": 2920.0,
            "threat_level": "MODERATE",
            "highest_priority": 0.85,
        },
    ]

    dark_events = [
        {
            "id": "de-001",
            "event_type": "ADSB",
            "entity_id": "4852bf",
            "entity_name": "MIL-IL76-CARGO",
            "detection_id": "det-runway-002",
            "threat_score": 0.92,
            "closest_approach_km": 1.4,
            "dark_start": "2026-09-14T02:15:00Z",
            "dark_end": "2026-09-14T04:45:00Z",
            "duration_minutes": 150,
            "lon": 23.218,
            "lat": 54.122,
        },
        {
            "id": "de-002",
            "event_type": "AIS",
            "entity_id": "273456789",
            "entity_name": "CARGO-VOLGA-9",
            "detection_id": "det-depot-003",
            "threat_score": 0.84,
            "closest_approach_km": 3.8,
            "dark_start": "2026-09-13T18:30:00Z",
            "dark_end": "2026-09-14T01:15:00Z",
            "duration_minutes": 405,
            "lon": 23.272,
            "lat": 54.198,
        },
        {
            "id": "de-003",
            "event_type": "ADSB",
            "entity_id": "5041aa",
            "entity_name": "RECON-UAV-FORPOST",
            "detection_id": "det-radar-001",
            "threat_score": 0.96,
            "closest_approach_km": 0.8,
            "dark_start": "2026-09-15T06:00:00Z",
            "dark_end": "2026-09-15T09:30:00Z",
            "duration_minutes": 210,
            "lon": 23.186,
            "lat": 54.164,
        },
        {
            "id": "de-004",
            "event_type": "ADSB",
            "entity_id": "5011dd",
            "entity_name": "HELO-MI8-AMTSh",
            "detection_id": "det-sam-004",
            "threat_score": 0.79,
            "closest_approach_km": 2.2,
            "dark_start": "2026-09-14T14:20:00Z",
            "dark_end": "2026-09-14T16:00:00Z",
            "duration_minutes": 100,
            "lon": 23.142,
            "lat": 54.208,
        },
    ]

    sitreps = [
        {
            "id": "sitrep-demo-001",
            "title": "SITREP-20260915-SUWALKI: Rapid Logistic Build-out & Radar Activation",
            "classification": "TOP SECRET // NOFORN // AIR-GAPPED GEOINT",
            "author": "Autonomous SITREP Generator (Local DeepSeek-R1-14B)",
            "created_at": "2026-09-15T10:45:00Z",
            "zone_id": "ZONE-ALPHA",
            "executive_summary": "High-confidence automated detection identifies an active logistical surge in the Suwalki Surveillance Sector. The completion of a 450m tactical runway extension (det-runway-002) paired with the operationalization of an early-warning phased array radar dome (det-radar-001) suggests forward air-ground integration within the past 45 days.",
            "tactical_assessment": "The reinforcement learning supply chain model reveals critical dependency flow from Druskininkai Rail Depot (det-depot-003) directly to the newly surfaced airfield. Combined with 4 correlated dark ADS-B cargo flights (IL-76 transponder blackout), adversary intent points to an operational forward logistics base.",
            "key_findings": [
                "Early Warning Radar (det-radar-001) operational on high-elevation ridge line (+242m ASL).",
                "Tactical Airstrip extension (det-runway-002) paved with heavy asphalt (18,500 m² total surface).",
                "Supply chain choke-point localized at depot det-depot-003 with betweenness centrality of 0.82.",
            ],
            "recommended_actions": [
                "Task Sentinel-1 SAR constellation for coherent interferometric change detection (InSAR) on suspected bunker det-bunker-005.",
                "Broadcast Cursor-on-Target (CoT) tactical marker to NATO enhanced Forward Presence (eFP) tactical edge units via ATAK.",
                "Escalate Surveillance Priority for Sector ZONE-ALPHA to Level 1.",
            ],
        },
        {
            "id": "sitrep-demo-002",
            "title": "SITREP-20260912-SECTOR-BRAVO: Anti-Air Defense Net Hardening",
            "classification": "SECRET // REL TO NATO",
            "author": "Autonomous SITREP Generator (Local LLaMA-3.3-70B)",
            "created_at": "2026-09-12T16:00:00Z",
            "zone_id": "ZONE-BRAVO",
            "executive_summary": "Verification of earthwork revetments confirms installation of surface-to-air missile guidance radar pads (det-sam-004) flanking the primary supply highway.",
            "tactical_assessment": "Air defense umbrella now overlaps with Suwalki Northern Ridge corridor, creating a low-altitude anti-access/area-denial (A2/AD) bubble up to FL250.",
            "key_findings": [
                "Revetment layout matches S-350 / Buk-M3 air defense battery configuration.",
                "Rejection of quarry anomaly det-revetment-007 prevents false alarm tasking.",
            ],
            "recommended_actions": [
                "Simulate 3D radar viewshed coverage using SRTM 30m DEM to detect low-altitude terrain masking corridors.",
            ],
        },
    ]

    audit_logs = {
        "det-radar-001": [
            {
                "timestamp": "2026-09-13T11:20:00Z",
                "analyst": "system_prithvi_v2",
                "action": "AUTO_DETECTED",
                "notes": "Anomaly detected with confidence 0.94 in Sentinel-2 B04/B8A reflectance ratio.",
            },
            {
                "timestamp": "2026-09-13T14:45:00Z",
                "analyst": "analyst_viper",
                "action": "STATUS_CHANGED",
                "previous_status": "PENDING",
                "new_status": "VERIFIED",
                "notes": "Confirmed optical dome signature; cross-referenced with Sentinel-1 VV/VH backscatter increase (+4.2 dB).",
            },
        ],
        "det-runway-002": [
            {
                "timestamp": "2026-09-14T09:00:00Z",
                "analyst": "system_prithvi_v2",
                "action": "AUTO_DETECTED",
                "notes": "Linear anomaly detected across pixels (40,50) to (65,210). Area: 18,500 m².",
            },
            {
                "timestamp": "2026-09-14T11:15:00Z",
                "analyst": "analyst_eagle",
                "action": "PRIORITY_ESCALATED",
                "notes": "Escalated priority to 0.89 due to proximity to Suwalki rail corridor.",
            },
        ],
    }

    comments = {
        "det-radar-001": [
            {
                "id": "c-001",
                "author": "analyst_viper",
                "role": "analyst",
                "timestamp": "2026-09-13T15:00:00Z",
                "text": "Radome material appears composite dielectric. Thermal infrared shows active heat signature from power generator unit.",
            },
            {
                "id": "c-002",
                "author": "admin",
                "role": "admin",
                "timestamp": "2026-09-14T08:30:00Z",
                "text": "Cursor-on-Target marker broadcasted to tactical edge network via ATAK server.",
            },
        ],
        "det-runway-002": [
            {
                "id": "c-003",
                "author": "analyst_eagle",
                "role": "analyst",
                "timestamp": "2026-09-14T10:00:00Z",
                "text": "Asphalt curing marks visible in Sentinel-2 B04. Estimated completion within 7 days.",
            }
        ],
    }

    return {
        "network": network_snapshot,
        "velocity": {
            "overall_velocity_sqm_per_month": 3420.5,
            "lookback_months": 12,
            "time_series": velocity_time_series,
        },
        "zones": zones_summary,
        "dark_events": dark_events,
        "sitreps": sitreps,
        "audit": audit_logs,
        "comments": comments,
        "last_updated": BASE_TIME.isoformat(),
    }


def generate_synthetic_image_chips() -> None:
    """Generate deterministic, compressed WebP image chips for T0, T1, and mask."""
    width, height = 512, 512

    # --- 1. T0 Baseline Image (Agricultural & forest landscape in summer) ---
    t0_img = Image.new("RGB", (width, height), (38, 55, 30))
    draw_t0 = ImageDraw.Draw(t0_img)

    # Rolling fields (varied green, olive, ochre polygons)
    draw_t0.polygon([(0, 0), (220, 0), (240, 180), (0, 160)], fill=(54, 76, 38))
    draw_t0.polygon([(220, 0), (512, 0), (512, 210), (240, 180)], fill=(78, 92, 45))
    draw_t0.polygon([(0, 160), (240, 180), (260, 360), (0, 340)], fill=(92, 105, 52))
    draw_t0.polygon([(240, 180), (512, 210), (512, 400), (260, 360)], fill=(62, 82, 42))
    draw_t0.polygon([(0, 340), (260, 360), (280, 512), (0, 512)], fill=(48, 68, 35))
    draw_t0.polygon([(260, 360), (512, 400), (512, 512), (280, 512)], fill=(70, 88, 48))

    # Natural unpaved dirt path
    draw_t0.line([(30, 260), (140, 245), (280, 270), (480, 290)], fill=(120, 110, 88), width=3)
    # Natural stream / tree line
    draw_t0.line([(180, 0), (210, 180), (190, 340), (230, 512)], fill=(28, 42, 26), width=12)

    # Slight blur & noise for realistic satellite texture
    t0_img = t0_img.filter(ImageFilter.GaussianBlur(radius=0.8))

    # --- 2. T1 Monitoring Image (Constructed infrastructure anomalies) ---
    t1_img = t0_img.copy()
    draw_t1 = ImageDraw.Draw(t1_img)

    # Anomaly 1: Tactical Runway Extension (asphalt black/slate runway with white centerline)
    runway_box = [(80, 80), (432, 140)]
    draw_t1.rectangle(runway_box, fill=(35, 40, 48), outline=(65, 75, 88), width=2)
    # Centerline dashes
    for x in range(100, 420, 24):
        draw_t1.line([(x, 110), (x + 14, 110)], fill=(225, 230, 240), width=2)
    # Apron tarmac
    draw_t1.polygon([(240, 140), (330, 140), (330, 200), (240, 200)], fill=(50, 56, 68))

    # Anomaly 2: Hardened Phased-Array Radar Radome Facility
    # Security fence / cleared clearing
    radar_center = (320, 360)
    draw_t1.ellipse([radar_center[0] - 65, radar_center[1] - 65, radar_center[0] + 65, radar_center[1] + 65], fill=(85, 92, 78), outline=(130, 140, 120), width=2)
    # Octagonal concrete pad
    draw_t1.regular_polygon((radar_center, 44), 8, fill=(115, 122, 130), outline=(160, 170, 180))
    # Bright white geodesic radome sphere with shadow
    draw_t1.ellipse([radar_center[0] - 22, radar_center[1] - 22, radar_center[0] + 22, radar_center[1] + 22], fill=(235, 240, 248), outline=(180, 190, 205), width=2)
    draw_t1.ellipse([radar_center[0] - 14, radar_center[1] - 14, radar_center[0] + 10, radar_center[1] + 10], fill=(255, 255, 255))

    # Anomaly 3: Logistics Depot Revetments / Storage Bunkers
    draw_t1.rectangle([(70, 330), (160, 410)], fill=(75, 82, 70), outline=(110, 120, 105))
    draw_t1.rectangle([(85, 345), (115, 395)], fill=(45, 52, 62))
    draw_t1.rectangle([(125, 345), (150, 395)], fill=(45, 52, 62))

    # --- 3. Change Segmentation Mask (Tactical GEOINT highlight) ---
    mask_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_mask = ImageDraw.Draw(mask_img)

    # Amber/Cyan glowing anomaly zones
    draw_mask.rectangle(runway_box, fill=(239, 68, 68, 160), outline=(248, 113, 113, 240), width=3)
    draw_mask.polygon([(240, 140), (330, 140), (330, 200), (240, 200)], fill=(245, 158, 11, 150))
    draw_mask.ellipse([radar_center[0] - 50, radar_center[1] - 50, radar_center[0] + 50, radar_center[1] + 50], fill=(59, 130, 246, 170), outline=(96, 165, 250, 255), width=3)
    draw_mask.rectangle([(70, 330), (160, 410)], fill=(16, 185, 129, 150), outline=(52, 211, 153, 230), width=2)

    # Save compressed WebP images
    t0_img.save(IMAGERY_DIR / "t0.webp", format="WEBP", quality=82)
    t1_img.save(IMAGERY_DIR / "t1.webp", format="WEBP", quality=82)
    mask_img.save(IMAGERY_DIR / "mask.webp", format="WEBP", quality=85)

    # Also save fallback JPEG versions
    t0_img.save(IMAGERY_DIR / "t0.jpg", format="JPEG", quality=82)
    t1_img.save(IMAGERY_DIR / "t1.jpg", format="JPEG", quality=82)

    print(f"Generated synthetic WebP imagery in {IMAGERY_DIR}")


def main() -> None:
    print("=" * 70)
    print(" Project Caelum-EO: Exporting Demo Data for GitHub Pages")
    print("=" * 70)

    ensure_directories()

    # 1. Detections GeoJSON
    detections_geojson = generate_curated_detections()
    geojson_path = DEMO_DATA_DIR / "detections.geojson"
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(detections_geojson, f, indent=2)
    print(f"Exported detections GeoJSON ({len(detections_geojson['features'])} features): {geojson_path}")

    # 2. Analytics JSON
    analytics_data = generate_curated_analytics(detections_geojson)
    analytics_path = DEMO_DATA_DIR / "analytics.json"
    with open(analytics_path, "w", encoding="utf-8") as f:
        json.dump(analytics_data, f, indent=2)
    print(f"Exported analytics JSON: {analytics_path}")

    # 3. Individual convenience endpoints
    with open(DEMO_DATA_DIR / "zones.json", "w", encoding="utf-8") as f:
        json.dump(analytics_data["zones"], f, indent=2)
    with open(DEMO_DATA_DIR / "dark_events.json", "w", encoding="utf-8") as f:
        json.dump(analytics_data["dark_events"], f, indent=2)
    with open(DEMO_DATA_DIR / "network.json", "w", encoding="utf-8") as f:
        json.dump(analytics_data["network"], f, indent=2)
    with open(DEMO_DATA_DIR / "sitreps.json", "w", encoding="utf-8") as f:
        json.dump(analytics_data["sitreps"], f, indent=2)

    # 4. Imagery Chips
    generate_synthetic_image_chips()

    print("Demo data generation complete!")


if __name__ == "__main__":
    main()
