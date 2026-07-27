/** Geolocation helper — wraps navigator.geolocation.getCurrentPosition in a Promise
 * with a small status machine (idle/loading/success/error/unsupported). Used by the
 * Explore "near me" toggle and the Preference Center "use my location" button. */
import { useCallback, useState } from "react";

export type GeoStatus = "idle" | "loading" | "success" | "error" | "unsupported";

export interface Coords {
  lat: number;
  lng: number;
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
          resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        },
        (err) => {
          setStatus("error");
          setError(
            err.code === err.PERMISSION_DENIED
              ? "Bạn đã từ chối quyền truy cập vị trí."
              : "Không lấy được vị trí, thử lại nhé.",
          );
          resolve(null);
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
      );
    });
  }, []);

  return { status, error, request };
}
