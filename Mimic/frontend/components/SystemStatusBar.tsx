"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Shield, Brain, Database, Cpu } from "lucide-react";

export function SystemStatusBar() {
    const [clipCount, setClipCount] = useState<number | null>(null);

    useEffect(() => {
        const fetchCache = async () => {
            try {
                const data = await api.fetchClips();
                if (data.clips) {
                    setClipCount(data.clips.length);
                }
            } catch (err) {
                console.error("Failed to fetch cache stats", err);
            }
        };
        fetchCache();
    }, []);

    return (
        <div className="fixed top-24 left-1/2 -translate-x-1/2 z-[60] w-full max-w-[900px] px-4 animate-in fade-in slide-in-from-top-4 duration-1000">
            <div className="glass-premium rounded-full border border-white/10 px-8 py-2.5 shadow-[0_20px_50px_rgba(0,0,0,0.5)] flex items-center justify-between gap-8">
                <div className="flex items-center gap-8">
                    {/* System Operational */}
                    <div className="flex items-center gap-2">
                        <div className="h-1.5 w-1.5 rounded-full bg-lime-400 glow-lime pulse-glow" />
                        <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest flex items-center gap-1.5">
                            <Shield className="h-3 w-3 text-lime-400" />
                            System: <span className="text-white">Operational</span>
                        </span>
                    </div>

                    {/* Gemini Active */}
                    <div className="flex items-center gap-2 border-l border-white/10 pl-8">
                        <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 glow-cyan pulse-glow" />
                        <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest flex items-center gap-1.5">
                            <Brain className="h-3 w-3 text-cyan-400" />
                            Gemini: <span className="text-white">Active</span>
                        </span>
                    </div>

                    {/* Cache Status - Electric Purple */}
                    <div className="flex items-center gap-2 border-l border-white/10 pl-8">
                        <div className="h-1.5 w-1.5 rounded-full bg-purple-500 glow-purple" />
                        <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest flex items-center gap-1.5">
                            <Database className="h-3 w-3 text-purple-400" />
                            Cache: <span className="text-white">{clipCount !== null ? `${clipCount} Clips` : 'Analyzing...'}</span>
                        </span>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <span className="text-[9px] font-black text-slate-500 uppercase tracking-[0.2em] flex items-center gap-1.5">
                        <Cpu className="h-3 w-3" />
                        CORE v7.0.4-SYNTH
                    </span>
                </div>
            </div>
        </div>
    );
}
