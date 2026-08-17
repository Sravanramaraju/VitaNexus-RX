import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function useTerminologySearch(kind, query, delay = 180) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const term = query.trim();
    if (!term) { setItems([]); setError(""); setLoading(false); return undefined; }
    const timer = setTimeout(() => {
      setLoading(true); setError("");
      api(`/terminology/${kind}?q=${encodeURIComponent(term)}&limit=30`)
        .then((result) => setItems(result.items || []))
        .catch((error) => {
          console.error(`Terminology lookup failed for ${kind}:`, error);
          setItems([]); setError(error.message || "Could not retrieve clinical terminology.");
        })
        .finally(() => setLoading(false));
    }, delay);
    return () => clearTimeout(timer);
  }, [kind, query, delay]);
  return { items, error, loading };
}
