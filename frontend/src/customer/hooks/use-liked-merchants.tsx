/**
 * LikedMerchantsProvider — episodic memory: the shared set of merchants the user has liked
 * (heart on restaurant cards). Loads ONCE for the whole customer app from GET /liked-merchants;
 * `toggle` optimistically updates + syncs (POST/DELETE) with rollback on failure. Wraps
 * CustomerHome so every RestaurantCard (Explore + chat) shares one heart-state + one load.
 * Persists across sessions (durable backend store) — a like survives a reload/comeback.
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getLikedMerchants, likeMerchant, unlikeMerchant } from "../api/customer-agent-client";
import { getCustomerUserId } from "./use-customer-identity";

type LikedCtx = {
  likedIds: Set<string>;
  isLiked: (merchantId: string) => boolean;
  toggle: (merchantId: string) => Promise<void>;
  loaded: boolean;
};

const Ctx = createContext<LikedCtx>({
  likedIds: new Set(),
  isLiked: () => false,
  toggle: async () => {},
  loaded: false,
});

export function LikedMerchantsProvider({ children }: { children: ReactNode }) {
  const [likedIds, setLikedIds] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState(false);

  // Load once on mount. Non-reactive userId (stable for the session, see use-customer-identity).
  useEffect(() => {
    const uid = getCustomerUserId();
    if (!uid) return;
    let cancelled = false;
    getLikedMerchants(uid).then((ms) => {
      if (cancelled) return;
      setLikedIds(new Set(ms.map((m) => m.merchant_id)));
      setLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const isLiked = useCallback((merchantId: string) => likedIds.has(merchantId), [likedIds]);

  const toggle = useCallback(
    async (merchantId: string) => {
      const uid = getCustomerUserId();
      if (!uid) return;
      const willLike = !likedIds.has(merchantId);
      // Optimistic: update immediately so the heart feels instant.
      setLikedIds((prev) => {
        const next = new Set(prev);
        if (willLike) next.add(merchantId);
        else next.delete(merchantId);
        return next;
      });
      try {
        if (willLike) await likeMerchant(uid, merchantId);
        else await unlikeMerchant(uid, merchantId);
      } catch {
        // Rollback on failure (backend down / 404 merchant) so the UI never lies.
        setLikedIds((prev) => {
          const next = new Set(prev);
          if (willLike) next.delete(merchantId);
          else next.add(merchantId);
          return next;
        });
      }
    },
    [likedIds],
  );

  return <Ctx.Provider value={{ likedIds, isLiked, toggle, loaded }}>{children}</Ctx.Provider>;
}

/** Consume the liked-merchant state (heart on a card). Must be used inside CustomerHome. */
export function useLikedMerchants() {
  return useContext(Ctx);
}
