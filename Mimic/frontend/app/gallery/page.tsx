"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/card";
import {
    Trash2,
    Plus,
    Activity,
    Database,
    Zap,
    Layers,
    History,
    Eye,
    X,
    Pencil,
    Check
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, resolveAssetUrl } from "@/lib/api";
import type { Clip, Reference, Result } from "@/lib/types";

type AssetItem = Clip | Reference | Result;

type ClipLike = Clip & { session_id?: string };

export default function LibraryPage() {
    const router = useRouter();
    const [clips, setClips] = useState<Clip[]>([]);
    const [references, setReferences] = useState<Reference[]>([]);
    const [results, setResults] = useState<Result[]>([]);
    const [allItems, setAllItems] = useState<AssetItem[]>([]);
    const [recentItems, setRecentItems] = useState<AssetItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);
    const [visibleCount, setVisibleCount] = useState(36);
    const scrollRef = useRef<HTMLDivElement>(null);
    const [renamingItem, setRenamingItem] = useState<AssetItem | null>(null);
    const [newName, setNewName] = useState("");

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
        } catch {
            toast.error("Failed to load assets");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchAllAssets(); }, []);

    useEffect(() => {
        let items: AssetItem[] = [];
        if (selectedCategory === null) items = [...clips, ...references, ...results];
        else if (selectedCategory === "raw_samples") items = [...clips];
        else if (selectedCategory === "references") items = [...references];
        else if (selectedCategory === "synthesis_output") items = [...results];

        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            items = items.filter(item => {
                const nameMatch = item.filename.toLowerCase().includes(q);
                // Smart Search: Check AI metadata if it exists
                const vibesMatch = (item as Clip).vibes?.some(v => v.toLowerCase().includes(q));
                const subjectsMatch = (item as Clip).subjects?.some(s => s.toLowerCase().includes(q));
                const descMatch = (item as Clip).description && String((item as Clip).description).toLowerCase().includes(q);

                return nameMatch || vibesMatch || subjectsMatch || descMatch;
            });
        }

        const sorted = items.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        setAllItems(sorted);
        setRecentItems(sorted.slice(0, 8)); // First 8 for recent section
    }, [searchQuery, clips, references, results, selectedCategory]);

    useEffect(() => {
        setVisibleCount(36);
    }, [searchQuery, selectedCategory]);

    const deleteItem = async (item: AssetItem) => {
        const type = getItemType(item);
        if (type === "Reference") {
            toast.error("Reference deletion is not available yet");
            return;
        }
        if (!confirm(`Delete ${item.filename}?`)) return;
        try {
            if (type === "Synthesis Output") {
                await api.deleteResult(item.filename);
            } else {
                await api.deleteClip(getSessionId(item), item.filename);
            }
            fetchAllAssets();
            toast.success("File deleted");
        } catch {
            toast.error("Delete failed");
        }
    };

    const handleRename = async () => {
        if (!renamingItem || !newName.trim()) return;
        try {
            const type = getItemType(renamingItem) === 'Raw Sample' ? 'clips' : getItemType(renamingItem) === 'Synthesis Output' ? 'results' : 'references';
            await api.renameFile(type, renamingItem.filename, newName);
            toast.success("File renamed successfully");
            setRenamingItem(null);
            setNewName("");
            fetchAllAssets();
        } catch {
            toast.error("Rename failed");
        }
    };

    const getItemType = (item: AssetItem): "Raw Sample" | "Reference" | "Synthesis Output" => {
        if ("session_id" in item) return "Raw Sample";
        if (results.includes(item as Result)) return "Synthesis Output";
        return "Reference";
    };

    const getItemPath = (item: AssetItem): string => {
        return item.path || "";
    };

    const getSessionId = (item: AssetItem): string => {
        return (item as ClipLike).session_id || "samples";
    };

    const handleItemClick = (item: AssetItem) => {
        const type = getItemType(item) === 'Raw Sample' ? 'clips' : getItemType(item) === 'Synthesis Output' ? 'results' : 'references';
        router.push(`/vault?filename=${encodeURIComponent(item.filename)}&type=${type}`);
    };

    const handleDownload = async (item: AssetItem) => {
        const path = getItemPath(item);
        try {
            const response = await fetch(resolveAssetUrl(path));
            if (!response.ok) throw new Error("Download failed");
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = item.filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            toast.success("Download started");
        } catch {
            toast.error("Download failed");
        }
    };

    const renderCard = (item: AssetItem, idx: number) => {
        const itemId = "session_id" in item ? `${item.session_id}-${item.filename}` : item.filename;
        const type = getItemType(item);
        const path = getItemPath(item);
        const vibes = ["Cinematic", "Dynamic", "Tech", "Nostalgic", "Fast-Cuts", "Organic"];
        const randomVibe = vibes[idx % vibes.length];

        return (
            <Card
                key={`${itemId}-${idx}`}
                className="group relative bg-[#0b0d14]/40 border border-white/5 rounded-lg overflow-hidden transition-all duration-300 hover:scale-[1.02] hover:border-cyan-500/30 glow-hover flex flex-col h-full"
            >
                {/* Vibe Tag - Pops up on hover */}
                <div className="absolute top-2 right-2 z-20 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-2 group-hover:translate-y-0">
                    <div className="px-2 py-0.5 rounded-full bg-pink-500 text-[9px] font-black text-white uppercase tracking-tighter glow-pink shadow-lg flex items-center gap-1 animate-bounce-subtle">
                        <Zap className="h-2 w-2" />
                        {randomVibe}
                    </div>
                </div>

                <div className="w-full aspect-video bg-black relative overflow-hidden">
                    <video
                        src={resolveAssetUrl(path)}
                        poster={item.thumbnail_url
                            ? resolveAssetUrl(item.thumbnail_url)
                            : undefined}
                        className="w-full h-full object-cover opacity-60 group-hover:opacity-90 transition-opacity duration-300"
                        muted
                        preload="none"
                        onMouseOver={(e) => e.currentTarget.play().catch(() => { })}
                        onMouseOut={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }}
                    />
                    <div className="absolute top-2 left-2 z-10">
                        <div className={cn(
                            "px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-widest backdrop-blur-md border",
                            type === 'Raw Sample' ? 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20 glow-cyan' :
                                type === 'Reference' ? 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20' :
                                    'text-purple-400 bg-purple-500/10 border-purple-500/20 glow-purple'
                        )}>
                            {type}
                        </div>
                    </div>
                    {/* Glass Overlay on Hover */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                </div>

                <div className="p-2.5 space-y-2.5 flex-1 flex flex-col">
                    <div className="flex-1 min-w-0">
                        {renamingItem === item ? (
                            <div className="flex items-center gap-1.5 mb-1">
                                <input
                                    type="text"
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleRename()}
                                    className="flex-1 h-6 bg-white/10 border border-white/20 rounded px-2 text-[10px] text-white outline-none focus:border-indigo-500"
                                    autoFocus
                                />
                                <button onClick={handleRename} aria-label="Save filename" className="h-6 w-6 rounded bg-emerald-500/20 text-emerald-400 flex items-center justify-center hover:bg-emerald-500 hover:text-white transition-all"><Check className="h-3 w-3" /></button>
                                <button onClick={() => setRenamingItem(null)} aria-label="Cancel rename" className="h-6 w-6 rounded bg-white/5 text-slate-400 flex items-center justify-center hover:bg-white/10 transition-all"><X className="h-3 w-3" /></button>
                            </div>
                        ) : (
                            <div className="flex items-center justify-between group/title mb-1">
                                <h3 className="text-xs font-bold text-white/90 truncate leading-tight">{item.filename}</h3>
                                <button
                                    onClick={() => { setRenamingItem(item); setNewName(item.filename); }}
                                    aria-label={`Rename ${item.filename}`}
                                    className="opacity-0 group-hover/title:opacity-100 p-1 text-slate-500 hover:text-white transition-all"
                                >
                                    <Pencil className="h-3 w-3" />
                                </button>
                            </div>
                        )}
                        <div className="flex items-center gap-2 text-[10px] text-slate-500 font-medium">
                            <span className="font-mono text-purple-400/80">{(item.size / (1024 * 1024)).toFixed(1)}MB</span>
                            <span className="opacity-30">•</span>
                            <span className="uppercase tracking-tighter">{new Date(item.created_at * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
                        </div>
                    </div>

                    {/* Action Buttons - More Vibrant */}
                    <div className="flex gap-1.5">
                        <button
                            onClick={() => handleItemClick(item)}
                            className="flex-1 flex items-center justify-center gap-1.5 h-8 bg-indigo-600/90 hover:bg-indigo-500 text-white rounded text-[10px] font-bold uppercase tracking-wider transition-all"
                        >
                            <Eye className="h-3 w-3" />
                            <span>View</span>
                        </button>
                        <button
                            onClick={(e) => { e.stopPropagation(); handleDownload(item); }}
                            className="w-8 h-8 flex items-center justify-center bg-white/5 hover:bg-cyan-500/20 text-slate-400 hover:text-cyan-400 rounded transition-all group/btn border border-white/5"
                            title="Download"
                        >
                            <svg className="h-3 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                        </button>
                        {type !== "Reference" && (
                            <button
                                onClick={(e) => { e.stopPropagation(); deleteItem(item); }}
                                className="w-8 h-8 flex items-center justify-center bg-white/5 hover:bg-red-500/20 text-slate-600 hover:text-red-400 rounded transition-all border border-white/5"
                                title="Delete"
                            >
                                <Trash2 className="h-3 w-3" />
                            </button>
                        )}
                    </div>
                </div>
            </Card>
        );
    };

    return (
        <div className="min-h-[calc(100vh-80px)] flex flex-col mx-auto max-w-7xl px-4 sm:px-6 pt-6 pb-12">
            {/* Header - Compact */}
            <div className="flex flex-col gap-6 mb-8">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-6">
                    <div className="space-y-2 min-w-0">
                        <div className="flex items-center gap-3">
                            <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center">
                                <Database className="h-4 w-4 text-white" />
                            </div>
                            <h1 className="text-2xl font-bold text-white">Library</h1>
                        </div>
                        <p className="text-xs text-slate-500 max-w-xl">Compressed asset index with real-time access to synchronized data</p>
                    </div>

                    <div className="flex gap-3 self-start sm:self-auto">
                        <div className="px-4 py-2 rounded-lg bg-white/[0.03] border border-white/10 flex items-center gap-3">
                            <div className="text-right">
                                <p className="text-2xs font-medium text-slate-500 uppercase">Total Assets</p>
                                <p className="text-sm font-bold text-white">{allItems.length}</p>
                            </div>
                            <Activity className="h-4 w-4 text-indigo-400" />
                        </div>
                    </div>
                </div>

                {/* Search & Filter - Compact */}
                <div className="flex gap-3 items-center">
                    <div className="relative flex-1">
                        <input
                            type="text"
                            placeholder="Search files..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full h-10 bg-white/[0.03] border border-white/10 rounded-lg pl-4 pr-4 text-sm text-white placeholder:text-slate-600 outline-none focus:border-indigo-500/40 transition-all"
                        />
                    </div>

                    <div className="relative shrink-0">
                        <button
                            onClick={() => setIsFilterModalOpen(true)}
                            className="h-10 px-4 sm:px-6 bg-indigo-500/20 hover:bg-indigo-500 border border-indigo-500/30 text-indigo-400 hover:text-white rounded-lg text-xs font-black uppercase tracking-widest transition-all flex items-center gap-2 sm:gap-3 group"
                        >
                            <Plus className="h-4 w-4 transition-transform group-hover:rotate-90" />
                            <span>Filters</span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Filter Modal */}
            {isFilterModalOpen && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-300">
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={() => setIsFilterModalOpen(false)} />
                    <div className="relative w-full max-w-[500px] max-h-[calc(100vh-1.5rem)] overflow-y-auto custom-scrollbar bg-[#0b0d14]/90 backdrop-blur-2xl rounded-2xl sm:rounded-3xl p-5 sm:p-8 border border-white/10 shadow-[0_40px_100px_rgba(0,0,0,0.8)]">
                        <div className="flex items-center justify-between gap-3 mb-6 sm:mb-8 pb-4 border-b border-white/5 relative z-10">
                            <div className="flex items-center gap-3">
                                <Plus className="h-5 w-5 text-indigo-400" />
                                <h3 className="text-lg sm:text-xl font-black text-white uppercase tracking-tighter">Advanced Filters</h3>
                            </div>
                            <button onClick={() => setIsFilterModalOpen(false)} className="h-10 w-10 rounded-full bg-white/5 flex items-center justify-center text-slate-400 hover:text-white transition-all border border-white/5">
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        <div className="space-y-8 relative z-10">
                            <div className="space-y-4">
                                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Select Sources</p>
                                <div className="grid grid-cols-1 min-[380px]:grid-cols-2 gap-3">
                                    {[
                                        { id: null, label: 'All Sources' },
                                        { id: 'raw_samples', label: 'Raw Samples' },
                                        { id: 'references', label: 'References' },
                                        { id: 'synthesis_output', label: 'Synthesis' }
                                    ].map((cat) => (
                                        <button
                                            key={String(cat.id)}
                                            onClick={() => setSelectedCategory(cat.id)}
                                            className={cn(
                                                "h-12 px-4 rounded-xl border text-[10px] font-bold uppercase tracking-widest transition-all text-left flex items-center gap-3",
                                                selectedCategory === cat.id
                                                    ? "bg-indigo-500 border-indigo-400 text-white"
                                                    : "bg-white/5 border-white/5 text-slate-400 hover:border-white/20"
                                            )}
                                        >
                                            <div className={cn("h-1.5 w-1.5 rounded-full", selectedCategory === cat.id ? "bg-white" : "bg-slate-700")} />
                                            {cat.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="space-y-4">
                                <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Energy & Content</p>
                                <div className="grid grid-cols-1 min-[380px]:grid-cols-2 gap-3">
                                    {['High Energy', 'Cinematic', 'Fast Cuts', 'Slow Motion', 'Color Graded', 'Raw'].map((tag) => (
                                        <label key={tag} className="flex items-center gap-3 p-3.5 rounded-xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.08] transition-all cursor-pointer group">
                                            <div className="h-4 w-4 rounded border border-white/20 flex items-center justify-center group-hover:border-indigo-400 transition-all">
                                                <div className="h-2 w-2 rounded-sm bg-indigo-500 opacity-0 group-hover:opacity-40" />
                                            </div>
                                            <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">{tag}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <button
                            onClick={() => setIsFilterModalOpen(false)}
                            className="w-full mt-8 sm:mt-10 h-12 sm:h-14 bg-indigo-500 text-white rounded-2xl font-black text-xs uppercase tracking-[0.2em] shadow-xl"
                        >
                            Apply Parameters
                        </button>
                    </div>
                </div>
            )}

            {/* Recently Uploaded Section - Horizontal Scroll */}
            <section className="mb-12">
                <h2 className="text-[12px] font-black text-white uppercase tracking-[0.3em] flex items-center gap-3 mb-6">
                    <History className="h-4 w-4 text-pink-500" />
                    Recently Uploaded
                </h2>
                <div
                    ref={scrollRef}
                    className="flex gap-4 overflow-x-auto pb-6 -mx-2 px-2 custom-scrollbar-horizontal snap-x"
                >
                    {loading ? (
                        <div className="flex gap-4">
                            {[1, 2, 3, 4, 5].map(i => <div key={i} className="min-w-[280px] h-[180px] bg-white/5 rounded-2xl animate-pulse" />)}
                        </div>
                    ) : recentItems.length === 0 ? (
                        <div className="w-full h-32 flex items-center justify-center border border-dashed border-white/5 rounded-3xl text-slate-600 text-xs font-bold uppercase tracking-widest bg-white/[0.01]">
                            No recent records detected
                        </div>
                    ) : (
                        recentItems.slice(0, 5).map((item, idx) => (
                            <div key={idx} className="min-w-[min(300px,calc(100vw-3rem))] snap-start">
                                {renderCard(item, idx)}
                            </div>
                        ))
                    )}
                </div>
            </section>

            {/* All Files Section */}
            <section className="flex-1">
                <h2 className="text-lg font-bold text-white mb-4 uppercase tracking-tight flex items-center gap-2">
                    <Layers className="h-4 w-4 text-cyan-500" />
                    All Files
                </h2>
                <div className="pb-8">
                    {loading ? (
                        <div className="flex items-center justify-center h-64 text-sm text-slate-500">Loading...</div>
                    ) : allItems.length === 0 ? (
                        <div className="flex items-center justify-center h-64 border border-dashed border-white/10 rounded-lg text-sm text-slate-500">
                            No files found
                        </div>
                    ) : (
                        <>
                            <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                                {allItems.slice(0, visibleCount).map((item, idx) => renderCard(item, idx))}
                            </div>
                            {visibleCount < allItems.length && (
                                <div className="mt-8 flex justify-center">
                                    <button
                                        onClick={() => setVisibleCount(count => count + 36)}
                                        className="h-11 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-8 text-[10px] font-black uppercase tracking-[0.2em] text-indigo-300 transition-colors hover:bg-indigo-500/20 hover:text-white"
                                    >
                                        Load more ({allItems.length - visibleCount} remaining)
                                    </button>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </section>
        </div>
    );
}
