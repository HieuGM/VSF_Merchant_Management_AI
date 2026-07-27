/**
 * Smart "stick to bottom" scroll controller for streaming chat.
 *
 * Why this exists: the old code did `scrollTo({ behavior: "smooth" })` on every
 * `messages` change. During SSE streaming each frame mutates messages, so dozens of
 * smooth-scroll animations queued and fought → jank and "stuck" objects. Here we only
 * re-pin (INSTANT, never smooth) when the user is already near the bottom, via rAF + a
 * ResizeObserver/MutationObserver pair. If the user scrolled up, we leave them alone and
 * surface `atBottom=false` so the page can show a "jump to latest" pill.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const THRESHOLD_PX = 96;

export function useStickToBottom<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const atBottomRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const rafRef = useRef<number | null>(null);

  const recompute = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const near = distance < THRESHOLD_PX;
    atBottomRef.current = near;
    setAtBottom(near);
  }, []);

  const pinIfStuck = useCallback(() => {
    if (!atBottomRef.current) return;
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      const el = ref.current;
      if (el) el.scrollTop = el.scrollHeight; // instant — no competing animations
      rafRef.current = null;
    });
  }, []);

  // Pin on content growth (streaming text / new messages) and on container resize.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(pinIfStuck);
    ro.observe(el);
    Array.from(el.children).forEach((child) => ro.observe(child));
    const mo = new MutationObserver(() => {
      // Observe newly added children too.
      Array.from(el.children).forEach((child) => ro.observe(child));
      pinIfStuck();
    });
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    return () => {
      ro.disconnect();
      mo.disconnect();
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [pinIfStuck]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
    atBottomRef.current = true;
    setAtBottom(true);
  }, []);

  return { ref, atBottom, onScroll: recompute, scrollToBottom };
}
