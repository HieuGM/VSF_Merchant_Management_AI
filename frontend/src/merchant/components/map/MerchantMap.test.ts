import { afterEach, describe, expect, it, vi } from 'vitest';
import * as merchantMapModule from './MerchantMap';

describe('OSRM routing', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns the road distance reported by OSRM', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        routes: [{
          distance: 2475,
          geometry: { type: 'LineString', coordinates: [[106.7, 10.7], [106.71, 10.71]] },
        }],
      }),
    }));

    const fetchOsrmRoute = (merchantMapModule as Record<string, unknown>).fetchOsrmRoute;
    expect(fetchOsrmRoute).toBeTypeOf('function');
    if (typeof fetchOsrmRoute !== 'function') return;

    await expect(fetchOsrmRoute([106.7, 10.7], [106.71, 10.71])).resolves.toMatchObject({
      distanceKm: 2.475,
    });
  });
});
