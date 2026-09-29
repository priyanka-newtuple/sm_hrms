import { useEffect, useState } from "react";
import type { ContentItem } from "@/skins/hrms/api/hrCockpit";

export function usePublicContent(path: string) {
  const [data, setData] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/v1/public/content/${path}`, { signal: controller.signal, credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Unable to load published content");
        return response.json();
      })
      .then(setData)
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [path]);
  return { data, loading };
}

export function usePublicQuery<T>({ queryFn }: { queryFn: () => Promise<T[]>; queryKey?: unknown }) {
  const [data, setData] = useState<T[]>([]);
  const [isLoading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    queryFn().then((rows) => { if (active) setData(rows); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [queryFn]);
  return { data, isLoading };
}
