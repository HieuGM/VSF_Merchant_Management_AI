import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MerchantMapFeatureCollection } from '../../types/monitoring';

interface FetchOsrmRouteOptions {
  osrmEndpoint?: string;
}

async function fetchOsrmRoute(
  start: [number, number],
  end: [number, number],
  options?: FetchOsrmRouteOptions,
): Promise<{ geometry: any }> {
  const baseUrl = (options?.osrmEndpoint || 'https://router.project-osrm.org').replace(/\/$/, '');
  const url = `${baseUrl}/route/v1/driving/${start[0]},${start[1]};${end[0]},${end[1]}?overview=full&geometries=geojson`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`OSRM HTTP error status ${response.status}`);
    }
    const data = await response.json();
    if (data.routes && data.routes.length > 0 && data.routes[0]?.geometry) {
      return { geometry: data.routes[0].geometry };
    }
  } catch (error) {
    console.warn('OSRM routing request failed, falling back to direct line:', error);
  }

  // Fallback to straight line if OSRM call fails or returns empty
  return {
    geometry: {
      type: 'LineString',
      coordinates: [start, end],
    },
  };
}

export function MerchantMap({
  featureCollection,
  selectedMerchantId,
  onMapClick,
  osrmEndpoint,
}: {
  featureCollection: MerchantMapFeatureCollection;
  selectedMerchantId?: string | null;
  onMapClick?: () => void;
  osrmEndpoint?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [activeSelectedId, setActiveSelectedId] = useState<string | null>(selectedMerchantId ?? null);

  useEffect(() => {
    if (selectedMerchantId !== undefined) {
      setActiveSelectedId(selectedMerchantId);
    }
  }, [selectedMerchantId]);

  useEffect(() => {
    let isCancelled = false;
    if (!hostRef.current || !featureCollection || featureCollection.features.length === 0) return;

    // Filter features: owner/user location plus same-type merchants (or explicit candidates/recommended)
    const ownerFeature = featureCollection.features.find(
      (f) => String(f.properties.role) === 'owner' || String(f.properties.role) === 'user_location',
    ) || featureCollection.features[0];

    const ownerType = String(
      ownerFeature.properties.cuisine_type ??
      ownerFeature.properties.category ??
      ownerFeature.properties.type ??
      ownerFeature.properties.merchant_type ??
      '',
    ).trim().toLowerCase();

    const displayFeatures = featureCollection.features.filter((f) => {
      const role = String(f.properties.role);
      if (role === 'owner' || role === 'user_location' || role === 'recommended') return true;

      const fType = String(
        f.properties.cuisine_type ??
        f.properties.category ??
        f.properties.type ??
        f.properties.merchant_type ??
        '',
      ).trim().toLowerCase();

      if (ownerType && fType) {
        return fType === ownerType || fType.includes(ownerType) || ownerType.includes(fType);
      }
      return true;
    });

    const firstCoords = displayFeatures[0].geometry.coordinates;

    const map = new maplibregl.Map({
      container: hostRef.current,
      style: {
        version: 8,
        sources: {
          'osm-tiles': {
            type: 'raster',
            tiles: [
              'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
              'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
              'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
            ],
            tileSize: 256,
            attribution: '© OpenStreetMap',
          },
        },
        layers: [
          {
            id: 'osm-tiles-layer',
            type: 'raster',
            source: 'osm-tiles',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: firstCoords,
      zoom: 13,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    const bounds = new maplibregl.LngLatBounds();
    const markers: maplibregl.Marker[] = [];

    const userCoords = ownerFeature.geometry.coordinates;

    displayFeatures.forEach((feature, index) => {
      const coords = feature.geometry.coordinates;
      const role = String(feature.properties.role);
      const name = String(feature.properties.name ?? role);
      const featureMerchantId = String(feature.properties.merchant_id ?? '');
      const isOwner = role === 'owner' || role === 'user_location';
      const isSelected = activeSelectedId ? featureMerchantId === String(activeSelectedId) : false;

      const element = document.createElement('div');
      element.className = `map-pin map-pin--${role} ${isSelected ? 'is-highlighted' : ''}`;

      if (isOwner) {
        // Person icon for current position / owner merchant (clearly bigger)
        element.innerHTML = `
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-label="Vị trí hiện tại">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        `;
      } else {
        element.textContent = String(index);
      }

      const popup = new maplibregl.Popup({ offset: 22, closeButton: false }).setHTML(
        `<div class="map-popup-card"><strong>${name}</strong><br/><small>${isOwner ? 'Vị trí của bạn (Owner)' : 'Merchant cùng loại / Đề xuất'}</small></div>`,
      );

      const marker = new maplibregl.Marker({ element })
        .setLngLat(coords)
        .setPopup(popup)
        .addTo(map);

      // On marker click: toggle selection to draw OSRM route path line
      if (!isOwner && featureMerchantId) {
        element.addEventListener('click', (ev) => {
          ev.stopPropagation();
          setActiveSelectedId((prev: string | null) => (prev === featureMerchantId ? null : featureMerchantId));
        });
      }

      bounds.extend(coords);
      markers.push(marker);
    });

    // Handle map background click
    map.on('click', () => {
      setActiveSelectedId(null);
      if (onMapClick) onMapClick();
    });

    // Draw OSRM route line from user position to selected target merchant
    const updateRouteLine = async () => {
      let selectedFeature = activeSelectedId
        ? displayFeatures.find((f) => String(f.properties.merchant_id) === String(activeSelectedId))
        : null;

      // In a 2-feature detail map (Owner + 1 Target Merchant), select the target merchant automatically
      if (!selectedFeature && displayFeatures.length === 2) {
        selectedFeature = displayFeatures.find(
          (f) => String(f.properties.role) !== 'owner' && String(f.properties.role) !== 'user_location',
        ) || null;
      }

      const sourceId = 'route-line-source';
      const layerId = 'route-line-layer';

      if (!selectedFeature || !userCoords || !selectedFeature.geometry.coordinates) {
        // Clear route line if no merchant is selected by click
        if (map.getLayer(layerId)) map.removeLayer(layerId);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
        return;
      }

      const startPt = userCoords as [number, number];
      const endPt = selectedFeature.geometry.coordinates as [number, number];

      const { geometry } = await fetchOsrmRoute(startPt, endPt, { osrmEndpoint });
      if (isCancelled || !mapRef.current) return;

      if (map.getSource(sourceId)) {
        (map.getSource(sourceId) as maplibregl.GeoJSONSource).setData({
          type: 'Feature',
          properties: {},
          geometry,
        });
      } else {
        map.addSource(sourceId, {
          type: 'geojson',
          data: {
            type: 'Feature',
            properties: {},
            geometry,
          },
        });

        // Hard blue color (#1d4ed8) and thicker line (width: 7)
        map.addLayer({
          id: layerId,
          type: 'line',
          source: sourceId,
          layout: {
            'line-join': 'round',
            'line-cap': 'round',
          },
          paint: {
            'line-color': '#1d4ed8',
            'line-width': 7,
            'line-opacity': 1.0,
          },
        });
      }

      if (geometry && Array.isArray(geometry.coordinates) && geometry.coordinates.length > 2) {
        const routeBounds = new maplibregl.LngLatBounds();
        geometry.coordinates.forEach((pt: [number, number]) => routeBounds.extend(pt));
        map.fitBounds(routeBounds, { padding: 65, maxZoom: 15 });
      }
    };

    map.on('load', () => {
      void updateRouteLine();
    });

    if (map.isStyleLoaded()) {
      void updateRouteLine();
    }

    if (displayFeatures.length > 1) {
      map.fitBounds(bounds, { padding: 45, maxZoom: 15 });
    } else {
      map.setCenter(firstCoords);
      map.setZoom(14);
    }

    const timer = setTimeout(() => {
      map.resize();
    }, 150);

    mapRef.current = map;

    return () => {
      isCancelled = true;
      clearTimeout(timer);
      markers.forEach((marker) => marker.remove());
      map.remove();
      mapRef.current = null;
    };
  }, [featureCollection, activeSelectedId, osrmEndpoint, onMapClick]);

  return (
    <div
      ref={hostRef}
      className={`merchant-map ${onMapClick ? 'is-clickable' : ''}`}
      aria-label="Bản đồ MapLibre"
    />
  );
}


