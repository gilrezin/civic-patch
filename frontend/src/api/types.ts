import type { Polygon } from "geojson";

export type Bounds = [number, number, number, number]; // W, S, E, N

export interface UserOut {
  id: number;
  display_name: string;
}

export interface VersionOut {
  id: number;
  version_number: number;
  prompt: string;
  parent_version_id: number | null;
  overlay_url: string | null;
  full_url: string | null;
  status: "pending" | "done" | "failed";
  error?: string | null;
  created_by: UserOut;
  created_at: string;
}

export interface StrokeOut {
  coordinates: [number, number][];
  width_m: number;
}

export interface HighlightOut {
  strokes: StrokeOut[];
}

export interface SmartOut {
  polygons: [number, number][][];
  strokes: StrokeOut[];
}

/** Map features for smart select, one cell at a time. */
export interface OsmArea {
  key: string;
  kind: "building" | "parking" | "green";
  label: string;
  ring: [number, number][];
}

export interface OsmRoad {
  key: string;
  kind: "road" | "path";
  label: string;
  coords: [number, number][];
  width_m: number;
}

export interface OsmCell {
  cell: [number, number];
  bbox: [number, number, number, number];
  areas: OsmArea[];
  roads: OsmRoad[];
}

export interface MaskOut {
  /** Each polygon is [outer ring, hole, hole, ...] in lng/lat. */
  polygons: [number, number][][][];
}

export interface MaskIn {
  zoom: number;
  x0: number;
  y0: number;
  width: number;
  height: number;
  png: string;
}

export interface EditOut {
  id: number;
  kind: "polygon" | "highlight" | "smart" | "mask";
  highlight: HighlightOut | null;
  smart: SmartOut | null;
  mask: MaskOut | null;
  /** The drawn polygon, or for highlights the bounding box of the strokes. */
  polygon: Polygon;
  bounds: Bounds;
  status: "pending" | "done" | "failed";
  error?: string | null;
  created_by: UserOut;
  created_at: string;
  updated_at: string;
  current_version: VersionOut | null;
  original_prompt: string;
  version_count: number;
  score: number;
  up: number;
  down: number;
  my_vote: -1 | 0 | 1;
  comment_count: number;
  original_url: string;
  place_name: string | null;
  saved: boolean;
}

/** A Gemini-edited Street View panorama rendered for one version of an edit. */
export interface StreetViewOut {
  id: number;
  edit_id: number;
  version_id: number;
  version_number: number;
  pano_id: string;
  lat: number;
  lng: number;
  /** Compass bearing at the centre column of the panorama (toward the site). */
  heading: number;
  distance_m: number;
  pano_date: string | null;
  original_url: string;
  edited_url: string;
  status: "pending" | "done" | "failed";
  created_at: string;
}

export interface ContributionOut {
  version_id: number;
  edit_id: number;
  kind: "edit" | "refinement";
  prompt: string;
  version_number: number;
  created_at: string;
  place_name: string | null;
  centroid: [number, number];
  edit_original_prompt: string;
  edit_creator: UserOut;
  edit_status: string;
  score: number;
}

export interface CommentOut {
  id: number;
  edit_id: number;
  body: string;
  author: UserOut;
  created_at: string;
}

export interface VoteOut {
  score: number;
  up: number;
  down: number;
  my_vote: -1 | 0 | 1;
}

export interface HintsPrepareOut {
  municipality: string | null;
  place_name: string | null;
  status: "ready" | "generating" | "available" | "failed" | "none";
  source: "plan" | "default";
  error?: string | null;
}

export interface PlanRef {
  exists: boolean;
  municipality: string | null;
  filename: string | null;
  url: string | null;
  hints_status: string | null;
}

export interface PlaceHere {
  city: string | null;
  neighbourhood: string | null;
  region: string | null;
  place_name: string | null;
  municipality: string | null;
  plan: PlanRef;
}

export interface SearchHit {
  name: string;
  lng: number;
  lat: number;
  bbox: [number, number, number, number];
}

export interface AuthOut {
  token: string;
  user: UserOut;
}

export interface ApiErrorBody {
  code: string;
  message: string;
}
