"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
    PlusCircle,
    Library,
    History,
    Zap,
    Settings,
    HelpCircle,
    Cpu,
    GitCompare,
    ChevronLeft,
    ChevronRight
} from "lucide-react";

const navItems = [
    { label: "Studio", icon: PlusCircle, href: "/" },
    { label: "Library", icon: Library, href: "/gallery" },
    { label: "Projects", icon: History, href: "/vault" },
    { label: "Compare", icon: GitCompare, href: "/compare" },
];

const secondaryItems = [
    { label: "Settings", icon: Settings, href: "/settings" },
    { label: "Docs", icon: HelpCircle, href: "/docs" },
];

export function Sidebar() {
    const pathname = usePathname();
    const [isCollapsed, setIsCollapsed] = useState(false);

    return (
        <aside className={cn(
            "fixed left-0 top-0 z-40 h-screen border-r border-white/5 bg-[#0a0a0f]/95 backdrop-blur-xl transition-all duration-500",
            isCollapsed ? "w-16" : "w-64"
        )}>
            <div className="flex h-full flex-col px-4 py-8">
                {/* Brand & Toggle */}
                <div className="mb-12 flex items-center justify-between">
                    {!isCollapsed && (
                        <div className="flex items-center gap-3 group cursor-pointer">
                            <div className="h-8 w-8 bg-gradient-to-br from-teal-500 to-purple-500 rounded-lg flex items-center justify-center shadow-lg shadow-teal-500/20">
                                <Zap className="h-4 w-4 text-white fill-current" />
                            </div>
                            <span className="text-sm font-bold tracking-wider uppercase text-white">Mimic</span>
                        </div>
                    )}
                    <button
                        onClick={() => setIsCollapsed(!isCollapsed)}
                        className={cn(
                            "h-8 w-8 rounded-lg bg-slate-800/50 hover:bg-slate-700/50 flex items-center justify-center transition-all",
                            isCollapsed && "mx-auto"
                        )}
                    >
                        {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
                    </button>
                </div>

                {/* Main Navigation */}
                <nav className="flex-1 space-y-1">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-300 group",
                                    isActive
                                        ? "bg-gradient-to-r from-teal-500/10 to-purple-500/10 text-white"
                                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/30"
                                )}
                                title={isCollapsed ? item.label : undefined}
                            >
                                <item.icon className={cn("h-4 w-4 flex-shrink-0", isActive ? "text-teal-400" : "text-slate-500")} />
                                {!isCollapsed && (
                                    <span className="text-xs font-semibold uppercase tracking-wider">{item.label}</span>
                                )}
                            </Link>
                        );
                    })}
                </nav>

                {/* Status System */}
                {!isCollapsed && (
                    <div className="mt-auto space-y-4">
                        <nav className="space-y-1">
                            {secondaryItems.map((item) => (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className="flex items-center gap-3 px-3 py-2 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800/30 transition-all"
                                >
                                    <item.icon className="h-3.5 w-3.5" />
                                    <span className="text-[10px] font-semibold uppercase tracking-wider">{item.label}</span>
                                </Link>
                            ))}
                        </nav>

                        <div className="p-4 rounded-lg bg-gradient-to-br from-teal-500/5 to-purple-500/5 border border-teal-500/20">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="h-1.5 w-1.5 rounded-full bg-teal-400 status-pulse" />
                                <h4 className="text-[10px] font-bold uppercase tracking-wider text-white">System Core</h4>
                            </div>
                            <div className="flex items-start gap-2">
                                <Cpu className="h-3.5 w-3.5 text-teal-500/50 mt-0.5" />
                                <p className="text-[9px] text-slate-400 font-medium leading-relaxed">
                                    Neural Link v2.3 <br />
                                    <span className="text-teal-400/60">All cores active</span>
                                </p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </aside>
    );
}
