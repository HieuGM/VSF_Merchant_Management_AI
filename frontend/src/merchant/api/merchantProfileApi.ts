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

export interface MerchantReviewItem {
  review_id: string;
  rating: number;
  text: string;
  sentiment: 'positive' | 'negative' | 'neutral';
  total_like: number;
  source_kind: string;
  created_at: string | null;
}

export async function fetchMerchantReviews(merchantId: string): Promise<{ merchant_id: string; count: number; reviews: MerchantReviewItem[] }> {
  return apiFetch<{ merchant_id: string; count: number; reviews: MerchantReviewItem[] }>(`/api/v1/merchants/${merchantId}/reviews`);
}

export interface MenuItemData {
  item_id: string;
  name: string;
  price: number;
  discount_price?: number | null;
  description?: string | null;
  category: string;
  image_url?: string | null;
  total_like: number;
  is_available: boolean;
}

export async function fetchMerchantMenu(merchantId: string): Promise<{ merchant_id: string; count: number; menu_items: MenuItemData[] }> {
  return apiFetch<{ merchant_id: string; count: number; menu_items: MenuItemData[] }>(`/api/v1/merchants/${merchantId}/menu`);
}

export interface PolicyDocumentItem {
  document_id: string;
  title: string;
  category: string;
  source_url: string;
  document_text: string;
  policy_updated_at: string | null;
}

export async function fetchProcessedPolicies(): Promise<{ count: number; documents: PolicyDocumentItem[] }> {
  return apiFetch<{ count: number; documents: PolicyDocumentItem[] }>('/api/v1/merchants/policies/processed');
}
