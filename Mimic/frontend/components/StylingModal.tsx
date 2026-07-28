"use client";

import { X, Type } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const POSITIONS = ['top', 'center', 'bottom'] as const;

const FONTS = [
    { key: "cormorant", label: "Cormorant", stack: "'Cormorant Garamond', serif", sample: "Cinematic" },
    { key: "playfair", label: "Playfair", stack: "'Playfair Display', serif", sample: "Editorial" },
    { key: "dm-serif", label: "DM Serif", stack: "'DM Serif Display', serif", sample: "Modern" },
    { key: "lora", label: "Lora", stack: "'Lora', serif", sample: "Warm" },
    { key: "bebas", label: "Bebas", stack: "'Bebas Neue', sans-serif", sample: "IMPACT" },
    { key: "montserrat", label: "Montserrat", stack: "'Montserrat', sans-serif", sample: "Minimal" },
] as const;

const COLORS = [
    { hex: "#FFFFFF", label: "White" },
    { hex: "#F5F0E8", label: "Ivory" },
    { hex: "#E8D5B7", label: "Champagne" },
    { hex: "#C9B99A", label: "Sand" },
    { hex: "#F0E68C", label: "Gold" },
    { hex: "#ADC8E0", label: "Sky" },
    { hex: "#D4A5C9", label: "Blush" },
    { hex: "#FF6B6B", label: "Coral" },
    { hex: "#2D2D2D", label: "Charcoal" },
    { hex: "#000000", label: "Black" },
];

export type TextStyle = {
    caption: string;
    position: 'top' | 'center' | 'bottom';
    font: string;
    color: string;
    fontSize: number;
};

interface StylingModalProps {
    isOpen: boolean;
    onClose: () => void;
    onApply: (payload: TextStyle) => void;
    initialCaption?: string;
    initialPosition?: 'top' | 'center' | 'bottom';
    initialFont?: string;
    initialColor?: string;
    initialFontSize?: number;
}

export default function StylingModal({
    isOpen, onClose, onApply,
    initialCaption, initialPosition, initialFont, initialColor, initialFontSize
}: StylingModalProps) {
    const [caption, setCaption] = useState("");
    const [position, setPosition] = useState<(typeof POSITIONS)[number]>("center");
    const [font, setFont] = useState<string>(FONTS[0].key);
    const [color, setColor] = useState<string>(COLORS[0].hex);
    const [fontSize, setFontSize] = useState(22);

    useEffect(() => {
        if (!isOpen) return;
        if (typeof initialCaption === "string") setCaption(initialCaption);
        if (initialPosition) setPosition(initialPosition);
        if (initialFont) setFont(initialFont);
        if (initialColor) setColor(initialColor);
        if (initialFontSize) setFontSize(initialFontSize);
    }, [isOpen, initialCaption, initialPosition, initialFont, initialColor, initialFontSize]);

    const activeFont = FONTS.find(f => f.key === font) || FONTS[0];

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-3 sm:p-12">
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

            <div className="relative w-full max-w-2xl bg-[#0d1017] border border-white/10 rounded-2xl sm:rounded-[2.5rem] shadow-2xl overflow-hidden flex flex-col max-h-[calc(100vh-1.5rem)] sm:max-h-[90vh]">
                {/* Header */}
                <div className="p-8 border-b border-white/5 flex items-center justify-between bg-black/20">
                    <div className="flex items-center gap-4">
                        <div className="h-10 w-10 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
                            <Type className="h-5 w-5" />
                        </div>
                        <div>
                            <h2 className="text-sm font-black text-white uppercase tracking-[0.3em]">Apply Visual Style</h2>
                            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-0.5">Post-Production Effects</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="h-10 w-10 rounded-xl hover:bg-white/5 flex items-center justify-center text-slate-500 transition-colors">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-4 sm:p-8 space-y-6 sm:space-y-8 custom-scrollbar">

                    {/* Caption */}
                    <section className="space-y-3">
                        <div className="flex items-center gap-3">
                            <Type className="h-4 w-4 text-indigo-500" />
                            <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Text Overlay</h3>
                        </div>
                        <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Caption</p>
                        <div className="flex gap-2">
                            <input
                                value={caption}
                                onChange={(e) => setCaption(e.target.value)}
                                placeholder='Type overlay text (e.g. "Oh, to be this young again.")'
                                className="flex-1 h-12 px-4 rounded-xl bg-white/[0.02] border border-white/5 text-[11px] text-slate-200 placeholder:text-slate-600 outline-none focus:border-indigo-500/30 focus:bg-white/[0.04] transition-all"
                            />
                            <button
                                onClick={() => setCaption("")}
                                className="h-12 px-4 rounded-xl bg-white/5 border border-white/10 text-[9px] font-black text-slate-400 uppercase tracking-widest hover:bg-white/10 transition-all"
                            >
                                Clear
                            </button>
                        </div>

                        {/* Live preview */}
                        {caption && (
                            <div className="h-14 rounded-xl bg-black/40 border border-white/5 flex items-center justify-center px-4 overflow-hidden">
                                <span
                                    style={{ fontFamily: activeFont.stack, color, fontSize, textShadow: "0 2px 8px rgba(0,0,0,0.9)" }}
                                    className="truncate"
                                >
                                    {caption}
                                </span>
                            </div>
                        )}
                    </section>

                    {/* Font picker */}
                    <section className="space-y-3">
                        <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Font</p>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                            {FONTS.map(f => (
                                <button
                                    key={f.key}
                                    onClick={() => setFont(f.key)}
                                    className={cn(
                                        "h-16 rounded-xl border flex flex-col items-center justify-center gap-1 transition-all",
                                        font === f.key
                                            ? "bg-indigo-600/10 border-indigo-500/40 text-white"
                                            : "bg-white/[0.02] border-white/5 text-slate-500 hover:bg-white/[0.04] hover:text-slate-300"
                                    )}
                                >
                                    <span style={{ fontFamily: f.stack, fontSize: 15 }}>{f.sample}</span>
                                    <span className="text-[8px] font-black uppercase tracking-widest opacity-60">{f.label}</span>
                                </button>
                            ))}
                        </div>
                    </section>

                    {/* Font size slider */}
                    <section className="space-y-3">
                        <div className="flex items-center justify-between">
                            <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Font Size</p>
                            <span className="text-[10px] font-black text-slate-400 tabular-nums">{fontSize}px</span>
                        </div>
                        <input
                            type="range"
                            min={12}
                            max={48}
                            step={1}
                            value={fontSize}
                            onChange={(e) => setFontSize(Number(e.target.value))}
                            className="w-full h-1.5 rounded-full accent-indigo-500 cursor-pointer"
                        />
                        <div className="flex justify-between text-[8px] text-slate-700 font-mono">
                            <span>12px</span>
                            <span>48px</span>
                        </div>
                    </section>

                    {/* Color picker */}
                    <section className="space-y-3">
                        <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Color</p>
                        <div className="flex gap-3 flex-wrap">
                            {COLORS.map(c => (
                                <button
                                    key={c.hex}
                                    title={c.label}
                                    onClick={() => setColor(c.hex)}
                                    className={cn(
                                        "h-9 w-9 rounded-full border-2 transition-all hover:scale-110",
                                        color === c.hex ? "border-indigo-400 scale-110 shadow-[0_0_12px_rgba(99,102,241,0.5)]" : "border-white/10"
                                    )}
                                    style={{ backgroundColor: c.hex }}
                                />
                            ))}
                        </div>
                    </section>

                    {/* Placement */}
                    <section className="space-y-3">
                        <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Placement</p>
                        <div className="flex gap-2">
                            {POSITIONS.map(p => (
                                <button
                                    key={p}
                                    onClick={() => setPosition(p)}
                                    className={cn(
                                        "flex-1 py-2 rounded-lg border text-[9px] font-black uppercase tracking-widest transition-all",
                                        position === p
                                            ? "bg-indigo-600/10 border-indigo-500/30 text-white"
                                            : "bg-white/[0.02] border-white/5 text-slate-500 hover:bg-white/[0.04]"
                                    )}
                                >
                                    {p}
                                </button>
                            ))}
                        </div>
                    </section>

                </div>

                {/* Footer */}
                <div className="p-8 border-t border-white/5 bg-black/20 flex gap-4">
                    <button
                        onClick={onClose}
                        className="flex-1 h-14 rounded-2xl bg-white/5 border border-white/10 text-[10px] font-black text-slate-400 uppercase tracking-widest hover:bg-white/10 transition-all"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => {
                            setCaption("");
                            setPosition("center");
                            setFont(FONTS[0].key);
                            setColor(COLORS[0].hex);
                            setFontSize(22);
                        }}
                        className="flex-1 h-14 rounded-2xl bg-white/5 border border-white/10 text-[10px] font-black text-slate-400 uppercase tracking-widest hover:bg-white/10 transition-all"
                    >
                        Reset
                    </button>
                    <button
                        onClick={() => onApply({ caption, position, font, color, fontSize })}
                        className="flex-[1.5] h-14 rounded-2xl bg-indigo-600 text-[10px] font-black text-white uppercase tracking-widest hover:bg-indigo-500 transition-all shadow-xl shadow-indigo-600/20"
                    >
                        Update Visual Path
                    </button>
                </div>
            </div>
        </div>
    );
}
