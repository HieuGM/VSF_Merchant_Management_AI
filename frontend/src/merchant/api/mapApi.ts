import { apiFetch } from '../../shared/api-client';
import type { MerchantMapFeatureCollection } from '../types/monitoring';

export interface MapLocation {
  lat: number;
  lng: number;
}

export interface MapCandidateSelection {
  candidateMerchantIds?: string[];
  recommendedMerchantIds?: string[];
}

export function getMerchantMap(
  merchantId: string,
  location?: MapLocation,
  selection: MapCandidateSelection = {},
): Promise<MerchantMapFeatureCollection> {
  return apiFetch<MerchantMapFeatureCollection>('/api/v1/maps/merchants.geojson', {
    params: {
      merchant_id: merchantId,
      lat: location?.lat,
      lng: location?.lng,
      candidate_merchant_ids: selection.candidateMerchantIds,
      recommended_merchant_ids: selection.recommendedMerchantIds,
    },
  });
}
