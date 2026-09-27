import React, { useState, useEffect, useMemo } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import Map from 'react-map-gl/maplibre';

// Suwalki Gap Surveillance Corridor Viewport
const INITIAL_VIEW_STATE = {
  longitude: 23.23,
  latitude: 54.14,
  zoom: 11.5,
  pitch: 45,
  bearing: -15
};

const DARK_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

// Classification tactical color map [R, G, B]
export const CLASSIFICATION_COLORS = {
  Radar_Dome: [245, 158, 11],          // Amber
  Logistics_Depot: [16, 185, 129],       // Emerald
  Airfield_Runway: [0, 242, 254],       // Cyan
  SAM_Battery_Site: [244, 63, 94],      // Crimson
  Hardened_Shelter: [168, 85, 247],     // Purple
  Naval_Pier_Berth: [79, 172, 254],     // Blue
  Fuel_Storage_Tank: [234, 179, 8],     // Yellow
  Unknown_Structure: [148, 163, 184]    // Slate
};

// Fallback Mock REST Data
const MOCK_FALLBACK_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: "mock-1",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.148, 54.118], [23.156, 54.118], [23.156, 54.126], [23.148, 54.126], [23.148, 54.118]]]
      },
      properties: {
        id: "mock-1",
        classification: "Radar_Dome",
        confidence: 0.965,
        detection_date: "2026-05-15T08:30:00Z"
      }
    },
    {
      type: "Feature",
      id: "mock-2",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.180, 54.100], [23.210, 54.100], [23.210, 54.115], [23.180, 54.115], [23.180, 54.100]]]
      },
      properties: {
        id: "mock-2",
        classification: "Logistics_Depot",
        confidence: 0.912,
        detection_date: "2026-06-02T11:15:00Z"
      }
    },
    {
      type: "Feature",
      id: "mock-3",
      geometry: {
        type: "Polygon",
        coordinates: [[[23.280, 54.195], [23.355, 54.200], [23.350, 54.215], [23.275, 54.210], [23.280, 54.195]]]
      },
      properties: {
        id: "mock-3",
        classification: "Airfield_Runway",
        confidence: 0.984,
        detection_date: "2026-07-10T14:00:00Z"
      }
    }
  ]
};

export default function MapComponent({ apiUrl = "http://localhost:8000/api/detections" }) {
  const [geoData, setGeoData] = useState(MOCK_FALLBACK_GEOJSON);

  useEffect(() => {
    fetch(apiUrl)
      .then(res => res.json())
      .then(data => {
        if (data && data.features && data.features.length > 0) {
          setGeoData(data);
        }
      })
      .catch(() => {
        // Retain mock fallback
      });
  }, [apiUrl]);

  const layers = useMemo(() => {
    return [
      new GeoJsonLayer({
        id: 'infrastructure-detections-layer',
        data: geoData,
        pickable: true,
        stroked: true,
        filled: true,
        extruded: true,
        wireframe: true,
        lineWidthMinPixels: 2,
        getFillColor: d => {
          const cls = d.properties?.classification;
          const rgb = CLASSIFICATION_COLORS[cls] || [148, 163, 184];
          return [...rgb, 190];
        },
        getLineColor: [255, 255, 255, 240],
        getElevation: d => (d.properties?.confidence || 0.5) * 80,
        autoHighlight: true,
        highlightColor: [0, 242, 254, 220]
      })
    ];
  }, [geoData]);

  return (
    <div className="map-container">
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller={true}
        layers={layers}
        getTooltip={({ object }) => {
          if (!object) return null;
          const p = object.properties || {};
          return {
            html: `
              <div style="font-family: sans-serif; font-size: 12px; background: rgba(10,13,20,0.9); padding: 8px; border: 1px solid #00f2fe; border-radius: 6px; color: #fff;">
                <b style="color: #00f2fe;">${p.classification?.replace(/_/g, ' ')}</b><br/>
                Confidence: ${(p.confidence * 100).toFixed(1)}%<br/>
                Date: ${new Date(p.detection_date).toLocaleDateString()}
              </div>
            `
          };
        }}
      >
        <Map mapStyle={DARK_MAP_STYLE} />
      </DeckGL>

      <div className="hud-panel">
        <div className="hud-title">CAELUM-EO | GEOINT</div>
        <div className="legend-list">
          {Object.entries(CLASSIFICATION_COLORS).map(([name, rgb]) => (
            <div key={name} className="legend-item">
              <span
                className="legend-color"
                style={{ backgroundColor: `rgb(${rgb.join(',')})` }}
              />
              <span>{name.replace(/_/g, ' ')}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
