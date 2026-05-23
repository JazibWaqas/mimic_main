"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
    ArrowLeft,
    Check,
    ChevronLeft,
    ChevronRight,
    Clock,
    Film,
    Loader2,
    Music,
    Pause,
    Play,
    RotateCcw,
    Save,
    Search,
    SlidersHorizontal,
    Smartphone,
    Sparkles,
    Type,
    Wand2,
    Zap
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { StyleConfig } from "@/lib/types";

type EditDecision = {
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

type ClipMetadata = {
    filename: string;
    filepath?: string;
    duration?: number;
    energy?: string;
    vibes?: string[];
    primary_subject?: string[];
    emotional_tone?: string[];
    content_description?: string;
    clip_quality?: number;
    best_moments?: Record<string, { start: number; end: number }>;
};

type AdvisorAlternative = {
    clip_filename: string;
    energy_level?: string;
    transition_type?: string;
    reason?: string;
    confidence?: number;
};

type IntelligencePayload = {
    edl?: { decisions?: EditDecision[] };
    clip_index?: { clips?: ClipMetadata[] };
    advisor?: {
        segment_moment_plans?: Record<string, { advisor_alternatives?: AdvisorAlternative[] }>;
    };
    blueprint?: {
        total_duration?: number;
        text_overlay?: string;
        segments?: Array<{
            id?: number;
            energy?: string;
            vibe?: string;
            arc_stage?: string;
            start?: number;
            end?: number;
            duration?: number;
        }>;
    };
    style_config?: StyleConfig;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MIN_CUT_DURATION = 0.25;

type LookState = {
    captionText: string;
    captionPosition: "top" | "center" | "bottom";
    fontFamily: string;
    colorPreset: StyleConfig["color"]["preset"];
};

type EditDraft = LookState & {
    decisions?: EditDecision[];
    savedAt?: string;
};

const DEFAULT_LOOK: LookState = {
    captionText: "",
    captionPosition: "bottom",
    fontFamily: "Inter",
    colorPreset: "neutral"
};

const getDraftKey = (name: string) => `mimic-edit-draft:${name}`;

const getBasename = (path: string) => {
    if (!path) return "";
    const parts = path.split(/[\\/]/);
    return parts[parts.length - 1] || path;
};

const formatTime = (seconds: number) => {
    if (!Number.isFinite(seconds)) return "0:00.0";
    const safe = Math.max(0, seconds);
    const mins = Math.floor(safe / 60);
    const secs = safe - mins * 60;
    return `${mins}:${secs.toFixed(1).padStart(4, "0")}`;
};

const clamp = (value: number, min: number, max: number) => {
    if (max < min) return min;
    return Math.min(max, Math.max(min, value));
};

const cutDuration = (decision: EditDecision) => {
    return Math.max(0, decision.timeline_end - decision.timeline_start);
};

const normalizeTimeline = (items: EditDecision[]) => {
    let cursor = 0;
    return items.map((item) => {
        const duration = Math.max(MIN_CUT_DURATION, cutDuration(item));
        const next = {
            ...item,
            timeline_start: Number(cursor.toFixed(4)),
            timeline_end: Number((cursor + duration).toFixed(4))
        };
        cursor += duration;
        return next;
    });
};

export default function VaultEditPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const filename = searchParams.get("filename");

    const videoRef = useRef<HTMLVideoElement>(null);
    const timelineScrollRef = useRef<HTMLDivElement>(null);
    const lastTimeUpdateRef = useRef(0);

    const [loading, setLoading] = useState(true);
    const [rendering, setRendering] = useState(false);
    const [renderStage, setRenderStage] = useState("");
    const [intelligence, setIntelligence] = useState<IntelligencePayload | null>(null);
    const [decisions, setDecisions] = useState<EditDecision[]>([]);
    const [originalDecisions, setOriginalDecisions] = useState<EditDecision[]>([]);
    const [selectedIdx, setSelectedIdx] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [clipQuery, setClipQuery] = useState("");
    const [isDirty, setIsDirty] = useState(false);
    const [zoomLevel, setZoomLevel] = useState(92);
    const [previewMode, setPreviewMode] = useState<"rendered" | "source">("rendered");
    const [previewCandidateFilename, setPreviewCandidateFilename] = useState<string | null>(null);
    const [previewVersion, setPreviewVersion] = useState(Date.now());
    const [mobileView, setMobileView] = useState(false);
    const [hasSavedDraft, setHasSavedDraft] = useState(false);

    const [captionText, setCaptionText] = useState("");
    const [captionPosition, setCaptionPosition] = useState<"top" | "center" | "bottom">("bottom");
    const [fontFamily, setFontFamily] = useState("Inter");
    const [colorPreset, setColorPreset] = useState<StyleConfig["color"]["preset"]>("neutral");
    const [originalLook, setOriginalLook] = useState<LookState>(DEFAULT_LOOK);

    const clips = useMemo(() => intelligence?.clip_index?.clips || [], [intelligence?.clip_index?.clips]);

    const clipsByFilename = useMemo(() => {
        const map = new Map<string, ClipMetadata>();
        clips.forEach((clip) => map.set(clip.filename, clip));
        return map;
    }, [clips]);

    const clipsByPath = useMemo(() => {
        const map = new Map<string, ClipMetadata>();
        clips.forEach((clip) => {
            if (clip.filepath) {
                map.set(clip.filepath, clip);
                map.set(getBasename(clip.filepath), clip);
            }
            map.set(clip.filename, clip);
        });
        return map;
    }, [clips]);

    const resolveClipForDecision = (decision: EditDecision | null) => {
        if (!decision) return undefined;
        return clipsByPath.get(decision.clip_path) || clipsByPath.get(getBasename(decision.clip_path));
    };

    useEffect(() => {
        if (!filename) {
            toast.error("No result selected");
            router.push("/vault");
            return;
        }

        const loadData = async () => {
            try {
                setLoading(true);
                const data = (await api.fetchIntelligence("results", filename)) as IntelligencePayload;
                const clipList = data.clip_index?.clips || [];
                const pathMap = new Map<string, ClipMetadata>();

                clipList.forEach((clip) => {
                    pathMap.set(clip.filename, clip);
                    if (clip.filepath) {
                        pathMap.set(clip.filepath, clip);
                        pathMap.set(getBasename(clip.filepath), clip);
                    }
                });

                let parsed = data.edl?.decisions?.map((decision) => {
                    const matchedClip =
                        pathMap.get(decision.clip_path) ||
                        pathMap.get(getBasename(decision.clip_path));

                    return {
                        ...decision,
                        clip_path: matchedClip?.filename || decision.clip_path,
                        clip_start: Number(decision.clip_start || 0),
                        clip_end: Number(decision.clip_end || cutDuration(decision)),
                        timeline_start: Number(decision.timeline_start || 0),
                        timeline_end: Number(decision.timeline_end || 0),
                        hold_end_seconds: decision.hold_end_seconds || null,
                        reasoning: decision.reasoning || "",
                        vibe_match: Boolean(decision.vibe_match)
                    };
                });

                if (!parsed?.length && data.blueprint?.segments?.length) {
                    parsed = data.blueprint.segments.map((segment, index) => {
                        const clip = clipList[index % Math.max(1, clipList.length)];
                        const start = Number(segment.start || 0);
                        const segmentDuration = Number(segment.duration || ((segment.end || 0) - start) || 1.5);

                        return {
                            segment_id: segment.id || index + 1,
                            clip_path: clip?.filename || "",
                            clip_start: 0,
                            clip_end: segmentDuration,
                            timeline_start: start,
                            timeline_end: start + segmentDuration,
                            hold_end_seconds: null,
                            reasoning: "",
                            vibe_match: true
                        };
                    });
                }

                const normalized = normalizeTimeline(parsed || []);
                const baseLook: LookState = {
                    captionText: data.blueprint?.text_overlay || "",
                    captionPosition: data.style_config?.text?.position || "bottom",
                    fontFamily: String(data.style_config?.text?.font || "Inter"),
                    colorPreset: data.style_config?.color?.preset || "neutral"
                };
                let initialDecisions = normalized;
                let initialLook = baseLook;
                let draftApplied = false;

                const savedDraft = window.localStorage.getItem(getDraftKey(filename));
                if (savedDraft) {
                    try {
                        const draft = JSON.parse(savedDraft) as EditDraft;
                        if (Array.isArray(draft.decisions) && draft.decisions.length) {
                            initialDecisions = normalizeTimeline(draft.decisions);
                            initialLook = {
                                captionText: draft.captionText ?? baseLook.captionText,
                                captionPosition: draft.captionPosition ?? baseLook.captionPosition,
                                fontFamily: draft.fontFamily ?? baseLook.fontFamily,
                                colorPreset: draft.colorPreset ?? baseLook.colorPreset
                            };
                            draftApplied = true;
                        }
                    } catch {
                        window.localStorage.removeItem(getDraftKey(filename));
                    }
                }

                setIntelligence(data);
                setDecisions(initialDecisions);
                setOriginalDecisions(normalized);
                setSelectedIdx(0);
                setCaptionText(initialLook.captionText);
                setCaptionPosition(initialLook.captionPosition);
                setFontFamily(initialLook.fontFamily);
                setColorPreset(initialLook.colorPreset);
                setOriginalLook(baseLook);
                setHasSavedDraft(draftApplied);
                setIsDirty(
                    draftApplied &&
                    (JSON.stringify(initialDecisions) !== JSON.stringify(normalized) ||
                        JSON.stringify(initialLook) !== JSON.stringify(baseLook))
                );
            } catch {
                toast.error("Could not load this edit");
            } finally {
                setLoading(false);
            }
        };

        loadData();
    }, [filename, router]);

    const totalDuration = useMemo(() => {
        return decisions.length ? decisions[decisions.length - 1].timeline_end : 0;
    }, [decisions]);

    const selectedDecision = decisions[selectedIdx] || null;
    const selectedClip = resolveClipForDecision(selectedDecision);
    const selectedSegment = intelligence?.blueprint?.segments?.[selectedIdx];
    const selectedDuration = selectedDecision ? cutDuration(selectedDecision) : 0;
    const selectedOriginalDecision = originalDecisions[selectedIdx] || null;
    const selectedCutChanged = Boolean(
        selectedDecision &&
        selectedOriginalDecision &&
        JSON.stringify(selectedDecision) !== JSON.stringify(selectedOriginalDecision)
    );
    const sourceDuration = Math.max(
        selectedClip?.duration || 0,
        selectedDecision?.clip_end || 0,
        selectedDuration || 0,
        1
    );
    const slipMax = Math.max(0, sourceDuration - selectedDuration);

    const getPreferredMomentStart = (clip: ClipMetadata | undefined) => {
        if (!clip) return 0;
        const segmentEnergy = selectedSegment?.energy || selectedClip?.energy || clip.energy || "Medium";
        const moment =
            clip.best_moments?.[segmentEnergy] ||
            clip.best_moments?.High ||
            clip.best_moments?.Medium ||
            clip.best_moments?.Low;

        return clamp(moment?.start || 0, 0, Math.max(0, (clip.duration || selectedDuration || 1) - selectedDuration));
    };

    const advisorAlternatives = useMemo(() => {
        if (!selectedDecision) return [];
        const plans = intelligence?.advisor?.segment_moment_plans || {};
        return plans[String(selectedDecision.segment_id)]?.advisor_alternatives || [];
    }, [intelligence, selectedDecision]);

    const suggestedRows = useMemo(() => {
        const seen = new Set<string>();
        const rows: Array<{ clip: ClipMetadata; confidence?: number; reason?: string; source: "advisor" | "library" }> = [];

        advisorAlternatives.forEach((alternative) => {
            const clip = clipsByFilename.get(alternative.clip_filename);
            if (clip && !seen.has(clip.filename)) {
                seen.add(clip.filename);
                rows.push({
                    clip,
                    confidence: alternative.confidence,
                    reason: alternative.reason,
                    source: "advisor"
                });
            }
        });

        const query = clipQuery.trim().toLowerCase();
        clips.forEach((clip) => {
            if (seen.has(clip.filename)) return;
            if (selectedClip?.filename === clip.filename) return;

            const searchable = [
                clip.filename,
                clip.energy,
                clip.content_description,
                ...(clip.vibes || []),
                ...(clip.primary_subject || []),
                ...(clip.emotional_tone || [])
            ].filter(Boolean).join(" ").toLowerCase();

            if (!query || searchable.includes(query)) {
                seen.add(clip.filename);
                rows.push({ clip, source: "library" });
            }
        });

        return rows.slice(0, 18);
    }, [advisorAlternatives, clipQuery, clips, clipsByFilename, selectedClip?.filename]);

    const videoUrl = filename ? `${API_BASE}/api/files/results/${encodeURIComponent(filename)}` : "";
    const previewCandidateClip = previewCandidateFilename ? clipsByFilename.get(previewCandidateFilename) : undefined;
    const sourcePreviewClip = previewCandidateClip || selectedClip;
    const sourcePreviewDuration = Math.max(
        sourcePreviewClip?.duration || 0,
        previewCandidateClip ? selectedDuration : sourceDuration,
        1
    );
    const sourcePreviewStart = previewCandidateClip
        ? getPreferredMomentStart(previewCandidateClip)
        : selectedDecision?.clip_start || 0;
    const sourcePreviewEnd = Math.min(sourcePreviewDuration, sourcePreviewStart + selectedDuration);
    const sourcePreviewUrl = sourcePreviewClip
        ? `${API_BASE}/api/files/samples/clips/${encodeURIComponent(sourcePreviewClip.filename)}?v=${previewVersion}`
        : "";
    const renderedPreviewUrl = `${videoUrl}?v=${previewVersion}`;
    const activePreviewUrl = previewMode === "source" && sourcePreviewUrl ? sourcePreviewUrl : renderedPreviewUrl;
    const previewLabel = previewMode === "source"
        ? previewCandidateClip
            ? `Previewing replacement: ${previewCandidateClip.filename}`
            : `Previewing selected cut: ${sourcePreviewClip?.filename || "source clip"}`
        : "Watching rendered edit";
    const displayCurrentTime = previewMode === "source"
        ? clamp(currentTime - sourcePreviewStart, 0, selectedDuration)
        : currentTime;
    const displayTotalTime = previewMode === "source" ? selectedDuration : (totalDuration || duration);
    const timelineWidth = Math.max(760, totalDuration * zoomLevel);
    const activeTimelineIdx = decisions.findIndex((decision) => {
        if (previewMode === "source") return false;
        return currentTime >= decision.timeline_start && currentTime < decision.timeline_end;
    });
    const currentLook = useMemo<LookState>(() => ({
        captionText,
        captionPosition,
        fontFamily,
        colorPreset
    }), [captionText, captionPosition, colorPreset, fontFamily]);

    const waveformBars = useMemo(() => {
        const count = Math.max(56, Math.floor(totalDuration * 5));
        return Array.from({ length: count }, (_, index) => {
            const wave = Math.sin(index * 0.73) + Math.sin(index * 0.19 + 1.7);
            return 18 + Math.abs(wave) * 18 + ((index * 17) % 11);
        });
    }, [totalDuration]);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        const onTimeUpdate = () => {
            if (previewMode === "source" && video.currentTime >= sourcePreviewEnd) {
                video.pause();
                video.currentTime = sourcePreviewEnd;
                setIsPlaying(false);
                setCurrentTime(video.currentTime);
                return;
            }

            const now = performance.now();
            if (now - lastTimeUpdateRef.current < 160) return;
            lastTimeUpdateRef.current = now;
            setCurrentTime(video.currentTime);
        };
        const onLoaded = () => {
            setDuration(video.duration || totalDuration);
            if (previewMode === "source") {
                video.currentTime = sourcePreviewStart;
                setCurrentTime(sourcePreviewStart);
            }
        };
        const onEnded = () => setIsPlaying(false);

        video.addEventListener("timeupdate", onTimeUpdate);
        video.addEventListener("loadedmetadata", onLoaded);
        video.addEventListener("ended", onEnded);

        return () => {
            video.removeEventListener("timeupdate", onTimeUpdate);
            video.removeEventListener("loadedmetadata", onLoaded);
            video.removeEventListener("ended", onEnded);
        };
    }, [activePreviewUrl, previewMode, sourcePreviewEnd, sourcePreviewStart, totalDuration]);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        video.pause();
        setIsPlaying(false);
        video.load();

        if (previewMode === "source") {
            const applyStart = () => {
                video.currentTime = sourcePreviewStart;
                setCurrentTime(sourcePreviewStart);
            };

            if (video.readyState >= 1) {
                applyStart();
            } else {
                video.addEventListener("loadedmetadata", applyStart, { once: true });
                return () => video.removeEventListener("loadedmetadata", applyStart);
            }
        } else if (selectedDecision) {
            const renderedStart = clamp(selectedDecision.timeline_start, 0, totalDuration || duration || 0);
            if (video.readyState >= 1) {
                video.currentTime = renderedStart;
                setCurrentTime(renderedStart);
            }
        }
    }, [activePreviewUrl, duration, previewMode, selectedDecision, sourcePreviewStart, totalDuration]);

    const markChanged = () => setIsDirty(true);

    const selectCut = (index: number) => {
        setSelectedIdx(index);
        setPreviewCandidateFilename(null);
        const decision = decisions[index];
        if (decision && previewMode === "rendered") {
            seek(decision.timeline_start);
        }
    };

    const seek = (time: number) => {
        const video = videoRef.current;
        const minTime = previewMode === "source" ? sourcePreviewStart : 0;
        const maxTime = previewMode === "source" ? sourcePreviewEnd : (totalDuration || duration || 0);
        const nextTime = clamp(time, minTime, maxTime);
        if (video) video.currentTime = nextTime;
        setCurrentTime(nextTime);
    };

    const showRenderedPreview = () => {
        setPreviewMode("rendered");
        setPreviewCandidateFilename(null);
    };

    const showSelectedSourcePreview = () => {
        setPreviewMode("source");
        setPreviewCandidateFilename(null);
    };

    const togglePlayback = async () => {
        const video = videoRef.current;
        if (!video) return;

        if (isPlaying) {
            video.pause();
            setIsPlaying(false);
            return;
        }

        try {
            if (previewMode === "source" && video.currentTime >= sourcePreviewEnd - 0.02) {
                video.currentTime = sourcePreviewStart;
                setCurrentTime(sourcePreviewStart);
            }
            await video.play();
            setIsPlaying(true);
        } catch {
            setIsPlaying(false);
        }
    };

    const updateSelectedDecision = (updater: (decision: EditDecision) => EditDecision) => {
        if (!selectedDecision) return;

        setDecisions((prev) => {
            const next = prev.map((decision, index) => (
                index === selectedIdx ? updater({ ...decision }) : decision
            ));
            return normalizeTimeline(next);
        });
        markChanged();
    };

    const setSelectedDuration = (nextDuration: number) => {
        updateSelectedDecision((decision) => {
            const durationValue = Math.max(MIN_CUT_DURATION, nextDuration);
            const clipStart = clamp(decision.clip_start, 0, sourceDuration);
            const naturalClipEnd = clipStart + durationValue;

            return {
                ...decision,
                timeline_end: decision.timeline_start + durationValue,
                clip_start: clipStart,
                clip_end: Math.min(sourceDuration, naturalClipEnd),
                hold_end_seconds: naturalClipEnd > sourceDuration ? naturalClipEnd - sourceDuration : null
            };
        });
    };

    const nudgeDuration = (amount: number) => {
        setSelectedDuration(selectedDuration + amount);
    };

    const setSlipStart = (nextStart: number) => {
        updateSelectedDecision((decision) => {
            const start = clamp(nextStart, 0, slipMax);
            return {
                ...decision,
                clip_start: start,
                clip_end: Math.min(sourceDuration, start + selectedDuration),
                hold_end_seconds: null
            };
        });
    };

    const swapToClip = (clip: ClipMetadata) => {
        if (!selectedDecision) return;

        const clipDuration = Math.max(clip.duration || selectedDuration || 1, 1);
        const start = getPreferredMomentStart(clip);

        updateSelectedDecision((decision) => ({
            ...decision,
            clip_path: clip.filename,
            clip_start: start,
            clip_end: Math.min(clipDuration, start + selectedDuration),
            hold_end_seconds: start + selectedDuration > clipDuration ? start + selectedDuration - clipDuration : null,
            reasoning: `Manually replaced with ${clip.filename}.`
        }));

        setPreviewMode("source");
        setPreviewCandidateFilename(null);
        toast.success(`Swapped in ${clip.filename}`);
    };

    const previewReplacementClip = (clip: ClipMetadata) => {
        setPreviewMode("source");
        setPreviewCandidateFilename(clip.filename);
    };

    const revertSelectedCut = () => {
        if (!selectedOriginalDecision) return;

        const reverted = normalizeTimeline(decisions.map((decision, index) => (
            index === selectedIdx ? { ...selectedOriginalDecision } : decision
        )));
        setDecisions(reverted);
        setIsDirty(JSON.stringify(reverted) !== JSON.stringify(originalDecisions));
        setPreviewCandidateFilename(null);
        setPreviewMode("rendered");
        toast.info("Selected cut reverted");
    };

    const resetChanges = () => {
        setDecisions(originalDecisions);
        setSelectedIdx(0);
        setCaptionText(originalLook.captionText);
        setCaptionPosition(originalLook.captionPosition);
        setFontFamily(originalLook.fontFamily);
        setColorPreset(originalLook.colorPreset);
        setPreviewMode("rendered");
        setPreviewCandidateFilename(null);
        setIsDirty(false);
        setClipQuery("");
        if (filename) {
            window.localStorage.removeItem(getDraftKey(filename));
        }
        setHasSavedDraft(false);
        toast.info("Timeline reset");
    };

    const saveDraft = () => {
        if (!filename) return;

        const draft: EditDraft = {
            ...currentLook,
            decisions,
            savedAt: new Date().toISOString()
        };

        window.localStorage.setItem(getDraftKey(filename), JSON.stringify(draft));
        setHasSavedDraft(true);
        toast.success("Draft saved");
    };

    const triggerRender = async () => {
        if (!filename || !decisions.length) return;

        setRendering(true);
        setRenderStage("Preparing timeline");

        try {
            const styleConfig: StyleConfig = {
                text: {
                    font: fontFamily,
                    weight: 600,
                    color: "#FFFFFF",
                    shadow: true,
                    position: captionPosition,
                    animation: "fade"
                },
                color: { preset: colorPreset },
                texture: { grain: false }
            };

            const cleanDecisions = normalizeTimeline(decisions).map((decision) => ({
                ...decision,
                clip_start: Number(decision.clip_start.toFixed(4)),
                clip_end: Number(decision.clip_end.toFixed(4)),
                timeline_start: Number(decision.timeline_start.toFixed(4)),
                timeline_end: Number(decision.timeline_end.toFixed(4)),
                hold_end_seconds: decision.hold_end_seconds ? Number(decision.hold_end_seconds.toFixed(4)) : null
            }));

            setRenderStage("Rendering revised edit");
            await api.renderEdl(filename, cleanDecisions, styleConfig, captionText);

            setRenderStage("Reloading preview");
            setDecisions(cleanDecisions);
            setOriginalDecisions(cleanDecisions);
            setOriginalLook(currentLook);
            setIsDirty(false);
            setHasSavedDraft(false);
            setPreviewMode("rendered");
            setPreviewCandidateFilename(null);
            setPreviewVersion(Date.now());
            window.localStorage.removeItem(getDraftKey(filename));

            const video = videoRef.current;
            if (video) {
                video.src = `${videoUrl}?v=${Date.now()}`;
                video.load();
                seek(0);
            }

            toast.success("Rendered updated edit");
        } catch (error) {
            toast.error(error instanceof Error ? error.message : "Render failed");
        } finally {
            setRendering(false);
            setRenderStage("");
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-[#050507] text-white flex items-center justify-center px-6 py-16">
                <div className="flex items-center gap-3 text-sm text-slate-400">
                    <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
                    Loading timeline
                </div>
            </div>
        );
    }

    if (!filename || !decisions.length) {
        return (
            <div className="min-h-screen bg-[#050507] text-white flex items-center justify-center px-6 py-16">
                <div className="max-w-md text-center space-y-4">
                    <Film className="h-8 w-8 mx-auto text-slate-600" />
                    <h1 className="text-xl font-bold">No editable timeline found</h1>
                    <button
                        onClick={() => router.push("/vault")}
                        className="h-10 px-4 rounded-lg bg-white text-black text-sm font-bold"
                    >
                        Back to Vault
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#07080b] text-slate-100 overflow-x-hidden font-sans">
            <div className="max-w-[1700px] mx-auto px-6 md:px-12 pt-6 pb-12 space-y-6">
                <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border border-white/10 bg-black/30 rounded-lg p-4 md:p-5">
                    <div className="flex items-center gap-3 min-w-0">
                        <button
                            onClick={() => router.push(`/vault?filename=${encodeURIComponent(filename)}&type=results`)}
                            className="h-10 w-10 rounded-lg border border-white/10 bg-white/[0.04] text-slate-300 hover:text-white hover:bg-white/[0.08] flex items-center justify-center transition-colors"
                            aria-label="Back to Vault"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </button>
                        <div className="min-w-0">
                            <div className="flex items-center gap-2">
                                <h1 className="text-lg font-black tracking-tight text-white">Edit Timeline</h1>
                                {isDirty && (
                                    <span className="rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 border border-amber-500/20">
                                        Unsaved
                                    </span>
                                )}
                                {hasSavedDraft && (
                                    <span className="rounded bg-cyan-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-cyan-200 border border-cyan-500/20">
                                        Draft Saved
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-slate-500 truncate max-w-[560px]">{filename}</p>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            onClick={saveDraft}
                            disabled={!isDirty || rendering}
                            className="h-10 px-4 rounded-lg border border-cyan-400/20 bg-cyan-400/[0.07] text-sm font-semibold text-cyan-100 hover:bg-cyan-400/[0.12] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            <Save className="h-4 w-4" />
                            Save Draft
                        </button>
                        <button
                            onClick={resetChanges}
                            disabled={!isDirty || rendering}
                            className="h-10 px-4 rounded-lg border border-white/10 bg-white/[0.04] text-sm font-semibold text-slate-300 hover:bg-white/[0.08] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            <RotateCcw className="h-4 w-4" />
                            Reset All
                        </button>
                        <button
                            onClick={triggerRender}
                            disabled={rendering}
                            className="h-10 px-5 rounded-lg bg-indigo-600 text-white text-sm font-bold hover:bg-indigo-500 disabled:opacity-60 flex items-center gap-2 shadow-[0_0_24px_rgba(79,70,229,0.35)]"
                        >
                            {rendering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                            Render Changes
                        </button>
                    </div>
                </header>

                <main className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_minmax(340px,420px)] gap-6 items-start">
                    <section className="min-w-0 space-y-6">
                        <div className="rounded-lg border border-white/10 bg-black/35 overflow-hidden grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.42fr)]">
                            <div className="flex flex-col">
                                <div className="border-b border-white/10 flex flex-col gap-3 px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
                                            <Film className="h-4 w-4 text-indigo-300" />
                                            Preview
                                        </div>
                                        <div className="mt-1 text-xs text-slate-500 truncate">{previewLabel}</div>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <button
                                            type="button"
                                            onClick={showRenderedPreview}
                                            className={cn(
                                                "h-8 rounded-lg px-3 text-xs font-bold transition-colors",
                                                previewMode === "rendered"
                                                    ? "bg-indigo-500 text-white"
                                                    : "bg-white/[0.05] text-slate-400 hover:text-white hover:bg-white/[0.08]"
                                            )}
                                        >
                                            Rendered Edit
                                        </button>
                                        <button
                                            type="button"
                                            onClick={showSelectedSourcePreview}
                                            className={cn(
                                                "h-8 rounded-lg px-3 text-xs font-bold transition-colors",
                                                previewMode === "source" && !previewCandidateClip
                                                    ? "bg-cyan-500 text-black"
                                                    : "bg-white/[0.05] text-slate-400 hover:text-white hover:bg-white/[0.08]"
                                            )}
                                        >
                                            Selected Cut
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setMobileView((value) => !value)}
                                            className={cn(
                                                "h-8 w-8 rounded-lg border flex items-center justify-center transition-colors",
                                                mobileView
                                                    ? "border-indigo-400/40 bg-indigo-500/20 text-white"
                                                    : "border-white/10 bg-white/[0.05] text-slate-400 hover:text-white hover:bg-white/[0.08]"
                                            )}
                                            title={mobileView ? "Wide preview" : "Phone preview"}
                                            aria-label={mobileView ? "Switch to wide preview" : "Switch to phone preview"}
                                        >
                                            <Smartphone className="h-4 w-4" />
                                        </button>
                                        <div className="font-mono text-xs text-slate-500 pl-1">
                                            {formatTime(displayCurrentTime)} / {formatTime(displayTotalTime)}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center justify-center px-5 py-8 lg:py-10 bg-[#030304]">
                                    <div
                                        className={cn(
                                            "relative rounded-[2.5rem] bg-black border border-white/10 overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)] transition-all duration-300",
                                            mobileView
                                                ? "w-full max-w-[420px] aspect-[2/3]"
                                                : "w-full max-w-[640px] aspect-[15/14]"
                                        )}
                                    >
                                        <video
                                            ref={videoRef}
                                            key={activePreviewUrl}
                                            src={activePreviewUrl}
                                            className="h-full w-full object-cover bg-black"
                                            playsInline
                                            controls
                                        />
                                        {previewMode === "source" && (
                                            <div className="absolute left-4 top-4 rounded-md bg-black/70 border border-white/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-cyan-200 backdrop-blur">
                                                Source Preview
                                            </div>
                                        )}
                                        {captionText && (
                                            <div
                                                className={cn(
                                                    "pointer-events-none absolute inset-x-4 text-center text-white drop-shadow-[0_4px_18px_rgba(0,0,0,0.95)]",
                                                    captionPosition === "top" && "top-10",
                                                    captionPosition === "center" && "top-1/2 -translate-y-1/2",
                                                    captionPosition === "bottom" && "bottom-12"
                                                )}
                                                style={{
                                                    fontFamily,
                                                    fontWeight: 800,
                                                    fontSize: "clamp(18px, 2.4vh, 28px)"
                                                }}
                                            >
                                                {captionText}
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="h-16 shrink-0 border-t border-white/10 flex items-center justify-center gap-5 px-4">
                                    <button
                                        onClick={() => seek(currentTime - 1)}
                                        className="h-9 w-9 rounded-lg bg-white/[0.04] border border-white/10 text-slate-300 hover:text-white hover:bg-white/[0.08] flex items-center justify-center"
                                        aria-label="Back one second"
                                    >
                                        <ChevronLeft className="h-5 w-5" />
                                    </button>
                                    <button
                                        onClick={togglePlayback}
                                        className="h-11 w-11 rounded-full bg-white text-black hover:scale-105 transition-transform flex items-center justify-center shadow-[0_0_24px_rgba(255,255,255,0.18)]"
                                        aria-label={isPlaying ? "Pause" : "Play"}
                                    >
                                        {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 fill-current ml-0.5" />}
                                    </button>
                                    <button
                                        onClick={() => seek(currentTime + 1)}
                                        className="h-9 w-9 rounded-lg bg-white/[0.04] border border-white/10 text-slate-300 hover:text-white hover:bg-white/[0.08] flex items-center justify-center"
                                        aria-label="Forward one second"
                                    >
                                        <ChevronRight className="h-5 w-5" />
                                    </button>
                                </div>
                            </div>

                            <aside className="border-t lg:border-t-0 lg:border-l border-white/10 bg-[#090a0d] flex flex-col">
                                <div className="h-11 shrink-0 border-b border-white/10 px-4 flex items-center gap-2 text-xs font-bold text-slate-300">
                                    <Wand2 className="h-4 w-4 text-cyan-300" />
                                    Quick Look
                                </div>
                                <div className="p-4 space-y-4">
                                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                                        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Selected Cut</div>
                                        <div className="mt-1 text-sm font-bold text-white truncate">
                                            {selectedClip?.filename || getBasename(selectedDecision?.clip_path || "")}
                                        </div>
                                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                                            <div className="rounded bg-black/35 border border-white/10 p-2">
                                                <div className="text-slate-500">Duration</div>
                                                <div className="font-mono text-white">{selectedDuration.toFixed(2)}s</div>
                                            </div>
                                            <div className="rounded bg-black/35 border border-white/10 p-2">
                                                <div className="text-slate-500">Energy</div>
                                                <div className="text-white truncate">{selectedSegment?.energy || selectedClip?.energy || "Mixed"}</div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                                        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Segment Intent</div>
                                        <div className="mt-1 text-sm text-slate-200">
                                            {selectedSegment?.arc_stage || "Main"} · {selectedSegment?.vibe || "General"}
                                        </div>
                                    </div>

                                    {selectedDecision?.reasoning && (
                                        <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/[0.04] p-3">
                                            <div className="text-[10px] uppercase tracking-wider text-indigo-300 font-bold">Why MIMIC Picked It</div>
                                            <p className="mt-2 text-xs leading-relaxed text-indigo-100/75">
                                                {selectedDecision.reasoning}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </aside>
                        </div>

                        <section className="rounded-lg border border-white/10 bg-black/40 overflow-hidden">
                            <div className="border-b border-white/10 px-4 py-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
                                        <Clock className="h-4 w-4 text-indigo-300" />
                                        Timeline
                                    </div>
                                    <div className="text-xs font-mono text-slate-500">{decisions.length} cuts · {totalDuration.toFixed(2)}s</div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Zoom</span>
                                    <input
                                        type="range"
                                        min={56}
                                        max={170}
                                        value={zoomLevel}
                                        onChange={(event) => setZoomLevel(Number(event.target.value))}
                                        className="w-28 accent-indigo-500"
                                    />
                                </div>
                            </div>

                            <div className="flex">
                                <div className="w-28 sm:w-32 shrink-0 border-r border-white/10 bg-[#08090b]">
                                    <div className="h-8 border-b border-white/10" />
                                    <div className="h-20 px-4 flex items-center gap-2 text-sm font-bold text-slate-300">
                                        <Film className="h-4 w-4 text-indigo-300" />
                                        Video
                                    </div>
                                    <div className="h-14 px-4 flex items-center gap-2 text-sm font-bold text-slate-500 border-t border-white/5">
                                        <Music className="h-4 w-4 text-emerald-400" />
                                        Audio
                                    </div>
                                </div>

                                <div ref={timelineScrollRef} className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden custom-scrollbar">
                                    <div className="relative" style={{ width: `${timelineWidth}px` }}>
                                        <div className="relative h-8 border-b border-white/10">
                                            {Array.from({ length: Math.floor(totalDuration) + 2 }).map((_, index) => {
                                                const left = index * zoomLevel;
                                                return (
                                                    <div key={index} className="absolute bottom-0" style={{ left }}>
                                                        <div className="h-2 w-px bg-white/25" />
                                                        <span className="absolute -top-4 -translate-x-1/2 text-[10px] font-mono text-slate-600">{index}s</span>
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        <div className="relative h-20 border-b border-white/5">
                                            {decisions.map((decision, index) => {
                                                const blockWidth = Math.max(18, cutDuration(decision) * zoomLevel);
                                                const isSelected = index === selectedIdx;
                                                const isActive = index === activeTimelineIdx;
                                                const clip = clipsByPath.get(decision.clip_path) || clipsByPath.get(getBasename(decision.clip_path));

                                                return (
                                                    <button
                                                        key={`${decision.segment_id}-${index}`}
                                                        type="button"
                                                        title={`${clip?.filename || getBasename(decision.clip_path)} · ${cutDuration(decision).toFixed(2)}s`}
                                                        onClick={() => selectCut(index)}
                                                        className={cn(
                                                            "absolute top-3 h-14 rounded-lg border text-left overflow-hidden transition-colors",
                                                            isSelected
                                                                ? "border-indigo-300 bg-indigo-500/35 shadow-[0_0_18px_rgba(99,102,241,0.35)]"
                                                                : "border-white/10 bg-[#15162a] hover:border-white/25 hover:bg-[#1b1d35]",
                                                            isActive && !isSelected && "border-cyan-300/50"
                                                        )}
                                                        style={{
                                                            left: `${decision.timeline_start * zoomLevel}px`,
                                                            width: `${blockWidth}px`
                                                        }}
                                                    >
                                                        <div className="h-full px-2 py-1.5 flex flex-col justify-between">
                                                            <span className="text-[10px] font-black text-white truncate">
                                                                {clip?.filename || getBasename(decision.clip_path)}
                                                            </span>
                                                            <span className="text-[10px] font-mono text-slate-400">
                                                                {cutDuration(decision).toFixed(1)}s
                                                            </span>
                                                        </div>
                                                    </button>
                                                );
                                            })}

                                            <div
                                                className="absolute top-0 bottom-0 w-px bg-cyan-300 pointer-events-none"
                                                style={{ left: `${currentTime * zoomLevel}px` }}
                                            >
                                                <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 h-3 w-3 rounded bg-cyan-300 shadow-[0_0_12px_rgba(34,211,238,0.8)]" />
                                            </div>
                                        </div>

                                        <div className="relative h-14">
                                            <div className="absolute left-0 right-0 top-3 h-8 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] px-2 flex items-center gap-px overflow-hidden">
                                                {waveformBars.map((height, index) => (
                                                    <span
                                                        key={index}
                                                        className="flex-1 rounded-full bg-emerald-300/70"
                                                        style={{ height: `${height}%` }}
                                                    />
                                                ))}
                                                <span className="absolute left-3 top-1/2 -translate-y-1/2 rounded bg-[#061511]/90 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-200">
                                                    Rendered audio
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </section>

                    <aside className="rounded-lg border border-white/10 bg-[#090a0d] overflow-hidden">
                        <div className="border-b border-white/10 px-4 py-3 flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
                                <SlidersHorizontal className="h-4 w-4 text-indigo-300" />
                                Cut Controls
                            </div>
                            <div className="text-xs font-mono text-slate-500">#{selectedIdx + 1}</div>
                        </div>

                        <div className="p-4 space-y-5">
                            <section className="rounded-lg border border-white/10 bg-white/[0.03] p-4 space-y-3">
                                <div>
                                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Current Clip</div>
                                    <div className="mt-1 text-base font-black text-white truncate">
                                        {selectedClip?.filename || getBasename(selectedDecision?.clip_path || "")}
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        type="button"
                                        onClick={showSelectedSourcePreview}
                                        className="h-9 rounded-lg border border-cyan-400/25 bg-cyan-400/[0.08] text-xs font-bold text-cyan-100 hover:bg-cyan-400/[0.14]"
                                    >
                                        Preview Cut
                                    </button>
                                    <button
                                        type="button"
                                        onClick={revertSelectedCut}
                                        disabled={!selectedCutChanged}
                                        className="h-9 rounded-lg border border-white/10 bg-black/35 text-xs font-bold text-slate-200 hover:bg-white/[0.07] disabled:opacity-40 disabled:cursor-not-allowed"
                                    >
                                        Revert Cut
                                    </button>
                                </div>

                                <div className="grid grid-cols-3 gap-2">
                                    <button
                                        onClick={() => nudgeDuration(-0.25)}
                                        className="h-9 rounded-lg border border-white/10 bg-black/35 text-sm font-bold text-slate-200 hover:bg-white/[0.07]"
                                    >
                                        -0.25s
                                    </button>
                                    <button
                                        onClick={() => setSelectedDuration(1.5)}
                                        className="h-9 rounded-lg border border-white/10 bg-black/35 text-sm font-bold text-slate-200 hover:bg-white/[0.07]"
                                    >
                                        1.5s
                                    </button>
                                    <button
                                        onClick={() => nudgeDuration(0.25)}
                                        className="h-9 rounded-lg border border-white/10 bg-black/35 text-sm font-bold text-slate-200 hover:bg-white/[0.07]"
                                    >
                                        +0.25s
                                    </button>
                                </div>

                                <label className="block space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Cut Length</span>
                                        <span className="text-xs font-mono text-white">{selectedDuration.toFixed(2)}s</span>
                                    </div>
                                    <input
                                        type="range"
                                        min={0.25}
                                        max={Math.max(6, sourceDuration + 2)}
                                        step={0.05}
                                        value={selectedDuration}
                                        onChange={(event) => setSelectedDuration(Number(event.target.value))}
                                        className="w-full accent-indigo-500"
                                    />
                                </label>

                                <label className="block space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Source Moment</span>
                                        <span className="text-xs font-mono text-white">
                                            {selectedDecision?.clip_start.toFixed(2)}s
                                        </span>
                                    </div>
                                    <input
                                        type="range"
                                        min={0}
                                        max={slipMax}
                                        step={0.05}
                                        value={selectedDecision?.clip_start || 0}
                                        onChange={(event) => setSlipStart(Number(event.target.value))}
                                        className="w-full accent-cyan-400"
                                    />
                                    <div className="flex justify-between text-[10px] font-mono text-slate-600">
                                        <span>0s</span>
                                        <span>{sourceDuration.toFixed(1)}s source</span>
                                    </div>
                                </label>
                            </section>

                            <section className="rounded-lg border border-white/10 bg-white/[0.03] p-4 space-y-3">
                                <div className="flex items-center gap-2">
                                    <Sparkles className="h-4 w-4 text-cyan-300" />
                                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Replace Clip</div>
                                </div>
                                <p className="text-xs leading-relaxed text-slate-500">
                                    Preview a clip first, then use it if it feels better. The rendered edit changes only after you render.
                                </p>
                                <div className="relative">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-600" />
                                    <input
                                        value={clipQuery}
                                        onChange={(event) => setClipQuery(event.target.value)}
                                        placeholder="Search clips"
                                        className="h-10 w-full rounded-lg border border-white/10 bg-black/35 pl-9 pr-3 text-sm text-white outline-none focus:border-indigo-400"
                                    />
                                </div>

                                <div className="space-y-2 max-h-[300px] overflow-y-auto custom-scrollbar pr-1">
                                    {suggestedRows.map((row) => {
                                        const isCurrent = row.clip.filename === selectedClip?.filename;
                                        const isPreviewing = previewMode === "source" && previewCandidateFilename === row.clip.filename;
                                        return (
                                            <div
                                                key={`${row.source}-${row.clip.filename}`}
                                                className={cn(
                                                    "w-full rounded-lg border p-3 text-left transition-colors",
                                                    isCurrent
                                                        ? "border-emerald-500/30 bg-emerald-500/[0.06]"
                                                        : isPreviewing
                                                            ? "border-cyan-400/50 bg-cyan-400/[0.08]"
                                                            : "border-white/10 bg-black/25 hover:border-indigo-400/50 hover:bg-indigo-500/[0.08]"
                                                )}
                                            >
                                                <div className="flex items-center justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <div className="text-sm font-bold text-white truncate">{row.clip.filename}</div>
                                                        <div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
                                                            {row.source === "advisor" ? "AI pick" : row.clip.energy || "Library"} · {(row.clip.duration || 0).toFixed(1)}s
                                                        </div>
                                                    </div>
                                                    {isCurrent ? (
                                                        <Check className="h-4 w-4 text-emerald-300 shrink-0" />
                                                    ) : row.confidence ? (
                                                        <span className="text-xs font-mono text-cyan-300">{Math.round(row.confidence * 100)}%</span>
                                                    ) : null}
                                                </div>
                                                {row.reason && (
                                                    <p className="mt-2 text-xs leading-relaxed text-slate-400 line-clamp-2">
                                                        {row.reason}
                                                    </p>
                                                )}
                                                <div className="mt-3 grid grid-cols-2 gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => previewReplacementClip(row.clip)}
                                                        className="h-8 rounded-md border border-cyan-400/25 bg-cyan-400/[0.08] text-xs font-bold text-cyan-100 hover:bg-cyan-400/[0.14]"
                                                    >
                                                        Preview
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => swapToClip(row.clip)}
                                                        disabled={isCurrent}
                                                        className="h-8 rounded-md border border-white/10 bg-white/[0.06] text-xs font-bold text-white hover:bg-white/[0.1] disabled:opacity-40 disabled:cursor-not-allowed"
                                                    >
                                                        Use Clip
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </section>

                            <section className="rounded-lg border border-white/10 bg-white/[0.03] p-4 space-y-3">
                                <div className="flex items-center gap-2">
                                    <Type className="h-4 w-4 text-indigo-300" />
                                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Text And Look</div>
                                </div>

                                <label className="block space-y-2">
                                    <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Caption</span>
                                    <input
                                        value={captionText}
                                        onChange={(event) => {
                                            setCaptionText(event.target.value);
                                            markChanged();
                                        }}
                                        className="h-10 w-full rounded-lg border border-white/10 bg-black/35 px-3 text-sm text-white outline-none focus:border-indigo-400"
                                    />
                                </label>

                                <div className="grid grid-cols-2 gap-2">
                                    <label className="block space-y-2">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Position</span>
                                        <select
                                            value={captionPosition}
                                            onChange={(event) => {
                                                setCaptionPosition(event.target.value as "top" | "center" | "bottom");
                                                markChanged();
                                            }}
                                            className="h-10 w-full rounded-lg border border-white/10 bg-black/35 px-3 text-sm text-white outline-none focus:border-indigo-400"
                                        >
                                            <option value="top">Top</option>
                                            <option value="center">Center</option>
                                            <option value="bottom">Bottom</option>
                                        </select>
                                    </label>

                                    <label className="block space-y-2">
                                        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Font</span>
                                        <select
                                            value={fontFamily}
                                            onChange={(event) => {
                                                setFontFamily(event.target.value);
                                                markChanged();
                                            }}
                                            className="h-10 w-full rounded-lg border border-white/10 bg-black/35 px-3 text-sm text-white outline-none focus:border-indigo-400"
                                        >
                                            <option value="Inter">Inter</option>
                                            <option value="Outfit">Outfit</option>
                                            <option value="Cormorant Garamond">Cormorant</option>
                                        </select>
                                    </label>
                                </div>

                                <label className="block space-y-2">
                                    <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Color Preset</span>
                                    <select
                                        value={colorPreset}
                                        onChange={(event) => {
                                            setColorPreset(event.target.value as StyleConfig["color"]["preset"]);
                                            markChanged();
                                        }}
                                        className="h-10 w-full rounded-lg border border-white/10 bg-black/35 px-3 text-sm text-white outline-none focus:border-indigo-400"
                                    >
                                        <option value="neutral">Neutral</option>
                                        <option value="warm">Warm</option>
                                        <option value="cool">Cool</option>
                                        <option value="vintage">Vintage</option>
                                        <option value="high_contrast">High Contrast</option>
                                    </select>
                                </label>
                            </section>
                        </div>
                    </aside>
                </main>
            </div>

            {rendering && (
                <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-6">
                    <div className="w-full max-w-sm rounded-lg border border-white/10 bg-[#090a0d] p-6 shadow-2xl">
                        <div className="flex items-center gap-3">
                            <Loader2 className="h-5 w-5 animate-spin text-indigo-300" />
                            <div>
                                <div className="text-sm font-black text-white">Rendering edit</div>
                                <div className="mt-1 text-xs text-slate-500">{renderStage || "Working"}</div>
                            </div>
                        </div>
                        <div className="mt-5 h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div className="h-full w-2/3 rounded-full bg-indigo-500 animate-pulse" />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
