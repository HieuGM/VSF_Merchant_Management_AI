/** Geolocation helper — wraps navigator.geolocation.getCurrentPosition in a Promise
 * with a small status machine (idle/loading/success/error/unsupported). Used by the
 * Explore "near me" toggle and the Preference Center "use my location" button.
 *
 * `enableHighAccuracy: true` is REQUIRED: desktop browsers otherwise fall back to
 * IP-based geolocation, which can be off by kilometres (e.g. a user in Gia Lâm gets
 * placed near Hoàng Mai → nearby search returns the wrong area). High accuracy uses
 * Wi-Fi triangulation / GPS and is typically ~20–100m on Wi-Fi. The `accuracy` field
 * (metres, 95% confidence) is surfaced so the UI can warn when it's poor. */
import { useCallback, useState } from "react";

export type GeoStatus = "idle" | "loading" | "success" | "error" | "unsupported";

export interface Coords {
  lat: number;
  lng: number;
  /** Position accuracy in metres (95% confidence) from the browser. null if unknown. */
  accuracy: number | null;
}

export function useGeolocation() {
  const [status, setStatus] = useState<GeoStatus>("idle");
  const [error, setError] = useState("");

  const request = useCallback((): Promise<Coords | null> => {
    return new Promise((resolve) => {
      if (typeof navigator === "undefined" || !navigator.geolocation) {
        setStatus("unsupported");
        setError("Trình duyệt không hỗ trợ định vị.");
        resolve(null);
        return;
      }
      setStatus("loading");
      setError("");
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setStatus("success");
          resolve({
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            accuracy: pos.coords.accuracy ?? null,
          });
        },
        (err) => {
          setStatus("error");
          setError(
            err.code === err.PERMISSION_DENIED
              ? "Bạn đã từ chối quyền truy cập vị trí."
              : err.code === err.POSITION_UNAVAILABLE
                ? "Không xác định được vị trí (thử bật GPS/Wi-Fi)."
                : "Không lấy được vị trí, thử lại nhé.",
          );
          resolve(null);
        },
        // enableHighAccuracy=true: prefer GPS/Wi-Fi triangulation over IP (km-level) geolocation.
        // maximumAge=0: never reuse a stale low-accuracy cached reading. 15s timeout for the
        // slower high-accuracy acquisition.
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
      );
    });
  }, []);

  return { status, error, request };
}

