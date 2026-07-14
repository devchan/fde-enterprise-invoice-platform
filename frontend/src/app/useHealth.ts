import { useCallback, useEffect, useState } from "react";
import { API_BASE_URL } from "../config";

// Plain fetch, not react-query: this is an unauthenticated infra probe, not tenant data.
export function useHealth() {
  const [health, setHealth] = useState<"unknown" | "ok" | "error">("unknown");

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      setHealth(response.ok ? "ok" : "error");
    } catch {
      setHealth("error");
    }
  }, []);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  return { health, checkHealth };
}
