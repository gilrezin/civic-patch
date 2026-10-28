import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const IconHand = (p: P) => (
  <svg {...base} {...p}>
    <path d="M18 11V6a2 2 0 0 0-4 0v5" />
    <path d="M14 10V4a2 2 0 0 0-4 0v6" />
    <path d="M10 10.5V6a2 2 0 0 0-4 0v8" />
    <path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15" />
  </svg>
);

export const IconPolygon = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 3l8.5 6.2-3.2 10H6.7L3.5 9.2z" />
    <circle cx="12" cy="3" r="1.6" fill="currentColor" />
    <circle cx="20.5" cy="9.2" r="1.6" fill="currentColor" />
    <circle cx="3.5" cy="9.2" r="1.6" fill="currentColor" />
  </svg>
);

export const IconEye = (p: P) => (
  <svg {...base} {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export const IconEyeOff = (p: P) => (
  <svg {...base} {...p}>
    <path d="M17.9 17.9A10 10 0 0 1 12 19c-6.5 0-10-7-10-7a17 17 0 0 1 4.1-5.1M9.9 5.2A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.2 3.2" />
    <path d="M14.1 14.1a3 3 0 0 1-4.2-4.2" />
    <path d="M2 2l20 20" />
  </svg>
);

export const IconLocate = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
    <circle cx="12" cy="12" r="8" />
  </svg>
);

export const IconPlus = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const IconMic = (p: P) => (
  <svg {...base} {...p}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
  </svg>
);

export const IconArrowUp = (p: P) => (
  <svg {...base} strokeWidth={2.4} {...p}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);

export const IconArrowDown = (p: P) => (
  <svg {...base} strokeWidth={2.4} {...p}>
    <path d="M12 5v14M19 12l-7 7-7-7" />
  </svg>
);

export const IconArrowRight = (p: P) => (
  <svg {...base} {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);

export const IconEdit = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
  </svg>
);

export const IconClock = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
);

export const IconComment = (p: P) => (
  <svg {...base} {...p}>
    <path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.2-4.2A8 8 0 1 1 21 12z" />
    <path d="M8 12h.01M12 12h.01M16 12h.01" />
  </svg>
);

export const IconShare = (p: P) => (
  <svg {...base} {...p}>
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" />
  </svg>
);

export const IconBookmark = (p: P) => (
  <svg {...base} {...p}>
    <path d="M6 3h12v18l-6-4-6 4z" />
  </svg>
);

export const IconBookmarkFilled = (p: P) => (
  <svg {...base} fill="currentColor" {...p}>
    <path d="M6 3h12v18l-6-4-6 4z" />
  </svg>
);

export const IconTrash = (p: P) => (
  <svg {...base} {...p}>
    <path d="M4 7h16M10 11v6M14 11v6" />
    <path d="M6 7l1 13h10l1-13" />
    <path d="M9 7V4h6v3" />
  </svg>
);

export const IconMapPin = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 22s7-7.1 7-12.5a7 7 0 0 0-14 0C5 14.9 12 22 12 22z" />
    <circle cx="12" cy="9.5" r="2.5" />
  </svg>
);

export const IconMapPinOff = (p: P) => (
  <svg {...base} {...p}>
    <path d="M9.3 4.6A7 7 0 0 1 19 9.5c0 2-1 4.2-2.4 6.2" />
    <path d="M6.2 6.2A7 7 0 0 0 5 9.5C5 14.9 12 22 12 22s1.9-1.9 3.8-4.6" />
    <path d="M10.2 10.2a2.5 2.5 0 0 0 3.6 3.6" />
    <path d="M2 2l20 20" />
  </svg>
);

export const IconLayersOff = (p: P) => (
  <svg {...base} {...p}>
    <path d="M8.6 5.9L12 4l9 5-3.4 1.9" />
    <path d="M5.4 7.7L3 9l9 5 2.6-1.4" />
    <path d="M3 13l9 5 3.9-2.2" />
    <path d="M3 17l9 5 9-5" />
    <path d="M2 2l20 20" />
  </svg>
);

export const IconLayers = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 3l9 5-9 5-9-5 9-5z" />
    <path d="M3 13l9 5 9-5" />
    <path d="M3 17l9 5 9-5" />
  </svg>
);

export const IconClose = (p: P) => (
  <svg {...base} {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);

export const IconCheck = (p: P) => (
  <svg {...base} {...p}>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);
