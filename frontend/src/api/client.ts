import type { Polygon } from "geojson";
import type { ApiErrorBody, AuthOut, CommentOut, EditOut, UserOut, VersionOut, VoteOut } from "./types";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.code = body.code;
    this.status = status;
  }
}

let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
}

const GENERATION_TIMEOUT_MS = 150_000;
const DEFAULT_TIMEOUT_MS = 20_000;

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: { timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    if ((err as Error).name === "AbortError") {
      throw new ApiError(504, { code: "timeout", message: "The request took too long. Please try again." });
    }
    throw new ApiError(0, { code: "network", message: "Could not reach the server." });
  }
  clearTimeout(timer);
  if (!res.ok) {
    let parsed: ApiErrorBody = { code: "error", message: `Request failed (${res.status})` };
    try {
      const data = await res.json();
      if (data?.detail && typeof data.detail === "object" && data.detail.code) parsed = data.detail;
      else if (typeof data?.detail === "string") parsed = { code: "error", message: data.detail };
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, parsed);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  signup: (email: string, password: string, display_name: string) =>
    request<AuthOut>("POST", "/auth/signup", { email, password, display_name }),
  login: (email: string, password: string) => request<AuthOut>("POST", "/auth/login", { email, password }),
  me: () => request<UserOut>("GET", "/auth/me"),

  listEdits: () => request<EditOut[]>("GET", "/edits"),
  getEdit: (id: number) => request<EditOut>("GET", `/edits/${id}`),
  createEdit: (polygon: Polygon, prompt: string) =>
    request<EditOut>("POST", "/edits", { polygon, prompt }, { timeoutMs: GENERATION_TIMEOUT_MS }),
  refineEdit: (id: number, prompt: string) =>
    request<EditOut>("POST", `/edits/${id}/refine`, { prompt }, { timeoutMs: GENERATION_TIMEOUT_MS }),
  listVersions: (id: number) => request<VersionOut[]>("GET", `/edits/${id}/versions`),

  vote: (id: number, value: -1 | 0 | 1) => request<VoteOut>("PUT", `/edits/${id}/vote`, { value }),
  listComments: (id: number) => request<CommentOut[]>("GET", `/edits/${id}/comments`),
  addComment: (id: number, body: string) => request<CommentOut>("POST", `/edits/${id}/comments`, { body }),
};
