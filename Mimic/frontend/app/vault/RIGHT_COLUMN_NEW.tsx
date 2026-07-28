"use client";

import { TrendingUp, BrainCircuit, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

type SelectedItemLike = {
    filename: string;
};

type RightColumnNewProps = {
    currentTime: number;
    viewMode: string;
    selectedItem?: SelectedItemLike | null;
    getVideoUrl: (item: SelectedItemLike) => string;
};

export default function RightColumnNew({ currentTime, viewMode, selectedItem, getVideoUrl }: RightColumnNewProps) {
    return (
        <aside className="space-y-6 overflow-y-auto custom-scrollbar pr-2 max-h-[88vh]">
    {/* EDITORIAL DECISIONS - Top Priority */}
    <div className="space-y-4">
        <div className="flex items-center gap-3 px-2">
            <div className="h-1 w-8 bg-gradient-to-r from-cyan-500 to-transparent rounded-full" />
            <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.4em]">Editorial Decisions</h3>
        </div>

        {/* SEG_15: Peak Moment */}
        <div className={cn(
            "bg-[#0a0c14]/60 border rounded-2xl p-6 transition-all duration-700 backdrop-blur-sm",
            (currentTime >= 8.2 && currentTime <= 12.5) || viewMode !== "results"
                ? "border-[#ff007f]/40 shadow-[0_0_30px_rgba(255,0,127,0.15)] scale-[1.01]"
                : "border-white/5 opacity-50"
        )}>
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                    <div className={cn("h-2 w-2 rounded-full bg-[#ff007f] shadow-[0_0_10px_#ff007f]", currentTime >= 8.2 && currentTime <= 12.5 && "animate-pulse")} />
                    <span className="text-[10px] font-black text-[#ff007f] uppercase tracking-[0.25em]">SEG_15: Peak Moment</span>
                </div>
                <span className="text-[9px] font-black text-white bg-[#ff007f]/20 px-3 py-1 rounded-full border border-[#ff007f]/30 uppercase tracking-wider">Critical</span>
            </div>
            <div className="flex gap-5">
                <div className="w-24 h-24 rounded-xl bg-black border border-[#ff007f]/30 overflow-hidden shrink-0 shadow-inner">
                    <video src={selectedItem ? getVideoUrl(selectedItem) : ""} className="w-full h-full object-contain" />
                </div>
                <div className="min-w-0 flex-1 flex flex-col justify-center">
                    <p className="text-[11px] font-black text-white uppercase tracking-tight truncate mb-3">
                        {selectedItem?.filename}
                    </p>
                    <p className="text-[10px] text-slate-300 font-bold uppercase leading-tight mb-1">Matches reference intensity</p>
                    <p className="text-[9px] text-slate-500 uppercase leading-snug font-medium">Best available peak candidate</p>
                </div>
            </div>
        </div>

        {/* SEG_14: System Build */}
        <div className={cn(
            "bg-[#0a0c14]/40 border rounded-xl p-5 transition-all duration-700",
            currentTime >= 4 && currentTime < 8.2
                ? "border-indigo-500/40 shadow-[0_0_20px_rgba(79,102,241,0.1)] opacity-100"
                : "border-white/5 opacity-40"
        )}>
            <div className="flex items-center justify-between mb-4">
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">SEG_14: System Build</span>
                <span className="text-[9px] font-black text-indigo-400 uppercase tracking-wider">Strong Match</span>
            </div>
            <div className="flex items-center gap-3">
                <TrendingUp className="h-4 w-4 text-emerald-500" />
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Supports emotional build</span>
            </div>
        </div>
    </div>

    {/* AI INSIGHT - Compact Summary */}
    <div className="bg-[#0a0c14]/60 border border-white/5 rounded-2xl p-6 backdrop-blur-sm">
        <div className="flex items-center gap-3 mb-5">
            <BrainCircuit className="w-4 h-4 text-cyan-400" />
            <h3 className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.3em]">AI Insight</h3>
        </div>
        <div className="space-y-4">
            <div className="border-l-2 border-cyan-500/30 pl-4">
                <p className="text-[10px] font-bold text-slate-300 uppercase tracking-tight leading-relaxed">
                    Edit maintained rhythmic consistency but lacked high-energy clips during peak window (8.2s–12.5s).
                </p>
            </div>
            <div className="border-l-2 border-[#ff007f]/30 pl-4">
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-tight leading-relaxed">
                    Clip library skewed toward calm shots, limiting peak amplification.
                </p>
            </div>
        </div>
    </div>

    {/* ACTIONS - Bottom */}
    <div className="bg-[#0a0c14]/60 border border-white/5 rounded-2xl p-6 backdrop-blur-sm">
        <div className="flex items-center gap-3 mb-5">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <h3 className="text-[10px] font-black text-indigo-400 uppercase tracking-[0.3em]">Recommended Action</h3>
        </div>
        <p className="text-[10px] font-bold text-slate-300 uppercase tracking-tight leading-relaxed mb-6 border-l-2 border-indigo-500/30 pl-4">
            Add 2–3 clips with fast camera motion to reinforce emotional climax.
        </p>
        <button
            onClick={() => toast.success("Re-generating video with editorial insights...")}
            className="w-full h-14 rounded-xl bg-indigo-600 text-white font-black text-[11px] uppercase tracking-[0.3em] shadow-[0_20px_40px_rgba(79,102,241,0.3)] hover:scale-[1.02] transition-all relative group overflow-hidden border border-indigo-500/40"
        >
            <span className="relative z-10">Remake Video</span>
            <div className="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity"></div>
        </button>
        <p className="text-[9px] text-center text-slate-600 uppercase tracking-widest mt-3 font-black">Applies editorial insights automatically</p>
    </div>
</aside>
    );
}
