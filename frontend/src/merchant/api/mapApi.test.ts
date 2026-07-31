import { afterEach, describe, expect, it, vi } from 'vitest';
import { getMerchantMap } from './mapApi';

describe('getMerchantMap', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('forwards an optional browser location to the GeoJSON endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'FeatureCollection', features: [] }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await getMerchantMap('94', { lat: 16.0544, lng: 108.2022 });

    expect(String(fetchMock.mock.calls[0][0])).toContain('merchant_id=94');
    expect(String(fetchMock.mock.calls[0][0])).toContain('lat=16.0544');
    expect(String(fetchMock.mock.calls[0][0])).toContain('lng=108.2022');
  });

  it('forwards retrieved and recommended merchant IDs as repeated query parameters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'FeatureCollection', features: [] }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await getMerchantMap('94', undefined, {
      candidateMerchantIds: ['m-1', 'm-2'],
      recommendedMerchantIds: ['m-2'],
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('candidate_merchant_ids=m-1');
    expect(url).toContain('candidate_merchant_ids=m-2');
    expect(url).toContain('recommended_merchant_ids=m-2');
  });
});
