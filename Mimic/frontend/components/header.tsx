"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Library, Database, Wand2, UserCircle } from "lucide-react";

const navItems = [
    { label: "Studio", href: "/", icon: Wand2 },
    { label: "Library", href: "/gallery", icon: Library },
    { label: "Vault", href: "/vault", icon: Database },
];

export function Header() {
    const pathname = usePathname();

    return (
        <header className="w-full z-50 py-4 px-6 md:px-12 bg-transparent">
            <div className="max-w-[1700px] mx-auto flex items-center justify-between">
                <div className="flex items-center gap-6">
                    <Link href="/" className="flex items-center gap-4 group">
                        <div className="h-12 w-12 bg-indigo-500 border border-white/20 rounded-2xl flex items-center justify-center shadow-[0_0_30px_rgba(99,102,241,0.4)] transition-all duration-500 group-hover:rotate-12 group-hover:scale-110">
                            <Wand2 className="h-6 w-6 text-white" />
                        </div>
                        <div className="flex flex-col">
                            <span className="text-2xl font-black tracking-tighter text-white leading-none">MIMIC</span>
                            <span className="text-[11px] font-black tracking-[0.2em] text-indigo-400 mt-1 uppercase">Smart Editor</span>
                        </div>
                    </Link>

                </div>

                {/* Navigation - High Visibility */}
                <nav className="flex items-center gap-12">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href;
                        const Icon = item.icon;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    "relative flex items-center gap-3 text-[14px] font-black uppercase tracking-[0.2em] transition-all duration-300 group py-1",
                                    isActive ? "text-white" : "text-slate-400 hover:text-white"
                                )}
                            >
                                <Icon className={cn("h-4 w-4 transition-colors", isActive ? "text-indigo-400" : "text-slate-600 group-hover:text-indigo-300")} />
                                <span>{item.label}</span>
                                <span className={cn(
                                    "absolute -bottom-2 left-0 h-[3px] bg-indigo-500 transition-all duration-500 rounded-full",
                                    isActive ? "w-full opacity-100 shadow-[0_0_15px_rgba(99,102,241,0.6)]" : "w-0 opacity-0 group-hover:w-full group-hover:opacity-100"
                                )} />
                            </Link>
                        );
                    })}
                </nav>

                {/* Account Section - Premium Indigo */}
                <div className="flex items-center gap-6">
                    {/* Status Info (Studio Only or Global) */}
                    <div className="hidden xl:flex items-center gap-6 border-r border-white/5 pr-6">
                        <div className="flex flex-col items-end gap-1">
                            <div className="flex items-center gap-1.5">
                                <span className="text-[10px] font-black text-white uppercase tracking-tighter">System: <span className="text-[#ccff00]">Operational</span></span>
                                <div className="h-1.5 w-1.5 rounded-full bg-[#ccff00] shadow-[0_0_10px_#ccff00] pulse-glow" />
                            </div>
                            <div className="flex items-center gap-1.5">
                                <span className="text-[10px] font-black text-white uppercase tracking-tighter">Gemini 3: <span className="text-cyan-400">Active</span></span>
                                <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 glow-cyan pulse-glow" />
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-4 py-2 px-6 rounded-2xl bg-white/[0.03] border border-white/10 hover:bg-white/10 transition-colors cursor-pointer group shadow-2xl">
                        <div className="flex flex-col items-end">
                            <span className="text-[11px] font-black text-white uppercase tracking-tight">Jazib Waqas</span>
                            <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-widest leading-none mt-1">Pro Account</span>
                        </div>
                        <div className="h-10 w-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center group-hover:bg-indigo-500 group-hover:text-white transition-all">
                            <UserCircle className="h-6 w-6 text-indigo-400 group-hover:text-white" />
                        </div>
                    </div>
                </div>
            </div>
        </header>
    );
}