# Deck.gl React Visualization Specification

**Repository:** `github.com/FranekJemiolo/Caelum-EO`
**Frontend Package:** `@franekjemiolo/caelum-eo-web`

---

## 1. Overview

The presentation layer provides a tactical, high-refresh-rate visualization suite built on top of **React 18**, **Deck.gl 9.0**, and **MapLibre GL**.

---

## 2. Key Components

1. **Deck.gl `GeoJsonLayer`:**
   - Visualizes polygon vectors from PostGIS.
   - 3D extrusion (`extruded: true`, elevation proportional to model confidence).
   - Dynamic classification-based color encoding:
     - Radar Dome: Amber (`#f59e0b`)
     - Logistics Depot: Emerald (`#10b981`)
     - Airfield Runway: Cyan (`#00f2fe`)
     - SAM Battery Site: Crimson (`#f43f5e`)
     - Hardened Shelter: Purple (`#a855f7`)
2. **Temporal Scrubber:**
   - Multi-month continuous time-slider.
   - Interactive play/pause automated playback with adjustable steps.
   - Displays sequential infrastructure build-out across satellite overpasses.
3. **Category Toggles & Confidence Filtering:**
   - Real-time layer filtering without server refetches.
   - Interactive pill controls displaying object counts.
4. **Target Intelligence Dossier:**
   - Side drawer detailing selected structure perimeter, centroid, satellite sensor ID, and tactical assessment notes.
