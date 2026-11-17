import { useCallback, useEffect, useRef, useState } from "react";

/** Calls `fn` every `ms` while the tab is open; pauses when hidden. */
export function usePoll(fn: () => Promise<void> | void, ms: number, deps: unknown[] = []) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      if (!alive) return;
      if (document.visibilityState === "visible") {
        try {
          await saved.current();
        } catch {
          /* keep polling */
        }
      }
      timer = window.setTimeout(tick, ms);
    };
    tick();
    const onVis = () => {
      if (document.visibilityState === "visible") {
        window.clearTimeout(timer);
        tick();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}

/** Re-render every `ms` (for "x minutes ago" labels). */
export function useNow(ms = 30000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return now;
}

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (v: T) => {
      setValue(v);
      try {
        localStorage.setItem(key, JSON.stringify(v));
      } catch {
        /* private mode */
      }
    },
    [key],
  );
  return [value, set];
}

/** Short beep with WebAudio (no audio file needed). */
let audioCtx: AudioContext | null = null;
export function unlockAudio(): boolean {
  try {
    audioCtx = audioCtx ?? new AudioContext();
    if (audioCtx.state === "suspended") audioCtx.resume();
    return true;
  } catch {
    return false;
  }
}

export function beep() {
  if (!audioCtx || audioCtx.state !== "running") return;
  const t = audioCtx.currentTime;
  [0, 0.22].forEach((offset, i) => {
    const osc = audioCtx!.createOscillator();
    const gain = audioCtx!.createGain();
    osc.type = "sine";
    osc.frequency.value = i ? 1046 : 880;
    gain.gain.setValueAtTime(0.0001, t + offset);
    gain.gain.exponentialRampToValueAtTime(0.35, t + offset + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + offset + 0.18);
    osc.connect(gain).connect(audioCtx!.destination);
    osc.start(t + offset);
    osc.stop(t + offset + 0.2);
  });
}

export function audioReady(): boolean {
  return !!audioCtx && audioCtx.state === "running";
}
