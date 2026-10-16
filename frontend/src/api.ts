// Thin typed client for the FastAPI backend.

export type VideoStatus = "uploaded" | "processing" | "done" | "failed";
export type Platform = "tiktok" | "instagram" | "youtube" | "";

export interface User {
  id: number;
  email: string;
  auto_add: boolean;
  has_share_key: boolean;
  share_key_hint: string;
}

export interface Video {
  id: number;
  kind: "file" | "link";
  source_url: string;
  platform: Platform;
  author: string;
  thumbnail_url: string;
  original_filename: string;
  caption: string;
  status: VideoStatus;
  transcript: string;
  error: string;
  created_at: string;
  recipe_id: number | null;
}

export interface Ingredient {
  id?: number;
  name: string;
  quantity: number | string | null;
  quantity_display?: string;
  unit: string;
  raw_text?: string;
}

export interface RecipeSummary {
  id: number;
  title: string;
  reviewed: boolean;
  estimated: boolean;
  source_url: string;
  platform: Platform;
  author: string;
  thumbnail_url: string;
  created_at: string;
  ingredient_count: number;
  in_default_list: boolean;
  /** True when the AI saw and/or heard the video itself, not just its caption. */
  watched: boolean;
  video_id: number | null;
}

export interface Recipe extends RecipeSummary {
  servings: number | null;
  steps: string[];
  ingredients: Ingredient[];
}

export interface RecipeInput {
  title: string;
  servings: number | null;
  steps: string[];
  ingredients: Ingredient[];
}

export interface GroceryItem {
  id: number;
  name: string;
  quantity: number | null;
  quantity_display: string;
  unit: string;
  aisle: string;
  checked: boolean;
  have_already: boolean;
  custom: boolean;
}

export interface GroceryList {
  id: number;
  name: string;
  is_default: boolean;
  created_at: string;
  recipes: RecipeSummary[];
  items: GroceryItem[];
}

const TOKEN_KEY = "rg_token";

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = token.get();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (res.status === 401 && t) {
    token.clear();
    window.location.assign("/welcome");
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : formatValidation(body.detail);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

// FastAPI 422s are a list of {loc, msg}; show the first one readably.
function formatValidation(detail: unknown): string {
  if (Array.isArray(detail) && detail[0]?.msg) {
    const d = detail[0];
    const field = Array.isArray(d.loc) ? d.loc.filter((x: unknown) => x !== "body").join(" → ") : "";
    return field ? `${field}: ${d.msg}` : d.msg;
  }
  return "Something went wrong";
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", { method: "POST", body: json({ email, password }) }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", body: json({ email, password }) }),
  me: () => request<User>("/auth/me"),
  config: () => request<{ shortcut_url: string }>("/config"),
  updateMe: (patch: Partial<Pick<User, "auto_add">>) => request<User>("/auth/me", { method: "PATCH", body: json(patch) }),
  createShareKey: () => request<{ key: string; hint: string }>("/auth/share-key", { method: "POST" }),
  revokeShareKey: () => request<void>("/auth/share-key", { method: "DELETE" }),

  shareLink: (url: string, caption = "") =>
    request<Video>("/videos/link", { method: "POST", body: json({ url, caption }) }),
  uploadVideo: (file: File, caption = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("caption", caption);
    return request<Video>("/videos", { method: "POST", body: form });
  },
  videos: () => request<Video[]>("/videos?limit=50"),
  video: (id: number) => request<Video>(`/videos/${id}`),
  retryVideo: (id: number, caption: string) => {
    const form = new FormData();
    form.append("caption", caption);
    return request<Video>(`/videos/${id}/retry`, { method: "POST", body: form });
  },
  /** Read a saved video again (e.g. after the AI key was added), keeping its caption. */
  rereadVideo: (id: number) => request<Video>(`/videos/${id}/retry`, { method: "POST", body: new FormData() }),
  /** Give a shared link its video file (saved from TikTok) so the AI can watch it. */
  attachVideo: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Video>(`/videos/${id}/file`, { method: "POST", body: form });
  },
  deleteVideo: (id: number) => request<void>(`/videos/${id}`, { method: "DELETE" }),

  recipes: () => request<RecipeSummary[]>("/recipes?limit=200"),
  recipe: (id: number) => request<Recipe>(`/recipes/${id}`),
  saveRecipe: (id: number, body: RecipeInput) => request<Recipe>(`/recipes/${id}`, { method: "PUT", body: json(body) }),
  createRecipe: (body: RecipeInput) => request<Recipe>("/recipes", { method: "POST", body: json(body) }),
  deleteRecipe: (id: number) => request<void>(`/recipes/${id}`, { method: "DELETE" }),

  defaultList: () => request<GroceryList>("/lists/default"),
  addRecipeToList: (listId: number, recipeId: number) =>
    request<GroceryList>(`/lists/${listId}/recipes`, { method: "POST", body: json({ recipe_id: recipeId }) }),
  removeRecipeFromList: (listId: number, recipeId: number) =>
    request<GroceryList>(`/lists/${listId}/recipes/${recipeId}`, { method: "DELETE" }),
  updateItem: (listId: number, itemId: number, patch: Partial<Pick<GroceryItem, "checked" | "have_already">>) =>
    request<GroceryItem>(`/lists/${listId}/items/${itemId}`, { method: "PATCH", body: json(patch) }),
  addItem: (listId: number, name: string) =>
    request<GroceryItem>(`/lists/${listId}/items`, { method: "POST", body: json({ name }) }),
  deleteItem: (listId: number, itemId: number) => request<void>(`/lists/${listId}/items/${itemId}`, { method: "DELETE" }),
  resetList: (listId: number) => request<GroceryList>(`/lists/${listId}/reset`, { method: "POST" }),
  clearList: (listId: number) => request<GroceryList>(`/lists/${listId}/clear`, { method: "POST" }),
};
