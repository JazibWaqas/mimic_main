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
const INTEL_CACHE_LIMIT = 40;

const getCachedIntel = (key: string) => {
  if (!intelCache.has(key)) return undefined;
  const value = intelCache.get(key);
  intelCache.delete(key);
  intelCache.set(key, value);
  return value;
};

const setCachedIntel = (key: string, value: unknown) => {
  intelCache.set(key, value);
  while (intelCache.size > INTEL_CACHE_LIMIT) {
    const oldestKey = intelCache.keys().next().value;
    if (!oldestKey) break;
    intelCache.delete(oldestKey);
  }
};

type RenderEdlDecision = {
  segment_id: number;
  clip_path: string;
  clip_start: number;
  clip_end: number;
  timeline_start: number;
  timeline_end: number;
  hold_end_seconds?: number | null;
  reasoning?: string;
  vibe_match?: boolean;
};

export type CreativeBrief = {
  status?: "needs_clarification" | "ready_for_approval";
  summary: string;
  assumptions?: string[];
  resolved_choices?: string[];
  intake?: Record<string, string>;
  intake_confidence?: Record<string, "confirmed" | "assumed" | "missing">;
  vibe: string[];
  pacing: string;
  clip_preferences: string[];
  avoid: string[];
  text_style: string;
  music_direction: string;
  question?: string;
  questions?: Array<{
    id: string;
    field?: string;
    question: string;
    options?: string[];
    impact?: string;
  }>;
  clarification_answers?: Record<string, string>;
  production_prompt: string;
};

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

  understandBrief: async (message: string, currentBrief?: CreativeBrief | null): Promise<CreativeBrief> => {
    if (IS_DEMO) {
      return {
        status: "ready_for_approval",
        summary: message.slice(0, 120) || "A clear social-ready edit.",
        assumptions: ["MIMIC will use practical defaults for any unclear creative choices."],
        resolved_choices: [],
        intake: {},
        intake_confidence: {},
        vibe: ["clear", "natural", "social-ready"],
        pacing: "Start clearly, build energy in the middle, end cleanly.",
        clip_preferences: ["strong opening shot", "natural movement", "clear subject moments"],
        avoid: ["random cuts", "forced captions"],
        text_style: "Short, simple caption that matches the mood.",
        music_direction: "Cut to the main beats without making it chaotic.",
        question: "",
        questions: [],
        production_prompt: message || "Create a clear social-ready short-form edit."
      };
    }

    const res = await fetch(`${API_BASE}/api/brief/understand`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, current_brief: currentBrief || null }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Could not build the creative brief");
    }

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
    const cached = type !== "results" ? getCachedIntel(cacheKey) : undefined;
    if (cached) return cached;

    const res = await fetch(`${API_BASE}/api/intelligence?type=${type}&filename=${encodeURIComponent(key)}`);
    if (!res.ok) throw new Error("Intelligence data not found");
    const data: unknown = await res.json();
    if (type !== "results") setCachedIntel(cacheKey, data);
    return data;
  },

  renderEdl: async (filename: string, decisions: RenderEdlDecision[], styleConfig?: StyleConfig, textOverlay?: string) => {
    if (IS_DEMO) return { success: true, filename };
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/pipeline/render_edl`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, decisions, style_config: styleConfig, text_overlay: textOverlay }),
      });
    } catch {
      throw new Error(`Could not reach the renderer at ${API_BASE}. Make sure the backend is running, then try Render Changes again.`);
    }
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "EDL rendering failed");
    }
    return res.json();
  },
};
