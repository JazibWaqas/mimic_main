// ============================================================================
// CENTRALIZED API CLIENT
// ============================================================================
// All backend communication goes through here
// Makes it easy to change endpoints, add error handling, etc.
// ============================================================================

import type { StyleConfig } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const IS_DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

const intelCache = new Map<string, unknown>();

// Helper for fetching demo data
const fetchDemoIndex = async () => {
  const res = await fetch("/demo/index.json");
  if (!res.ok) throw new Error("Demo index not found");
  return res.json();
};

export const getStatus = async (sessionId: string) => {
  if (IS_DEMO) return { status: "success", progress: 100, message: "Demo Mode Active" };
  const res = await fetch(`${API_BASE}/api/status/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
};

export const generateVideo = async (sessionId: string) => {
  if (IS_DEMO) return { success: true, message: "Generative actions disabled in Reference Demo Mode" };
  const res = await fetch(`${API_BASE}/api/generate/${encodeURIComponent(sessionId)}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to start generation");
  return res.json();
};

export const getDownloadUrl = (sessionId: string) => {
  if (IS_DEMO) return "/demo/files/result.mp4";
  return `${API_BASE}/api/download/${encodeURIComponent(sessionId)}`;
};

export const getWebSocketUrl = (sessionId: string) => {
  if (IS_DEMO) return ""; // No WS in demo
  return `ws://localhost:8000/ws/progress/${encodeURIComponent(sessionId)}`;
};

export const getHistory = async () => {
  if (IS_DEMO) {
    const data = await fetchDemoIndex();
    return data.results;
  }
  const res = await fetch(`${API_BASE}/api/history`);
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
};

export const api = {
  identify: async (reference: File) => {
    if (IS_DEMO) return { success: true, message: "Identity scan simulated in Demo Mode" };
    const formData = new FormData();
    formData.append("reference", reference);
    const res = await fetch(`${API_BASE}/api/identify`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Identity scan failed");
    return res.json();
  },
  uploadFiles: async (reference: File | undefined, clips: File[], music?: File) => {
    if (IS_DEMO) return { success: true, session_id: "demo_session" };
    const formData = new FormData();
    if (reference) formData.append("reference", reference);
    if (music) formData.append("music", music);
    clips.forEach((clip) => formData.append("clips", clip));

    const res = await fetch(`${API_BASE}/api/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  },

  startGeneration: async (sessionId: string, textPrompt?: string, targetDuration?: number, styleConfig?: StyleConfig) => {
    if (IS_DEMO) return { success: true, message: "Generation skipped in Demo Mode" };
    let url = `${API_BASE}/api/generate/${sessionId}`;
    const params = new URLSearchParams();
    if (textPrompt) params.append("text_prompt", textPrompt);
    if (targetDuration) params.append("target_duration", targetDuration.toString());

    if (params.toString()) {
      url += `?${params.toString()}`;
    }

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: styleConfig ? JSON.stringify(styleConfig) : undefined
    });

    if (!res.ok) throw new Error("Generation failed");
    return res.json();
  },

  applyStyle: async (filename: string, config: StyleConfig) => {
    if (IS_DEMO) return { success: true };
    const res = await fetch(`${API_BASE}/api/results/${encodeURIComponent(filename)}/style`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error("Style application failed");
    intelCache.delete(`results:${filename}`);
    return res.json();
  },

  connectProgress: (sessionId: string) => {
    if (IS_DEMO) return null;
    return new WebSocket(`ws://localhost:8000/ws/progress/${sessionId}`);
  },

  fetchClips: async () => {
    if (IS_DEMO) {
      const data = await fetchDemoIndex();
      return { clips: data.clips };
    }
    const res = await fetch(`${API_BASE}/api/clips`);
    if (!res.ok) throw new Error("Failed to fetch clips");
    return res.json();
  },

  deleteClip: async (sessionId: string, filename: string) => {
    if (IS_DEMO) return { success: true };
    const res = await fetch(`${API_BASE}/api/clips/${sessionId}/${filename}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete clip");
    return res.json();
  },

  fetchResults: async () => {
    if (IS_DEMO) {
      const data = await fetchDemoIndex();
      return { results: data.results };
    }
    const res = await fetch(`${API_BASE}/api/results`);
    if (!res.ok) throw new Error("Failed to fetch results");
    return res.json();
  },

  deleteResult: async (filename: string) => {
    if (IS_DEMO) return { success: true };
    const res = await fetch(`${API_BASE}/api/results/${filename}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete result");
    return res.json();
  },

  renameFile: async (type: string, oldFilename: string, newFilename: string) => {
    if (IS_DEMO) return { success: true };
    const res = await fetch(`${API_BASE}/api/rename?type=${type}&old_filename=${encodeURIComponent(oldFilename)}&new_filename=${encodeURIComponent(newFilename)}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to rename file");
    return res.json();
  },

  fetchReferences: async () => {
    if (IS_DEMO) {
      const data = await fetchDemoIndex();
      return { references: data.references };
    }
    const res = await fetch(`${API_BASE}/api/references`);
    if (!res.ok) throw new Error("Failed to fetch references");
    return res.json();
  },

  fetchIntelligence: async (type: string, key: string) => {
    if (IS_DEMO) {
      // In demo mode, all intelligence maps to our one golden result or reference
      const path = type === "results" ? "/demo/files/result.json" : "/demo/files/result.json"; // We wrap everything in one for now
      const res = await fetch(path);
      if (!res.ok) throw new Error("Demo intelligence not found");
      return res.json();
    }
    const cacheKey = `${type}:${key}`;
    if (type !== "results" && intelCache.has(cacheKey)) return intelCache.get(cacheKey);

    const res = await fetch(`${API_BASE}/api/intelligence?type=${type}&filename=${encodeURIComponent(key)}`);
    if (!res.ok) throw new Error("Intelligence data not found");
    const data: unknown = await res.json();
    if (type !== "results") intelCache.set(cacheKey, data);
    return data;
  },
};
