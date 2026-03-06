"use client";

import { useMemo, useState, useRef } from "react";
import { useSearchParams } from "next/navigation";
import {
    Play,
    Pause,
    RotateCcw,
    Volume2,
    VolumeX,
    Plus
} from "lucide-react";

export default function ComparePage() {
    const searchParams = useSearchParams();
    const [isPlaying, setIsPlaying] = useState(false);
    const [isMuted, setIsMuted] = useState(true);

    const refVideoRef = useRef<HTMLVideoElement>(null);
    const outputVideoRef = useRef<HTMLVideoElement>(null);

    const refUrl = useMemo(() => {
        const ref = searchParams.get("ref");
        return ref ? `http://localhost:8000${ref}` : "";
    }, [searchParams]);

    const outputUrl = useMemo(() => {
        const output = searchParams.get("output");
        return output ? `http://localhost:8000${output}` : "";
    }, [searchParams]);

    const togglePlayPause = () => {
        if (refVideoRef.current && outputVideoRef.current) {
            if (isPlaying) {
                refVideoRef.current.pause();
                outputVideoRef.current.pause();
            } else {
                refVideoRef.current.play();
                outputVideoRef.current.play();
            }
            setIsPlaying(!isPlaying);
        }
    };

    const restart = () => {
        if (refVideoRef.current && outputVideoRef.current) {
            refVideoRef.current.currentTime = 0;
            outputVideoRef.current.currentTime = 0;
            refVideoRef.current.play();
            outputVideoRef.current.play();
            setIsPlaying(true);
        }
    };

    const toggleMute = () => {
        if (refVideoRef.current && outputVideoRef.current) {
            refVideoRef.current.muted = !isMuted;
            outputVideoRef.current.muted = !isMuted;
            setIsMuted(!isMuted);
        }
    };

    return (
        <div className="pt-32 p-10 max-w-[1400px] mx-auto mimic-fade-in pb-40">
            <header className="mb-20">
                <div className="inline-flex items-center gap-4 px-4 py-1.5 rounded-xl glass-indigo border-indigo-500/20 mb-6">
                    <Plus className="h-3 w-3 text-indigo-400 rotate-45" />
                    <span className="text-[9px] font-black uppercase tracking-[0.4em] text-indigo-300">Side-by-Side Diagnostic</span>
                </div>
                <h1 className="text-6xl font-black uppercase tracking-tighter">
                    <span className="shiny-text">NEURAL.</span> <br />
                    <span className="text-white/95">COMPARISON.</span>
                </h1>
            </header>

            <div className="grid lg:grid-cols-2 gap-10 mb-20">
                {/* Reference Module */}
                <div className="space-y-6">
                    <div className="flex items-center justify-between px-2">
                        <h2 className="text-[11px] font-black uppercase tracking-[0.4em] text-indigo-400">Structural Blueprint</h2>
                        <span className="text-[9px] font-bold text-slate-500 uppercase tracking-[0.2em]">Source DNA</span>
                    </div>
                    <div className="aspect-video bg-black rounded-3xl overflow-hidden glass-indigo border-indigo-500/30 relative">
                        {refUrl ? (
                            <video
                                ref={refVideoRef}
                                src={refUrl}
                                className="w-full h-full object-contain"
                                muted={isMuted}
                            />
                        ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center text-slate-700 space-y-4">
                                <div className="h-12 w-12 rounded-full border border-dashed border-white/10 flex items-center justify-center">
                                    <div className="h-2 w-2 rounded-full bg-slate-800" />
                                </div>
                                <p className="text-[10px] uppercase tracking-[0.2em] font-bold">Waiting for Telemetry</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Output Module */}
                <div className="space-y-6">
                    <div className="flex items-center justify-between px-2">
                        <h2 className="text-[11px] font-black uppercase tracking-[0.4em] text-cyan-400">Synthesized Master</h2>
                        <span className="text-[9px] font-bold text-slate-500 uppercase tracking-[0.2em]">Neural Output</span>
                    </div>
                    <div className="aspect-video bg-black rounded-3xl overflow-hidden glass-cyan border-cyan-500/30 relative">
                        {outputUrl ? (
                            <video
                                ref={outputVideoRef}
                                src={outputUrl}
                                className="w-full h-full object-contain"
                                muted={isMuted}
                            />
                        ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center text-slate-700 space-y-4">
                                <div className="h-12 w-12 rounded-full border border-dashed border-white/10 flex items-center justify-center">
                                    <div className="h-2 w-2 rounded-full bg-slate-800" />
                                </div>
                                <p className="text-[10px] uppercase tracking-[0.2em] font-bold">Capture Link Required</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Global Playback Terminal */}
            <div className="glass rounded-[2rem] p-10 border-white/5 flex flex-col items-center gap-10">
                <div className="flex items-center justify-center gap-12">
                    <button
                        onClick={restart}
                        className="h-12 w-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-500 hover:text-white hover:border-white/30 transition-all duration-500"
                    >
                        <RotateCcw className="h-4 w-4" />
                    </button>

                    <button
                        onClick={togglePlayPause}
                        className="h-24 w-24 rounded-full bg-indigo-500 flex items-center justify-center text-white shadow-[0_0_40px_rgba(99,102,241,0.4)] hover:scale-110 active:scale-95 transition-all duration-500"
                    >
                        {isPlaying ? <Pause className="h-8 w-8 fill-current" /> : <Play className="h-8 w-8 fill-current ml-2" />}
                    </button>

                    <button
                        onClick={toggleMute}
                        className="h-12 w-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-500 hover:text-white hover:border-white/30 transition-all duration-500"
                    >
                        {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                    </button>
                </div>

                <div className="h-[2px] w-64 bg-gradient-to-r from-transparent via-white/10 to-transparent" />

                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-slate-600">Synchronized Playback Matrix // Active</p>
            </div>
        </div>
    );
}