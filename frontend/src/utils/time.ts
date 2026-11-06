import { useSyncExternalStore } from "react";

/** Parse an ISO timestamp; strings with no offset are treated as UTC (the API always sends UTC). */
export function parseIso(iso: string): number {
  const hasOffset = /(Z|[+-]\d\d:?\d\d)$/i.test(iso);
  const t = Date.parse(hasOffset ? iso : iso + "Z");
  return Number.isNaN(t) ? Date.parse(iso) : t;
}

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

const UNITS: Array<[string, number]> = [
  ["year", YEAR],
  ["month", MONTH],
  ["week", WEEK],
  ["day", DAY],
  ["hour", HOUR],
  ["minute", MINUTE],
];

/** "1 minute ago", "3 hours ago", "2 days ago", "3 weeks ago", "5 months ago", "1 year ago". */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - parseIso(iso)) / 1000));
  if (seconds < MINUTE) {
    const n = Math.max(1, seconds);
    return `${n} second${n === 1 ? "" : "s"} ago`;
  }
  for (const [name, size] of UNITS) {
    if (seconds >= size) {
      const n = Math.floor(seconds / size);
      return `${n} ${name}${n === 1 ? "" : "s"} ago`;
    }
  }
  return "1 minute ago";
}

/** Absolute local time for tooltips, e.g. "Oct 28, 2026, 2:45 PM". */
export function absoluteTime(iso: string): string {
  return new Date(parseIso(iso)).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// Shared 30 s ticker so every relative label re-renders without each one owning a timer.
const listeners = new Set<() => void>();
let now = Date.now();
let timer: number | null = null;

function subscribe(cb: () => void) {
  listeners.add(cb);
  if (timer === null) {
    timer = window.setInterval(() => {
      now = Date.now();
      listeners.forEach((l) => l());
    }, 30_000);
  }
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0 && timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}

/** Current time, refreshed every 30 seconds while any component uses it. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, () => now, () => now);
}
