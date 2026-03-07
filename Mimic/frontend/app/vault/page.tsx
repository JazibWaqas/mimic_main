"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import {
    Activity,
    MonitorPlay,
    X,
    Sparkles,
    Zap,
    Palette,
    BrainCircuit,
    ChevronDown,
    ChevronUp,
    Video,
    Search,
    Share2,
    Play,
    Info,
    History,
    MoreHorizontal,
    Download,
    Settings,
    Heart,
    Film,
    Clock,
    Music,
    Compass,
    Microscope,
    Footprints,
    Code2,
    BarChart3,
    Smartphone
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { Result, Reference, Clip, StyleConfig } from "@/lib/types";
import StylingModal from "@/components/StylingModal";
import type { TextStyle } from "@/components/StylingModal";

export type ViewMode = "results" | "references" | "clips";
export type AssetItem = Clip | Reference | Result;

type VaultDecision = {
    segment_id: number;
    what_i_tried: string;
    decision: string;
    what_if?: string;
    is_key?: boolean;
    importance?: "key" | "all" | string;
    tags?: string[];
};

type EdlDecision = {
    segment_id: number;
    clip_path?: string;
    reasoning?: string;
    timeline_start: number;
    timeline_end: number;
};

type VaultReportViewModel = {
    executive_summary?: string[];
    advisor?: { hero?: string; body?: string };
    decision_stream?: VaultDecision[];
    key_decision_stream?: VaultDecision[];
    friction_log?: string[];
    next_steps?: string[];
    technical?: string[];
    clip_suggestions?: string[];
    post_mortem?: {
        worked?: string;
        didnt?: string;
        responsibility?: { vibe?: string; emotion?: string };
    };
};

type IntelligenceViewModel = {
    vault_report?: VaultReportViewModel;
    edl?: { decisions?: EdlDecision[] };
    bpm?: number;
    style_config?: StyleConfig;
};

type AssetWithPath = { path?: string; filepath?: string; url?: string };

const VAULT_VISUAL_STORAGE_KEY = "mimic_vault_visual_styles";

function loadVaultVisualStore(): Map<string, TextStyle> {
    if (typeof window === "undefined") return new Map();
    try {
        const raw = localStorage.getItem(VAULT_VISUAL_STORAGE_KEY);
        if (!raw) return new Map();
        const obj = JSON.parse(raw) as Record<string, TextStyle>;
        return new Map(Object.entries(obj));
    } catch {
        return new Map();
    }
}

function saveVaultVisualStore(store: Map<string, TextStyle>) {
    if (typeof window === "undefined") return;
    try {
        const obj = Object.fromEntries(store);
        localStorage.setItem(VAULT_VISUAL_STORAGE_KEY, JSON.stringify(obj));
    } catch {
        // ignore
    }
}

export default function VaultPage() {
    const searchParams = useSearchParams();

    // Data state
    const [clips, setClips] = useState<Clip[]>([]);
    const [references, setReferences] = useState<Reference[]>([]);
    const [results, setResults] = useState<Result[]>([]);
    const [selectedItem, setSelectedItem] = useState<AssetItem | null>(null);
    const [viewMode, setViewMode] = useState<ViewMode>("results");
    const [loading, setLoading] = useState(true);
    const [intelligence, setIntelligence] = useState<IntelligenceViewModel | null>(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [searchQuery, setSearchQuery] = useState("");
    const [isPlaying, setIsPlaying] = useState(false);

    // Module expansion states for lower half
    const [advisorExpanded, setAdvisorExpanded] = useState(true);      // Expanded by default
    const [frictionExpanded, setFrictionExpanded] = useState(false);  // Collapsed by default
    const [postMortemExpanded, setPostMortemExpanded] = useState(true);  // Expanded by default
    const [nextStepsExpanded, setNextStepsExpanded] = useState(false);  // Collapsed by default
    const [technicalExpanded, setTechnicalExpanded] = useState(false);    // Collapsed by default
    const [intelExpanded, setIntelExpanded] = useState(true);

    const [advisorShowMore, setAdvisorShowMore] = useState(false);

    const [showAllDecisions, setShowAllDecisions] = useState(false);
    const [mobileView, setMobileView] = useState(false);
    const [isStylingOpen, setIsStylingOpen] = useState(false);
    const [isStylingLoading, setIsStylingLoading] = useState(false);

    const [vaultCaptionPreview, setVaultCaptionPreview] = useState<string>("");
    const [vaultCaptionPosition, setVaultCaptionPosition] = useState<'top' | 'center' | 'bottom'>('center');
    const [vaultCaptionFont, setVaultCaptionFont] = useState<string>("cormorant");
    const [vaultCaptionColor, setVaultCaptionColor] = useState<string>("#FFFFFF");
    const [vaultCaptionSize, setVaultCaptionSize] = useState<number>(22);

    const [vaultCaptionDraft, setVaultCaptionDraft] = useState<string>("");
    const [vaultCaptionPositionDraft, setVaultCaptionPositionDraft] = useState<'top' | 'center' | 'bottom'>('center');
    const [vaultCaptionFontDraft, setVaultCaptionFontDraft] = useState<string>("cormorant");
    const [vaultCaptionColorDraft, setVaultCaptionColorDraft] = useState<string>("#FFFFFF");
    const [vaultCaptionSizeDraft, setVaultCaptionSizeDraft] = useState<number>(22);

    const vaultTextStoreRef = useRef(new Map<string, TextStyle>());

    useEffect(() => {
        const loaded = loadVaultVisualStore();
        loaded.forEach((val, key) => vaultTextStoreRef.current.set(key, val));
    }, []);

    const videoRef = useRef<HTMLVideoElement>(null);
    const decisionListRef = useRef<HTMLDivElement>(null);

    // Fetch data
    useEffect(() => {
        const fetchAllAssets = async () => {
            try {
                const [clipsData, refsData, resultsData] = await Promise.all([
                    api.fetchClips(),
                    api.fetchReferences(),
                    api.fetchResults()
                ]);
                setClips(clipsData.clips || []);
                setReferences(refsData.references || []);
                setResults(resultsData.results || []);
            } catch (err) {
                toast.error("Failed to load assets");
            } finally {
                setLoading(false);
            }
        };
        fetchAllAssets();
    }, []);

    // Selection logic
    useEffect(() => {
        const filename = searchParams.get("filename");
        const type = searchParams.get("type") as ViewMode | null;

        if (filename && type && (references.length > 0 || results.length > 0 || clips.length > 0)) {
            let item: AssetItem | undefined;
            if (type === "results") item = results.find(r => r.filename === filename);
            else if (type === "references") item = references.find(r => r.filename === filename);
            else if (type === "clips") item = clips.find(c => c.filename === filename);

            if (item) {
                setSelectedItem(item);
                setViewMode(type);
            }
        } else if (results.length > 0 && !selectedItem) {
            setSelectedItem(results[0]);
        }
    }, [searchParams, results, references, clips, selectedItem]);

    // Intelligence Fetch
    useEffect(() => {
        if (!selectedItem) return;
        const fetchIntel = async () => {
            try {
                const key = viewMode === "clips" ? (selectedItem as Clip).clip_hash || selectedItem.filename : selectedItem.filename;
                const data = await api.fetchIntelligence(viewMode, key);
                setIntelligence(data as IntelligenceViewModel);
            } catch (_err) {
                setIntelligence(null);
            }
        };
        fetchIntel();
    }, [selectedItem, viewMode]);

    // Filter key decisions based on intelligence criteria
    const displayDecisions = useMemo(() => {
        const all = intelligence?.vault_report?.decision_stream || [];
        const key = intelligence?.vault_report?.key_decision_stream || [];
        if (showAllDecisions) return all;
        return key.length ? key : all;
    }, [showAllDecisions, intelligence?.vault_report?.decision_stream, intelligence?.vault_report?.key_decision_stream]);

    const displayEdlDecisions = useMemo(() => {
        return (intelligence?.edl?.decisions || []) as EdlDecision[];
    }, [intelligence?.edl?.decisions]);
    const edlTimingMap = useMemo(() => {
        const map = new Map<number, { start: number; end: number }>();

        intelligence?.edl?.decisions?.forEach((d: EdlDecision) => {
            map.set(d.segment_id, {
                start: d.timeline_start,
                end: d.timeline_end
            });
        });

        return map;
    }, [intelligence?.edl?.decisions]);

    // Auto-scroll decision list - REMOVED for better UX
    // useEffect(() => {
    //     if (viewMode === "results" && intelligence?.vault_report?.decision_stream) {
    //         const activeIdx = intelligence.vault_report.decision_stream.findIndex((decision: any) => {
    //             const timing = edlTimingMap.get(decision.segment_id);
    //             return timing && currentTime >= timing.start && currentTime <= timing.end;
    //         });
    //         if (activeIdx !== -1 && decisionListRef.current) {
    //             const activeEl = decisionListRef.current.children[activeIdx] as HTMLElement;
    //             if (activeEl) {
    //                 activeEl.scrollIntoView({
    //                     behavior: "smooth",
    //                     block: "center"
    //                 });
    //             }
    //         }
    //     }
    // }, [currentTime, intelligence, viewMode, edlTimingMap]);

    const videoUrl = useMemo(() => {
        if (!selectedItem) return "";
        const withPath = selectedItem as AssetWithPath;
        let path = withPath.path || withPath.filepath || withPath.url || "";

        const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

        // v14.9 Demo Mode Support
        if (path.startsWith("/demo/") || process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
            const relPath = path.startsWith("/") ? path : `/${path}`;
            return `${relPath}?v=${Date.now()}`;
        }

        // Backend assets
        const fullPath = path.startsWith("/") ? path : `/${path}`;
        return `${API_BASE}${fullPath}?v=${Date.now()}`;
    }, [selectedItem]);

    const selectedKey = selectedItem?.filename ? `${viewMode}:${selectedItem.filename}` : "";
    const blueprintOverlay = (intelligence as any)?.blueprint?.text_overlay || "";
    const blueprintSource = (intelligence as any)?.blueprint?.contract?.source || "";
    const isPromptModeResult = Boolean((intelligence as any)?.blueprint?.text_prompt) || blueprintSource === "text_prompt";

    // Keep modal drafts aligned with current committed state when opening
    useEffect(() => {
        if (!isStylingOpen) return;
        setVaultCaptionDraft(vaultCaptionPreview);
        setVaultCaptionPositionDraft(vaultCaptionPosition);
        setVaultCaptionFontDraft(vaultCaptionFont);
        setVaultCaptionColorDraft(vaultCaptionColor);
        setVaultCaptionSizeDraft(vaultCaptionSize);
    }, [isStylingOpen, vaultCaptionPreview, vaultCaptionPosition, vaultCaptionFont, vaultCaptionColor, vaultCaptionSize]);

    // Load per-video preview state (avoid leaking caption across assets)
    useEffect(() => {
        if (!selectedKey) return;
        const saved = vaultTextStoreRef.current.get(selectedKey);
        if (saved) {
            setVaultCaptionPreview(saved.caption);
            setVaultCaptionPosition(saved.position);
            setVaultCaptionFont(saved.font || "cormorant");
            setVaultCaptionColor(saved.color || "#FFFFFF");
            setVaultCaptionSize(saved.fontSize || 22);
        } else {
            setVaultCaptionPreview("");
            setVaultCaptionPosition('center');
            setVaultCaptionFont("cormorant");
            setVaultCaptionColor("#FFFFFF");
            setVaultCaptionSize(22);
        }
    }, [selectedKey]);

    useEffect(() => {
        if (!selectedKey) return;
        if (vaultTextStoreRef.current.has(selectedKey)) return;
        if (!blueprintOverlay) return;
        setVaultCaptionPreview(blueprintOverlay);
    }, [selectedKey, blueprintOverlay]);

    const currentModeAssets = useMemo(() => {
        const assets = viewMode === "results" ? results : viewMode === "references" ? references : clips;
        if (!searchQuery.trim()) return assets;
        return assets.filter(a => a.filename.toLowerCase().includes(searchQuery.toLowerCase()));
    }, [viewMode, results, references, clips, searchQuery]);

    const cleanupReasoning = (text: string) => {
        if (!text) return "Optimized for visual flow.";
        return text
            .replace(/SERVING AS A STRATEGIC/g, 'Chosen as a')
            .replace(/SATISFIES THE NARRATIVE'S/g, 'Matches the')
            .replace(/HIGH-ENERGY DEMAND/g, 'energy')
            .replace(/PRIMARY EMOTIONAL CARRIER/g, 'main vibe')
            .toLowerCase();
    };

    const truncate = (text: string, maxLen: number) => {
        if (!text) return "";
        if (text.length <= maxLen) return text;
        return text.slice(0, maxLen).trimEnd() + "...";
    };

    if (loading) return (
        <div className="h-screen flex items-center justify-center bg-[#020306]">
            <div className="text-indigo-500 text-[10px] font-black uppercase tracking-[0.5em] animate-pulse">Syncing_Vault</div>
        </div>
    );

    return (
        <div className="min-h-screen bg-[#08090a] text-slate-100 flex flex-col overflow-hidden">

            {/* STAGE HEADER: Netflix-Deep Glass */}
            <header className="h-14 flex items-center justify-between px-12 bg-[#08090a]/80 backdrop-blur-2xl border-b border-white/[0.03] shrink-0 z-[100]">
                <div className="flex items-center gap-6">
                    <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
                        <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Live</span>
                    </div>
                </div>

                <div className="flex-1 max-w-lg mx-auto">
                    <div className="relative group">
                        <div className="absolute inset-0 bg-white/[0.03] backdrop-blur-3xl rounded-3xl border border-white/5 group-focus-within:border-indigo-500/20 group-focus-within:bg-white/[0.05] transition-all duration-700" />
                        <input
                            type="text"
                            placeholder="Search library..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="relative w-full bg-transparent py-2 pl-4 pr-4 text-[11px] font-normal text-white placeholder-slate-600 outline-none z-10"
                        />
                    </div>
                </div>

                <nav className="flex items-center bg-white/5 p-1 rounded-xl border border-white/10 shrink-0">
                    {(["results", "references", "clips"] as ViewMode[]).map(mode => (
                        <button
                            key={mode}
                            onClick={() => setViewMode(mode)}
                            className={cn(
                                "px-5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all",
                                viewMode === mode ? "text-white bg-indigo-600 shadow-lg shadow-indigo-600/20" : "text-slate-500 hover:text-slate-300"
                            )}
                        >
                            {mode}
                        </button>
                    ))}
                </nav>
            </header>

            {/* ASSET STRIP: Netflix-Style Content Cards */}
            <div className="h-48 border-b border-white/[0.03] bg-black/10 shrink-0 overflow-hidden relative">
                <div className="flex gap-6 overflow-x-auto p-6 custom-scrollbar-horizontal no-scrollbar h-full items-center px-12">
                    {currentModeAssets.map((item, idx) => {
                        const isSelected = selectedItem?.filename === item.filename;
                        return (
                            <div
                                key={idx}
                                onClick={() => setSelectedItem(item)}
                                className="shrink-0 w-64 group/item cursor-pointer"
                            >
                                <div
                                    className={cn(
                                        "relative w-full aspect-video rounded-xl overflow-hidden border transition-all duration-500 bg-[#0f1115] shadow-2xl",
                                        isSelected
                                            ? "border-indigo-500 ring-2 ring-indigo-500/40 scale-[1.05] z-10"
                                            : "border-white/5 opacity-90 hover:opacity-100 hover:scale-[1.02] hover:border-white/20"
                                    )}
                                >
                                    {item.thumbnail_url ? (
                                        <img
                                            src={item.thumbnail_url.startsWith("http") || item.thumbnail_url.startsWith("/demo/")
                                                ? item.thumbnail_url
                                                : `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${item.thumbnail_url.startsWith("/") ? item.thumbnail_url : `/${item.thumbnail_url}`}`}
                                            alt={item.filename}
                                            className="w-full h-full object-cover"
                                        />
                                    ) : (
                                        <div className="w-full h-full flex flex-col items-center justify-center bg-indigo-500/5 gap-2">
                                            <Film className="h-6 w-6 text-indigo-500/20" />
                                            <span className="text-[8px] font-black uppercase text-indigo-500/40">No Preview</span>
                                        </div>
                                    )}

                                    {/* Netflix-style Card Footer */}
                                    <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/90 to-transparent flex flex-col justify-end p-3 transform translate-y-2 group-hover/item:translate-y-0 transition-transform">
                                        <div className="flex items-center justify-between">
                                            <p className="text-[9px] font-black text-white uppercase tracking-wider truncate">{item.filename}</p>
                                            <div className="flex items-center gap-1.5">
                                                <div className="h-5 w-5 rounded bg-white/10 backdrop-blur-md flex items-center justify-center">
                                                    <Play className="h-2.5 w-2.5 text-white fill-white" />
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {isSelected && (
                                        <div className="absolute top-3 right-3 px-2 py-0.5 rounded bg-indigo-600 text-[7px] font-black uppercase tracking-tighter shadow-lg">Viewing</div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* WORKBENCH: Dense Two-Column Stage */}
            <main className="flex-1 flex overflow-hidden">
                <div className="flex-1 flex flex-col overflow-y-auto custom-scrollbar p-12">

                    <div className="max-w-[1500px] mx-auto w-full flex gap-10 items-start">

                        {/* LEFT: Video Stage (Increased height for cinematic feel) */}
                        <div className="flex-1 flex flex-col gap-6 min-w-0 -mt-4">
                            <div className={cn("relative mx-auto group transition-all duration-300", mobileView ? "w-[420px] max-w-[420px]" : "w-full max-w-[640px]")}>
                                <div className={cn("video-aura", isPlaying && "video-aura-active animate-pulse-vibrant")} />
                                <div className={cn("relative rounded-[2.5rem] overflow-hidden bg-black shadow-[0_0_50px_rgba(0,0,0,0.5)] border border-white/10 group-hover:border-indigo-500/30 transition-all duration-700", mobileView ? "w-[420px] h-[630px]" : "aspect-[15/14]")}>
                                    {selectedItem ? (
                                        <video
                                            ref={videoRef}
                                            src={videoUrl}
                                            onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime || 0)}
                                            onLoadedMetadata={() => setDuration(videoRef.current?.duration || 0)}
                                            onPlay={() => setIsPlaying(true)}
                                            onPause={() => setIsPlaying(false)}
                                            className="w-full h-full object-cover"
                                            controls
                                        />
                                    ) : (
                                        <div className="w-full h-full flex flex-col items-center justify-center opacity-20">
                                            <Play className="h-12 w-12 mb-4" />
                                            <p className="text-[10px] font-black uppercase tracking-widest">Select specimen</p>
                                        </div>
                                    )}

                                    {/* Vault-only overlays (non-destructive preview) */}
                                    {vaultCaptionPreview && (
                                        <div className="absolute inset-0 pointer-events-none">
                                            <div
                                                className={cn(
                                                    "absolute left-0 right-0 px-10 text-center",
                                                    (vaultCaptionPosition || "center") === "top" && "top-[8%]",
                                                    (vaultCaptionPosition || "center") === "center" && "top-1/2 -translate-y-1/2",
                                                    (vaultCaptionPosition || "center") === "bottom" && "bottom-[10%]"
                                                )}
                                                style={{
                                                    fontFamily: vaultCaptionFont === "cormorant" ? "'Cormorant Garamond', serif"
                                                        : vaultCaptionFont === "playfair" ? "'Playfair Display', serif"
                                                            : vaultCaptionFont === "dm-serif" ? "'DM Serif Display', serif"
                                                                : vaultCaptionFont === "lora" ? "'Lora', serif"
                                                                    : vaultCaptionFont === "bebas" ? "'Bebas Neue', sans-serif"
                                                                        : vaultCaptionFont === "montserrat" ? "'Montserrat', sans-serif"
                                                                            : "'Cormorant Garamond', serif",
                                                    fontWeight: 600,
                                                    color: vaultCaptionColor || "#FFFFFF",
                                                    textShadow: "0 2px 12px rgba(0,0,0,0.85)",
                                                }}
                                            >
                                                <div
                                                    className="animate-in fade-in duration-500 leading-tight"
                                                    style={{ fontSize: vaultCaptionSize }}
                                                >
                                                    {vaultCaptionPreview}
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Info & Secondary Controls */}
                            <div className={cn("mx-auto flex items-center justify-between px-4", mobileView ? "w-[420px] max-w-[420px]" : "w-full max-w-[640px]")}>
                                <div className="space-y-1">
                                    <div className="flex flex-col gap-1">
                                        <span className="text-2xl font-black text-white uppercase tracking-tighter italic drop-shadow-sm">{selectedItem?.filename.replace(/\.[^/.]+$/, "") || "UNTITLED"}</span>
                                    </div>
                                    <div className="flex items-center gap-5 opacity-50">
                                        <div className="flex items-center gap-2"><Clock className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">{duration.toFixed(1)}s</span></div>
                                        <div className="flex items-center gap-2"><Music className="h-3.5 w-3.5" /><span className="text-[10px] font-bold uppercase tracking-wider">{intelligence?.bpm || 128} BPM</span></div>
                                    </div>
                                    {(intelligence as any)?.blueprint?.text_overlay && (
                                        <div className="mt-2 text-[11px] text-white/40 font-medium italic">
                                            "{(intelligence as any).blueprint.text_overlay}"
                                        </div>
                                    )}
                                </div>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => setMobileView(!mobileView)}
                                        className={cn(
                                            "h-12 w-12 rounded-2xl border text-white flex items-center justify-center transition-all active:scale-95",
                                            mobileView ? "bg-indigo-500/20 border-indigo-500/40 hover:bg-indigo-500/30" : "bg-white/5 border-white/10 hover:bg-white/10"
                                        )}
                                        title={mobileView ? "Wide view" : "Mobile view"}
                                    >
                                        <Smartphone className="h-5 w-5" />
                                    </button>
                                    <button className="h-12 px-7 rounded-2xl bg-white text-black font-black text-[10px] uppercase tracking-widest hover:bg-indigo-500 hover:text-white transition-all shadow-xl active:scale-95">Refine Edit</button>
                                    <button className="h-12 w-12 rounded-2xl bg-white/5 border border-white/10 text-white flex items-center justify-center hover:bg-white/10 transition-all active:scale-95"><Share2 className="h-5 w-5" /></button>
                                    <button
                                        onClick={() => setIsStylingOpen(true)}
                                        disabled={viewMode !== "results" || isStylingLoading}
                                        className={cn(
                                            "h-12 w-12 rounded-2xl bg-white/5 border border-white/10 text-slate-500 flex items-center justify-center hover:bg-white/10 transition-all active:scale-95",
                                            (viewMode !== "results" || isStylingLoading) && "opacity-20 cursor-not-allowed"
                                        )}
                                    >
                                        <Palette className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* RIGHT COLUMN: DECISION STREAM */}
                        <div className="w-[420px] flex flex-col gap-6 shrink-0">

                            {/* DECISION STREAM: THE WHITEBOX */}
                            <div className="flex flex-col bg-gradient-to-b from-white/[0.02] to-transparent border border-white/[0.05] rounded-[2.5rem] overflow-hidden shadow-2xl" style={{ height: '630px' }}>
                                <div className="p-7 border-b border-white/[0.05] flex items-center justify-between bg-black/20 backdrop-blur-md">
                                    <div className="flex items-center gap-4">
                                        <div className="h-2 w-2 rounded-full bg-indigo-500 shadow-[0_0_10px_#6366f1]" />
                                        <h3 className="text-[11px] font-black text-white uppercase tracking-[0.4em]">Decision Stream</h3>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="px-3 py-1 rounded-lg bg-white/5 border border-white/10">
                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
                                                {showAllDecisions ? "All" : "Key"} {displayDecisions.length} / {intelligence?.edl?.decisions?.length || 0}
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => setShowAllDecisions(!showAllDecisions)}
                                            className={cn(
                                                "px-2 py-1 rounded-md transition-colors",
                                                showAllDecisions
                                                    ? "bg-white/10 border-white/20 hover:bg-white/15"
                                                    : "bg-indigo-500/15 border-indigo-500/30 hover:bg-indigo-500/25"
                                            )}
                                        >
                                            <span className={cn(
                                                "text-[7px] font-black uppercase tracking-widest",
                                                showAllDecisions ? "text-slate-400" : "text-indigo-400"
                                            )}>
                                                {showAllDecisions ? "All" : "Key"}
                                            </span>
                                        </button>
                                    </div>
                                </div>

                                <div ref={decisionListRef} className="flex-1 overflow-y-auto p-7 space-y-4 custom-scrollbar-thin">
                                    {!displayDecisions.length ? (
                                        <div className="h-full flex flex-col items-center justify-center opacity-20 text-center px-12">
                                            <Zap className="h-10 w-10 mb-6 text-indigo-500" />
                                            <p className="text-[11px] font-black uppercase tracking-[0.2em] leading-relaxed">Awaiting logic<br />Play to sync</p>
                                        </div>
                                    ) : (
                                        <>
                                            {/* Show filtered decisions with proper hierarchy */}
                                            {displayDecisions.map((decision: VaultDecision, idx: number) => {
                                                const timing = edlTimingMap.get(decision.segment_id);
                                                const isActive = timing && currentTime >= timing.start && currentTime <= timing.end;
                                                const isKeyDecision = !showAllDecisions; // Vault decisions are key decisions, EDL are all decisions

                                                return (
                                                    <div
                                                        key={idx}
                                                        onClick={() => {
                                                            if (timing && videoRef.current) {
                                                                videoRef.current.currentTime = timing.start;
                                                            }
                                                        }}
                                                        className={cn(
                                                            "transition-all duration-300 relative group/card cursor-pointer",
                                                            isKeyDecision ? (
                                                                "p-6 rounded-[1.25rem] bg-gradient-to-b from-white/[0.04] to-white/[0.015] border-[rgba(130,140,255,0.15)] shadow-[0_0_40px_rgba(120,130,255,0.08)] border-l-2 border-[rgba(59,130,246,0.6)]"
                                                            ) : (
                                                                "p-4 rounded-[1rem] bg-gradient-to-b from-white/[0.02] to-white/[0.01] border-white/[0.1] shadow-[0_0_20px_rgba(120,130,255,0.04)]"
                                                            ),
                                                            isActive
                                                                ? "scale-[1.05] z-20 border-2 border-indigo-400 shadow-[0_0_100px_rgba(99,102,241,0.4)] bg-gradient-to-b from-indigo-500/10 to-indigo-500/5 animate-pulse"
                                                                : isKeyDecision
                                                                    ? "opacity-90 hover:opacity-100 hover:-translate-y-0.5 hover:shadow-[0_0_60px_rgba(120,130,255,0.15)]"
                                                                    : "opacity-60 hover:opacity-80 hover:-translate-y-0.5"
                                                        )}
                                                    >
                                                        <div className="flex items-center justify-between mb-3">
                                                            <div className="flex items-center gap-3">
                                                                <span className={cn(
                                                                    "font-mono tracking-[0.12em]",
                                                                    isKeyDecision ? "text-[#8B90FF]" : "text-slate-400"
                                                                )}>
                                                                    SEGMENT {String(decision.segment_id).padStart(2, '0')}
                                                                </span>
                                                                {isActive && (
                                                                    <div className={cn(
                                                                        "h-1.5 w-1.5 rounded-full animate-pulse",
                                                                        isKeyDecision ? "bg-indigo-400 shadow-[0_0_10px_#818cf8]" : "bg-gray-400"
                                                                    )} />
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                {timing && (
                                                                    <span className="text-[10px] font-mono text-[rgba(180,190,255,0.7)]">
                                                                        {timing.start.toFixed(1)}s – {timing.end.toFixed(1)}s
                                                                    </span>
                                                                )}
                                                                {isKeyDecision && (
                                                                    <span className="px-2 py-0.5 rounded bg-indigo-500/20 border border-indigo-500/30">
                                                                        <span className="text-[6px] font-black text-indigo-300 uppercase tracking-widest">KEY DECISION</span>
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </div>

                                                        <div className="space-y-3">
                                                            {/* Vault decisions have full intelligence structure */}
                                                            {isKeyDecision && (
                                                                <>
                                                                    {/* Intent Line (largest) */}
                                                                    <div className="mb-2">
                                                                        <p className="text-[15px] font-medium text-white leading-[1.35]">
                                                                            <span className="text-[#9AA0FF] font-normal">I wanted </span>
                                                                            {decision.what_i_tried}
                                                                        </p>
                                                                    </div>

                                                                    {/* Decision Label + Explanation */}
                                                                    <div className="space-y-1">
                                                                        <p className="text-[10px] font-black text-[#6F74FF] uppercase tracking-[0.14em]">DECISION</p>
                                                                        <p className="text-[13px] text-[#D6D8FF] leading-relaxed">{decision.decision}</p>
                                                                    </div>

                                                                    {/* Counterfactual (if exists) */}
                                                                    {decision.what_if &&
                                                                        !decision.what_if.toLowerCase().includes('no stronger alternative') &&
                                                                        !decision.what_if.toLowerCase().includes('no viable upgrade') && (
                                                                            <div className="flex items-start gap-2">
                                                                                <span className="text-[rgba(180,190,255,0.55)] text-sm">→</span>
                                                                                <p className="text-[12px] text-[rgba(180,190,255,0.55)] italic leading-relaxed flex-1">
                                                                                    {decision.what_if}
                                                                                </p>
                                                                            </div>
                                                                        )}
                                                                </>
                                                            )}
                                                        </div>

                                                        {isActive && (
                                                            <div className="absolute bottom-0 left-0 h-1 bg-indigo-500 rounded-full transition-all duration-300" style={{ width: '100%' }} />
                                                        )}
                                                    </div>
                                                );
                                            })}

                                            {/* Show full EDL forensic view (always separate from Vault decision_stream) */}
                                            {showAllDecisions && displayEdlDecisions.map((edlDecision: EdlDecision, idx: number) => {
                                                const timing = { start: edlDecision.timeline_start, end: edlDecision.timeline_end };
                                                const isActive = currentTime >= timing.start && currentTime <= timing.end;


                                                return (
                                                    <div key={`all-${idx}`} className={cn(
                                                        "p-4 rounded-[1rem] border transition-all duration-300 relative group/card",
                                                        "bg-gradient-to-b from-white/[0.02] to-white/[0.01] border-white/[0.1]",
                                                        "shadow-[0_0_20px_rgba(120,130,255,0.04)]",
                                                        isActive
                                                            ? "scale-[1.02] z-10 border-indigo-400/50 shadow-[0_0_40px_rgba(99,102,241,0.2)]"
                                                            : "opacity-50 hover:opacity-70"
                                                    )}>
                                                        <div className="flex items-center justify-between mb-2">
                                                            <div className="flex items-center gap-3">
                                                                <span className="text-[10px] font-mono text-slate-400 tracking-widest">SEGMENT {String(edlDecision.segment_id).padStart(2, '0')}</span>
                                                                {isActive && <div className="h-1 w-1 rounded-full bg-indigo-400 animate-pulse" />}
                                                            </div>
                                                            <span className="text-[9px] text-[rgba(180,190,255,0.5)] font-mono">
                                                                {timing.start.toFixed(1)}s - {timing.end.toFixed(1)}s
                                                            </span>
                                                        </div>
                                                        <div className="space-y-2">
                                                            <p className="text-[11px] text-slate-300 leading-relaxed">
                                                                {edlDecision.clip_path?.split(/[\\/]/).pop()}
                                                            </p>
                                                            <p className="text-[10px] text-slate-500 leading-relaxed">
                                                                {cleanupReasoning(edlDecision.reasoning || "")}
                                                            </p>
                                                        </div>
                                                        {isActive && (
                                                            <div className="absolute bottom-0 left-0 h-0.5 bg-indigo-400 rounded-full transition-all duration-300" style={{ width: '100%' }} />
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>

                    </div>

                    {/* LOWER HALF: Two-column Intelligence Grid */}
                    <div className="max-w-[1500px] mx-auto w-full mt-2 grid grid-cols-[60%_40%] gap-6">

                        {/* LEFT COLUMN: Intelligence Stack */}
                        <div className="space-y-4">

                            {/* 1. ADVISOR DIAGNOSIS (Expanded by default) */}
                            <div className="rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.02] overflow-hidden shadow-xl max-w-[700px]">
                                <button
                                    onClick={() => setAdvisorExpanded(!advisorExpanded)}
                                    className="w-full px-5 py-4 flex items-center justify-between hover:bg-white/[0.02] transition-all"
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="h-8 w-8 rounded-xl bg-indigo-500/20 flex items-center justify-center text-indigo-400 border border-indigo-500/30 shadow-[0_0_20px_rgba(99,102,241,0.2)]">
                                            <Compass className="h-4 w-4" />
                                        </div>
                                        <div className="text-left">
                                            <h3 className="text-[13px] font-black text-white uppercase tracking-[0.25em]">Advisor Diagnosis</h3>
                                            <p className="text-[11px] font-bold text-indigo-400 uppercase tracking-widest mt-0.5">Executive Verdict</p>
                                        </div>
                                    </div>
                                    {advisorExpanded ? <ChevronUp className="h-4 w-4 text-indigo-400" /> : <ChevronDown className="h-4 w-4 text-indigo-400" />}
                                </button>

                                {advisorExpanded && (
                                    <div className="px-5 pb-5 pt-0 space-y-3 animate-in slide-in-from-top-2">
                                        {(intelligence?.vault_report?.executive_summary || []).length > 0 && (
                                            <div className="p-4 rounded-2xl bg-black/20 border border-white/5">
                                                <p className="text-[12px] font-black text-indigo-400 uppercase tracking-widest mb-2">Executive Summary</p>
                                                <div className="space-y-2">
                                                    {(intelligence?.vault_report?.executive_summary || []).slice(0, 6).map((item: string, i: number) => (
                                                        <div key={i} className="flex items-start gap-2">
                                                            <span className="text-indigo-400/60 mt-[2px]">•</span>
                                                            <p className="text-[14px] text-slate-300 leading-relaxed">{item}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        <p className="text-[15px] font-semibold text-white leading-relaxed">
                                            {intelligence?.vault_report?.advisor?.hero || "Analyzing edit performance..."}
                                        </p>
                                        <div className="space-y-2">
                                            <p className="text-[13px] text-slate-400 leading-relaxed">
                                                {advisorShowMore
                                                    ? (intelligence?.vault_report?.advisor?.body || "Detailed analysis pending...")
                                                    : truncate(intelligence?.vault_report?.advisor?.body || "Detailed analysis pending...", 240)
                                                }
                                            </p>
                                            {(intelligence?.vault_report?.advisor?.body || "").length > 260 && (
                                                <button
                                                    onClick={() => setAdvisorShowMore(!advisorShowMore)}
                                                    className="text-[10px] font-black text-indigo-400/80 uppercase tracking-widest hover:text-indigo-300 transition-colors"
                                                >
                                                    {advisorShowMore ? "Show Less" : "Show More"}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* 2. FRICTION TIMELINE (Collapsed by default) */}
                            <div className="rounded-3xl border border-amber-500/10 bg-amber-500/[0.01] overflow-hidden">
                                <button
                                    onClick={() => setFrictionExpanded(!frictionExpanded)}
                                    className="w-full p-6 flex items-center justify-between hover:bg-white/[0.02] transition-all"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-400 border border-amber-500/20">
                                            <BarChart3 className="h-5 w-5" />
                                        </div>
                                        <div className="text-left">
                                            <h3 className="text-[14px] font-black text-white uppercase tracking-[0.25em]">Friction Timeline</h3>
                                            <p className="text-[12px] font-bold text-amber-500/60 uppercase tracking-widest mt-0.5">Temporal Self-Awareness</p>
                                        </div>
                                    </div>
                                    {frictionExpanded ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                                </button>

                                {frictionExpanded && (
                                    <div className="p-6 pt-0 space-y-3 animate-in slide-in-from-top-2">
                                        {intelligence?.vault_report?.friction_log?.map((entry: string, i: number) => (
                                            <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-black/20 border border-white/5">
                                                <span className="text-[11px] font-black text-amber-500/80 uppercase tracking-wider shrink-0">
                                                    {i === 0
                                                        ? "START"
                                                        : i === ((intelligence?.vault_report?.friction_log || []).length - 1)
                                                            ? "END"
                                                            : "MID"}
                                                </span>
                                                <p className="text-[14px] text-slate-400 leading-relaxed">{entry}</p>
                                            </div>
                                        )) || <p className="text-[11px] text-slate-500 italic">No friction entries recorded</p>}
                                    </div>
                                )}
                            </div>

                            {/* 3. NEXT STEPS (Collapsed by default) */}
                            <div className="rounded-3xl border border-cyan-500/10 bg-cyan-500/[0.01] overflow-hidden">
                                <button
                                    onClick={() => setNextStepsExpanded(!nextStepsExpanded)}
                                    className="w-full p-6 flex items-center justify-between hover:bg-white/[0.02] transition-all"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-xl bg-cyan-500/10 flex items-center justify-center text-cyan-400 border border-cyan-500/20">
                                            <Footprints className="h-5 w-5" />
                                        </div>
                                        <div className="text-left">
                                            <h3 className="text-[14px] font-black text-white uppercase tracking-[0.25em]">Recommended Next Steps</h3>
                                            <p className="text-[11px] font-bold text-cyan-500/60 uppercase tracking-widest mt-0.5">Turn Critique Into Action</p>
                                        </div>
                                    </div>
                                    {nextStepsExpanded ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                                </button>

                                {nextStepsExpanded && (
                                    <div className="p-6 pt-0 animate-in slide-in-from-top-2">
                                        <div className="space-y-2">
                                            {intelligence?.vault_report?.next_steps?.map((step: string, i: number) => (
                                                <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-black/20 border border-white/5">
                                                    <span className="text-[12px] font-black text-cyan-400/80 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                                                    <p className="text-[14px] text-slate-400 leading-relaxed">{step}</p>
                                                </div>
                                            )) || <p className="text-[11px] text-slate-500 italic">No next steps defined</p>}
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="rounded-3xl border border-violet-500/10 bg-violet-500/[0.01] overflow-hidden">
                                <button
                                    onClick={() => setIntelExpanded(!intelExpanded)}
                                    className="w-full p-6 flex items-center justify-between hover:bg-white/[0.02] transition-all"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-xl bg-violet-500/10 flex items-center justify-center text-violet-300 border border-violet-500/20">
                                            <Sparkles className="h-5 w-5" />
                                        </div>
                                        <div className="text-left">
                                            <h3 className="text-[14px] font-black text-white uppercase tracking-[0.25em]">Clip Suggestions</h3>
                                            <p className="text-[10px] font-bold text-violet-500/60 uppercase tracking-widest mt-0.5">Library Curation Guidance</p>
                                        </div>
                                    </div>
                                    {intelExpanded ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                                </button>
                                {intelExpanded && (
                                    <div className="p-6 pt-0 animate-in slide-in-from-top-2">
                                        <div className="space-y-2">
                                            {intelligence?.vault_report?.clip_suggestions?.map((s: string, i: number) => (
                                                <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-black/20 border border-white/5">
                                                    <span className="text-[11px] font-black text-violet-300/80 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                                                    <p className="text-[14px] text-slate-400 leading-relaxed">{s}</p>
                                                </div>
                                            )) || <p className="text-[13px] text-slate-500 italic">No clip suggestions generated</p>}
                                        </div>
                                        <button className="mt-4 w-full h-10 rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-300 font-black text-[12px] uppercase tracking-widest hover:bg-violet-500/20 transition-all">
                                            Retry with Better Clips
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* RIGHT COLUMN: System & Context + Post-Mortem */}
                        <div className="space-y-6">

                            {/* POST-MORTEM (Expanded by default) */}
                            <div className="rounded-3xl border border-white/10 bg-white/[0.01] overflow-hidden">
                                <button
                                    onClick={() => setPostMortemExpanded(!postMortemExpanded)}
                                    className="w-full p-6 flex items-center justify-between hover:bg-white/[0.02] transition-all"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400 border border-emerald-500/20">
                                            <Microscope className="h-5 w-5" />
                                        </div>
                                        <div className="text-left">
                                            <h3 className="text-[12px] font-black text-white uppercase tracking-[0.25em]">Post-Mortem</h3>
                                            <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest mt-0.5">Explicit Accountability</p>
                                        </div>
                                    </div>
                                    {postMortemExpanded ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                                </button>

                                {postMortemExpanded && (
                                    <div className="p-6 pt-0 space-y-5 animate-in slide-in-from-top-2">
                                        {/* WHAT WORKED */}
                                        <div className="p-5 rounded-2xl bg-emerald-500/[0.03] border border-emerald-500/10">
                                            <p className="text-[10px] font-black text-emerald-400 uppercase tracking-widest mb-3">What Worked</p>
                                            <p className="text-[14px] text-slate-300 leading-relaxed">
                                                {intelligence?.vault_report?.post_mortem?.worked || "No post-mortem analysis available"}
                                            </p>
                                        </div>

                                        {/* WHAT DIDN'T */}
                                        <div className="p-5 rounded-2xl bg-red-500/[0.03] border border-red-500/10">
                                            <p className="text-[10px] font-black text-red-400 uppercase tracking-widest mb-3">What Didn&apos;t</p>
                                            <p className="text-[14px] text-slate-300 leading-relaxed">
                                                {intelligence?.vault_report?.post_mortem?.didnt || "No critique recorded"}
                                            </p>
                                        </div>

                                        {/* RESPONSIBILITY */}
                                        <div className="flex items-center gap-3 pt-2">
                                            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Responsibility:</span>
                                            <div className="flex gap-2">
                                                <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[9px] font-bold text-indigo-400 uppercase">
                                                    Vibe: {intelligence?.vault_report?.post_mortem?.responsibility?.vibe || "System"}
                                                </span>
                                                <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[9px] font-bold text-indigo-400 uppercase">
                                                    Emotion: {intelligence?.vault_report?.post_mortem?.responsibility?.emotion || "System"}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* TECHNICAL DISCIPLINE (Collapsed by default) */}
                            <div className="rounded-3xl border border-slate-500/10 bg-slate-500/[0.01] overflow-hidden">
                                <button
                                    onClick={() => setTechnicalExpanded(!technicalExpanded)}
                                    className="w-full p-6 flex items-center justify-between hover:bg-white/[0.02] transition-all"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="h-10 w-10 rounded-xl bg-slate-500/10 flex items-center justify-center text-slate-400 border border-slate-500/20">
                                            <Code2 className="h-5 w-5" />
                                        </div>
                                        <div className="text-left">
                                            <h3 className="text-[12px] font-black text-white uppercase tracking-[0.25em]">Technical Discipline</h3>
                                            <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest mt-0.5">Implementation Depth</p>
                                        </div>
                                    </div>
                                    {technicalExpanded ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                                </button>

                                {technicalExpanded && (
                                    <div className="p-6 pt-0 animate-in slide-in-from-top-2">
                                        <div className="space-y-2">
                                            {intelligence?.vault_report?.technical?.map((item: string, i: number) => (
                                                <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-black/20">
                                                    <span className="text-slate-600 mt-1">•</span>
                                                    <p className="text-[11px] font-mono text-slate-400 leading-relaxed">{item}</p>
                                                </div>
                                            )) || <p className="text-[11px] text-slate-500 italic">No technical notes</p>}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                </div>
            </main>

            <StylingModal
                key={`${selectedItem?.filename || "none"}:${(intelligence?.style_config && JSON.stringify(intelligence.style_config).length) || 0}`}
                isOpen={isStylingOpen}
                onClose={() => {
                    setIsStylingOpen(false);
                    setVaultCaptionDraft("");
                    setVaultCaptionPositionDraft('center');
                    setVaultCaptionFontDraft("cormorant");
                    setVaultCaptionColorDraft("#FFFFFF");
                    setVaultCaptionSizeDraft(22);
                }}
                initialCaption={vaultCaptionDraft}
                initialPosition={vaultCaptionPositionDraft}
                initialFont={vaultCaptionFontDraft}
                initialColor={vaultCaptionColorDraft}
                initialFontSize={vaultCaptionSizeDraft}
                onApply={async (payload) => {
                    setIsStylingLoading(true);
                    try {
                        if (selectedKey) {
                            vaultTextStoreRef.current.set(selectedKey, payload);
                            saveVaultVisualStore(vaultTextStoreRef.current);
                        }
                        setVaultCaptionPreview(payload.caption);
                        setVaultCaptionPosition(payload.position);
                        setVaultCaptionFont(payload.font);
                        setVaultCaptionColor(payload.color);
                        setVaultCaptionSize(payload.fontSize);
                        setIsStylingOpen(false);
                        setVaultCaptionDraft("");
                        setVaultCaptionPositionDraft('center');
                        setVaultCaptionFontDraft("cormorant");
                        setVaultCaptionColorDraft("#FFFFFF");
                        setVaultCaptionSizeDraft(22);
                    } finally {
                        setIsStylingLoading(false);
                    }
                }}
            />
        </div>
    );
}