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

export interface EditOut {
  id: number;
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

export interface AuthOut {
  token: string;
  user: UserOut;
}

export interface ApiErrorBody {
  code: string;
  message: string;
}
