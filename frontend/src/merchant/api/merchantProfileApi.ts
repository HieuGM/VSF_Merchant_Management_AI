import { apiFetch } from '../../shared/api-client';
import type { MerchantProfileData } from '../types/merchantChat';

export interface DemoTargetMerchant {
  merchant_id: string;
  name: string;
  city: string;
  cuisine: string;
}

interface DemoTargetMerchantResponse {
  merchants: DemoTargetMerchant[];
}

/** Fetch owner merchants explicitly enabled for the demo UI. */
export async function fetchDemoTargetMerchants(): Promise<DemoTargetMerchant[]> {
  const response = await apiFetch<DemoTargetMerchantResponse>('/api/v1/merchants/demo-targets');
  return response.merchants;
}

/**
 * Fetch the full 8-dimension performance profile for a merchant.
 * Used to resolve the active merchant context from the backend.
 */
export async function fetchMerchantProfile(merchantId: string): Promise<MerchantProfileData> {
  return apiFetch<MerchantProfileData>(`/api/v1/merchants/${merchantId}/profile`);
}
