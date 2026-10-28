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
