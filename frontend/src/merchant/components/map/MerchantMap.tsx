import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MerchantMapFeatureCollection } from '../../types/monitoring';

export function MerchantMap({
  featureCollection,
  selectedMerchantId,
  onMapClick,
}: {
  featureCollection: MerchantMapFeatureCollection;
  selectedMerchantId?: string | null;
  onMapClick?: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!hostRef.current || !featureCollection || featureCollection.features.length === 0) return;
    const firstCoords = featureCollection.features[0].geometry.coordinates;

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

    // Find owner/user location feature
    const userFeature = featureCollection.features.find(
      (f) => String(f.properties.role) === 'owner' || String(f.properties.role) === 'user_location',
    ) || featureCollection.features[0];

    const userCoords = userFeature.geometry.coordinates;

    // Find target selected merchant feature
    let selectedFeature = selectedMerchantId
      ? featureCollection.features.find((f) => String(f.properties.merchant_id) === String(selectedMerchantId))
      : null;

    if (!selectedFeature && featureCollection.features.length > 1) {
      selectedFeature = featureCollection.features.find(
        (f) => String(f.properties.role) !== 'owner' && String(f.properties.role) !== 'user_location',
      ) || null;
    }

    featureCollection.features.forEach((feature, index) => {
      const coords = feature.geometry.coordinates;
      const role = String(feature.properties.role);
      const name = String(feature.properties.name ?? role);
      const isSelected = selectedMerchantId
        ? String(feature.properties.merchant_id) === String(selectedMerchantId)
        : selectedFeature === feature;

      const element = document.createElement('div');
      element.className = `map-pin map-pin--${role} ${isSelected ? 'is-highlighted' : ''}`;
      element.textContent = role === 'owner' || role === 'user_location' ? '●' : String(index);

      const popup = new maplibregl.Popup({ offset: 22, closeButton: false }).setHTML(
        `<div class="map-popup-card"><strong>${name}</strong><br/><small>${role === 'owner' ? 'Vị trí của bạn' : 'Đối thủ / Đề xuất'}</small></div>`,
      );

      const marker = new maplibregl.Marker({ element })
        .setLngLat(coords)
        .setPopup(popup)
        .addTo(map);

      bounds.extend(coords);
      markers.push(marker);
    });

    // Draw route line from user position to target merchant when selected
    map.on('load', () => {
      if (selectedFeature && userCoords && selectedFeature.geometry.coordinates) {
        const targetCoords = selectedFeature.geometry.coordinates;

        map.addSource('route-line-source', {
          type: 'geojson',
          data: {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'LineString',
              coordinates: [userCoords, targetCoords],
            },
          },
        });

        map.addLayer({
          id: 'route-line-layer',
          type: 'line',
          source: 'route-line-source',
          layout: {
            'line-join': 'round',
            'line-cap': 'round',
          },
          paint: {
            'line-color': '#00a398',
            'line-width': 4,
            'line-dasharray': [2, 1],
          },
        });
      }
    });

    if (selectedFeature && userCoords) {
      const focusBounds = new maplibregl.LngLatBounds();
      focusBounds.extend(userCoords);
      focusBounds.extend(selectedFeature.geometry.coordinates);
      map.fitBounds(focusBounds, { padding: 60, maxZoom: 15 });
    } else if (featureCollection.features.length > 1) {
      map.fitBounds(bounds, { padding: 40, maxZoom: 15 });
    } else {
      map.setCenter(firstCoords);
      map.setZoom(14);
    }

    const timer = setTimeout(() => {
      map.resize();
    }, 150);

    mapRef.current = map;

    return () => {
      clearTimeout(timer);
      markers.forEach((marker) => marker.remove());
      map.remove();
      mapRef.current = null;
    };
  }, [featureCollection, selectedMerchantId]);

  return (
    <div
      ref={hostRef}
      className={`merchant-map ${onMapClick ? 'is-clickable' : ''}`}
      onClick={onMapClick}
      aria-label="Bản đồ MapLibre"
    />
  );
}


