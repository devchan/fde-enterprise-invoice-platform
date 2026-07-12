// Injected at build time by Vite; falls back to the local dev backend when unset.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8010";
// Namespaced localStorage key for the cached (non-sensitive) session identity.
export const SESSION_STORAGE_KEY = "fde.invoice.session";
