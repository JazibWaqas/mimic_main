"use client";

import { useState, useEffect } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { Clip, Reference, Result } from "@/lib/types";

interface CategorySidebarProps {
    onSelect: (category: string | null, item?: Clip | Reference | Result) => void;
    selectedCategory: string | null;
}

export default function CategorySidebar({ onSelect, selectedCategory }: CategorySidebarProps) {
    const [expanded, setExpanded] = useState<string | null>(null);
    const [clips, setClips] = useState<Clip[]>([]);
    const [references, setReferences] = useState<Reference[]>([]);
    const [results, setResults] = useState<Result[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchAll = async () => {
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
                console.error("Failed to load categories", err);
            } finally {
                setLoading(false);
            }
        };
        fetchAll();
    }, []);

    const categories = [
        { name: "Clips", items: clips, key: "clips" },
        { name: "Reference Videos", items: references, key: "references" },
        { name: "Results", items: results, key: "results" }
    ];

    const toggleCategory = (key: string) => {
        if (expanded === key) {
            setExpanded(null);
            onSelect(null);
        } else {
            setExpanded(key);
            onSelect(key);
        }
    };

    const handleItemClick = (category: string, item: Clip | Reference | Result) => {
        onSelect(category, item);
    };

    return (
        <div className="min-w-[220px] max-w-[260px] sticky top-0 h-[calc(100vh-80px)] bg-gradient-to-b from-slate-800/90 via-slate-900/90 to-black/90 overflow-y-auto no-scrollbar border-r border-white/5">
            <h3 className="text-lg font-black text-white text-center pt-4 mb-4 uppercase tracking-wider">Categories</h3>
            <ul className="list-none p-0 m-0 pb-4">
                {categories.map((cat) => (
                    <li key={cat.key}>
                        <div
                            className={cn(
                                "cursor-pointer font-medium py-3 px-5 rounded-md transition-all mb-0.5 flex items-center justify-between",
                                expanded === cat.key || selectedCategory === cat.key
                                    ? "bg-indigo-500/20 text-white font-bold"
                                    : "text-white/70 hover:bg-white/5 hover:text-white"
                            )}
                            onClick={() => toggleCategory(cat.key)}
                        >
                            <span>{cat.name}</span>
                            {expanded === cat.key ? (
                                <ChevronDown className="h-4 w-4" />
                            ) : (
                                <ChevronRight className="h-4 w-4" />
                            )}
                        </div>
                        {expanded === cat.key && (
                            <ul className="list-none pl-6 pr-2 mt-1 mb-2">
                                {loading ? (
                                    <li className="text-white/50 text-[9px] py-2 px-3">Loading...</li>
                                ) : cat.items.length === 0 ? (
                                    <li className="text-white/50 text-[9px] py-2 px-3">No items</li>
                                ) : (
                                    cat.items.map((item, idx) => (
                                        <li key={idx}>
                                            <button
                                                type="button"
                                                className="w-full text-left bg-transparent border-none text-white/70 text-[9px] py-2 px-3 rounded-md transition-all hover:bg-white/5 hover:text-white hover:font-semibold mb-0.5 truncate"
                                                onClick={() => handleItemClick(cat.key, item)}
                                            >
                                                {item.filename}
                                            </button>
                                        </li>
                                    ))
                                )}
                            </ul>
                        )}
                    </li>
                ))}
            </ul>
        </div>
    );
}
