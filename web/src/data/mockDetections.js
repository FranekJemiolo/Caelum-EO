/**
 * Strategic GEOINT Detections Dataset (Suwalki Gap & Strategic Corridor)
 * Spans May 2026 to September 2026 to enable rich temporal scrubbing.
 */
export const INITIAL_GEOINT_DATA = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: "det-001",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [23.148, 54.118],
            [23.156, 54.118],
            [23.156, 54.126],
            [23.148, 54.126],
            [23.148, 54.118]
          ]
        ]
      },
      properties: {
        id: "det-001",
        classification: "Radar_Dome",
        confidence: 0.965,
        detection_date: "2026-05-15T08:30:00Z",
        source_imagery: {
          item_id: "S2A_MSIL2A_20260515_T34UFB",
          platform: "Sentinel-2A",
          cloud_cover: 2.1,
          resolution_m: 10
        },
        tactical_notes: "Reinforced geodesic radar enclosure detected on high ground overlooking frontier transit axis."
      }
    },
    {
      type: "Feature",
      id: "det-002",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [23.180, 54.100],
            [23.210, 54.100],
            [23.210, 54.115],
            [23.180, 54.115],
            [23.180, 54.100]
          ]
        ]
      },
      properties: {
        id: "det-002",
        classification: "Logistics_Depot",
        confidence: 0.912,
        detection_date: "2026-06-02T11:15:00Z",
        source_imagery: {
          item_id: "S2B_MSIL2A_20260602_T34UFB",
          platform: "Sentinel-2B",
          cloud_cover: 4.5,
          resolution_m: 10
        },
        tactical_notes: "Multiple prefabricated warehouse bays with asphalt staging apron adjacent to rail line."
      }
    },
    {
      type: "Feature",
      id: "det-003",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [23.280, 54.195],
            [23.355, 54.200],
            [23.350, 54.215],
            [23.275, 54.210],
            [23.280, 54.195]
          ]
        ]
      },
      properties: {
        id: "det-003",
        classification: "Airfield_Runway",
        confidence: 0.984,
        detection_date: "2026-07-10T14:00:00Z",
        source_imagery: {
          item_id: "S2A_MSIL2A_20260710_T34UFB",
          platform: "Sentinel-2A",
          cloud_cover: 1.2,
          resolution_m: 10
        },
        tactical_notes: "Paved 2,400m tactical airstrip extension with turnaround loops and taxiway connector."
      }
    },
    {
      type: "Feature",
      id: "det-004",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [23.220, 54.130],
            [23.238, 54.130],
            [23.238, 54.144],
            [23.220, 54.144],
            [23.220, 54.130]
          ]
        ]
      },
      properties: {
        id: "det-004",
        classification: "SAM_Battery_Site",
        confidence: 0.941,
        detection_date: "2026-08-22T09:45:00Z",
        source_imagery: {
          item_id: "S2B_MSIL2A_20260822_T34UFB",
          platform: "Sentinel-2B",
          cloud_cover: 0.8,
          resolution_m: 10
        },
        tactical_notes: "Hexagonal earthen revetments with central engagement radar hardstand."
      }
    },
    {
      type: "Feature",
      id: "det-005",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [23.190, 54.118],
            [23.208, 54.118],
            [23.208, 54.129],
            [23.190, 54.129],
            [23.190, 54.118]
          ]
        ]
      },
      properties: {
        id: "det-005",
        classification: "Hardened_Shelter",
        confidence: 0.893,
        detection_date: "2026-09-18T10:20:00Z",
        source_imagery: {
          item_id: "S2A_MSIL2A_20260918_T34UFB",
          platform: "Sentinel-2A",
          cloud_cover: 3.4,
          resolution_m: 10
        },
        tactical_notes: "Bury-and-cover concrete arch shelter for ammunition or command & control elements."
      }
    }
  ]
};
