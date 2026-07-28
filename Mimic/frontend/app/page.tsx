"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { Upload, Video, MonitorPlay, X, Plus, Sparkles, BrainCircuit, Terminal, Activity, CheckCircle2, Zap, Layers, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { api, getStatus, resolveAssetUrl, type CreativeBrief } from "@/lib/api";
import { useDropzone } from "react-dropzone";
import Image from "next/image";

const BRIEF_INTAKE_LABELS: Record<string, string> = {
  subject_priority: "Subject",
  clip_selection_bias: "Clip bias",
  pacing_style: "Pacing",
  music_sync_style: "Music sync",
  caption_strategy: "Captions",
  quality_tolerance: "Shot tolerance",
  ending_strategy: "Ending",
};

const VISIBLE_INTAKE_FIELDS = [
  "subject_priority",
  "clip_selection_bias",
  "pacing_style",
  "music_sync_style",
  "caption_strategy",
  "quality_tolerance",
  "ending_strategy",
];

type BriefThreadMessage = {
  role: "user" | "mimic";
  text: string;
};

export default function StudioPage() {
  const router = useRouter();
  const [refFile, setRefFile] = useState<File | null>(null);
  const [materialFiles, setMaterialFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [musicFile, setMusicFile] = useState<File | null>(null);
  const [textPrompt, setTextPrompt] = useState("");
  const [brief, setBrief] = useState<CreativeBrief | null>(null);
  const [briefThread, setBriefThread] = useState<BriefThreadMessage[]>([]);
  const [briefAnswers, setBriefAnswers] = useState<Record<string, string>>({});
  const [briefApproved, setBriefApproved] = useState(false);
  const [isBriefing, setIsBriefing] = useState(false);
  const [targetDuration] = useState(15);
  const [activeMode, setActiveMode] = useState<"text" | "video">("video");
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [logMessages, setLogMessages] = useState<string[]>([]);
  const [, setRecommendations] = useState<string[]>([]);

  type BlueprintSegment = {
    arc_stage: string;
    energy: string;
    duration: number;
  };

  type BlueprintViewModel = {
    plan_summary?: string;
    narrative_message?: string;
    total_duration: number;
    segments?: BlueprintSegment[];
  };

  type LibraryHealthViewModel = {
    confidence_score: number;
    avg_quality: number;
    asset_count: number;
    energy_distribution: Record<string, number>;
  };

  const [blueprint, setBlueprint] = useState<BlueprintViewModel | null>(null);
  const [libraryHealth, setLibraryHealth] = useState<LibraryHealthViewModel | null>(null);
  const [, setPinnedCritique] = useState<string | null>(null);
  const [isIdLoading, setIsIdLoading] = useState(false);
  const [lastMaterialHash, setLastMaterialHash] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState(false);
  const searchParams = useSearchParams();
  const scrollRef = useRef<HTMLDivElement>(null);
  const processedThumbs = useRef<Set<string>>(new Set());
  const refVideoUrlRef = useRef<string | null>(null);

  // Smart Telemetry Auto-Scroll (User-Aware)
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    // Only auto-scroll if user is currently at the bottom (or logs are new)
    const threshold = 120;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;

    if (isNearBottom || logMessages.length < 3) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
  }, [logMessages]);

  // Handle Refine State
  useEffect(() => {
    const refineFile = searchParams.get("refine");
    if (refineFile) {
      const fetchOldIntel = async () => {
        try {
          type RefineIntel = { advisor?: { remake_strategy?: string } };
          const data = await api.fetchIntelligence("results", refineFile) as RefineIntel;
          if (data?.advisor?.remake_strategy) {
            setPinnedCritique(data.advisor.remake_strategy);
            toast.info("Advisor critique pinned for refinement");
          }
        } catch (err) {
          console.error("Failed to fetch old intel for refine state", err);
        }
      };
      fetchOldIntel();
    }
  }, [searchParams]);

  // v12.7: Safe Healing Worker - Ensures all files eventually get a preview
  useEffect(() => {
    const healMissingPreviews = async () => {
      const missing = materialFiles.filter(f => !previews[f.name + f.size] && !processedThumbs.current.has(f.name + f.size));
      if (missing.length === 0) return;

      for (const file of missing) {
        const key = file.name + file.size;
        processedThumbs.current.add(key);
        const thumb = await generateThumbnail(file);
        if (thumb) {
          setPreviews(prev => ({ ...prev, [key]: thumb }));
        }
      }
    };
    healMissingPreviews();
  }, [materialFiles, previews]);

  // Manage ref video URL to prevent memory leaks
  useEffect(() => {
    if (refFile) {
      // Revoke old URL if exists
      if (refVideoUrlRef.current) {
        URL.revokeObjectURL(refVideoUrlRef.current);
      }
      refVideoUrlRef.current = URL.createObjectURL(refFile);
    } else {
      if (refVideoUrlRef.current) {
        URL.revokeObjectURL(refVideoUrlRef.current);
        refVideoUrlRef.current = null;
      }
    }
    return () => {
      if (refVideoUrlRef.current) {
        URL.revokeObjectURL(refVideoUrlRef.current);
        refVideoUrlRef.current = null;
      }
    };
  }, [refFile]);


  const onDropRef = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles?.[0]) {
      const file = acceptedFiles[0];
      setRefFile(file);
      setIsIdLoading(true);
      try {
        const { session_id } = await api.identify(file);
        setCurrentSessionId(session_id);
        toast.success(`Identity Locked: ${session_id.substring(5, 12)}`);
      } catch {
        toast.error("Identity mapping failed");
      } finally {
        setIsIdLoading(false);
      }
    }
  }, []);

  const generateThumbnail = (file: File): Promise<string> => {
    return new Promise((resolve) => {
      const src = URL.createObjectURL(file);
      const video = document.createElement("video");
      let done = false;

      const finish = (value: string) => {
        if (done) return;
        done = true;
        clearTimeout(timeout);
        URL.revokeObjectURL(src);
        video.remove();
        resolve(value);
      };

      const draw = () => {
        try {
          if (!video.videoWidth || !video.videoHeight) return finish("");
          const canvas = document.createElement("canvas");
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          const ctx = canvas.getContext("2d");
          if (!ctx) return finish("");
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
          finish(dataUrl);
        } catch {
          finish("");
        }
      };

      const timeout = setTimeout(() => finish(""), 10000);

      video.preload = "auto";
      video.muted = true;
      video.playsInline = true;

      video.onloadedmetadata = () => {
        const duration = Number.isFinite(video.duration) ? video.duration : 0;
        const seekTime = duration ? Math.min(duration * 0.25, 1) : 0;
        if (seekTime > 0) {
          video.currentTime = seekTime;
        } else if (video.readyState >= 2) {
          draw();
        }
      };

      video.onloadeddata = () => {
        if (!done && video.readyState >= 2) draw();
      };

      video.onseeked = () => {
        if (!done) draw();
      };

      video.onerror = () => {
        console.warn("[THUMB] Local generation failed for:", file.name);
        finish("");
      };

      // v12.7: Set src ONLY after listeners are ready
      video.src = src;
      video.load();
    });
  };

  const onDropMaterial = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles?.length > 0) {
      setMaterialFiles(prev => [...prev, ...acceptedFiles]);

      // Generate thumbnails in parallel but update state as each is ready
      // This prevents UI blocking while thumbnails are being created
      acceptedFiles.forEach(async (file) => {
        const thumb = await generateThumbnail(file);
        if (thumb) {
          setPreviews(prev => ({ ...prev, [file.name + file.size]: thumb }));
        }
      });

      toast.success(`${acceptedFiles.length} Clips Added`);
    }
  }, []);

  const { getRootProps: getRefProps, getInputProps: getRefInputProps } = useDropzone({
    onDrop: onDropRef, accept: { 'video/*': [] }, multiple: false
  });

  const { getRootProps: getMaterialProps, getInputProps: getMaterialInputProps, isDragActive: isMaterialDragActive } = useDropzone({
    onDrop: onDropMaterial, accept: { 'video/*': [] }, multiple: true
  });

  const checkStatus = async (sessionId: string) => {
    try {
      const status = await getStatus(sessionId);
      setProgress(status.progress * 100);
      if (status.current_step && status.current_step !== statusMsg) setStatusMsg(status.current_step);
      if (status.logs) setLogMessages(status.logs);
      if (status.library_health) setLibraryHealth(status.library_health);
      if (status.blueprint) setBlueprint(status.blueprint);
      if (status.blueprint?.recommendations) setRecommendations(status.blueprint.recommendations);
      if (status.status === "complete") {
        setIsGenerating(false); setProgress(100);
        const filename = status.output_path?.split(/[\\/]/).pop() || `mimic_output_${sessionId}.mp4`;
        router.push(`/vault?filename=${filename}&type=results`);
      } else if (status.status === "error") {
        setIsGenerating(false); toast.error(status.error || "Generation Error");
      }
    } catch { }
  };

  const getApprovedPrompt = () => {
    if (briefApproved && brief?.production_prompt) return brief.production_prompt;
    return "";
  };

  const buildCreativeBrief = async (answersOverride?: Record<string, string>) => {
    const typedMessage = textPrompt.trim();
    const answers = answersOverride ?? briefAnswers;
    const usedAnswers = Object.keys(answers).length > 0;
    const message = typedMessage || (usedAnswers && brief ? "Apply the selected clarification answers to the current brief." : "");

    if (!message || (!brief && !typedMessage)) {
      toast.error(brief ? "Type an update or answer the questions first." : "Describe the edit first.");
      return;
    }

    setIsBriefing(true);
    try {
      const nextBrief = await api.understandBrief(message, brief ? { ...brief, clarification_answers: answers } : null);
      setBrief(nextBrief);
      setBriefAnswers({});
      setBriefApproved(false);
      setTextPrompt("");
      setBriefThread(prev => [
        ...prev,
        ...(typedMessage ? [{ role: "user" as const, text: typedMessage }] : []),
        ...(usedAnswers ? [{
          role: "user" as const,
          text: `Selected: ${Object.values(answers).join("; ")}`,
        }] : []),
        {
          role: "mimic" as const,
          text: nextBrief.status === "needs_clarification"
            ? "I updated the brief and need a few decisions before approval."
            : "I updated the brief. It is ready for approval.",
        },
      ].slice(-8));
      toast.success(
        usedAnswers
          ? "Plan updated from your answers"
          : nextBrief.status === "needs_clarification"
            ? "MIMIC needs a few choices"
            : "Plan ready to review"
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not build the plan.";
      toast.error(message);
    } finally {
      setIsBriefing(false);
    }
  };

  const approveBrief = () => {
    if (!brief) return;
    if (brief.status === "needs_clarification" && (brief.questions?.length || 0) > 0) {
      toast.error("Answer the alignment questions or use smart defaults first.");
      return;
    }
    setBriefApproved(true);
    toast.success("Plan approved");
  };

  const answerBriefQuestion = (id: string, answer: string) => {
    setBriefAnswers(prev => ({ ...prev, [id]: answer }));
    setBriefApproved(false);
  };

  const applyBriefAnswers = () => {
    if (!brief) return;
    const questions = brief.questions || [];
    const missing = questions.filter(q => !briefAnswers[q.id]);
    if (missing.length > 0) {
      toast.error("Answer each question first, or use smart defaults.");
      return;
    }
    buildCreativeBrief(briefAnswers);
  };

  const useBriefDefaults = () => {
    if (!brief) return;
    const defaults = Object.fromEntries(
      (brief.questions || []).map((question) => [
        question.id,
        question.options?.[0] || "Use MIMIC's recommended default",
      ])
    );
    setBriefAnswers(defaults);
    buildCreativeBrief(defaults);
  };

  const startMimic = async () => {
    const approvedPrompt = getApprovedPrompt();
    if (activeMode === "text" && !approvedPrompt) {
      return toast.error(brief ? "Approve the plan first." : "Build a plan first.");
    }
    if (!refFile && !approvedPrompt) return toast.error("Provide a reference video or approve a text plan.");
    if (materialFiles.length === 0) return toast.error("Provide source material clips.");

    setIsGenerating(true); setStatusMsg("Initializing..."); setProgress(5); setGenerationError(false);
    try {
      // Create a unique fingerprint of the current configuration
      const currentMaterialHash = materialFiles.map(f => f.name + f.size).join("|") +
        (refFile ? refFile.name + refFile.size : "none") +
        (musicFile ? musicFile.name + musicFile.size : "none");

      let session_id = currentSessionId;
      const canSkipUpload = session_id && lastMaterialHash === currentMaterialHash;

      if (canSkipUpload) {
        console.log("[STUDIO] Config unchanged. Fast-tracking to generation using session:", session_id);
        setStatusMsg("Reusing session assets...");
        setProgress(10);
      } else {
        console.log("[STUDIO] Config changed or new session. Starting upload...");
        // 1. Upload assets (reference and music are optional now)
        type UploadedClipMeta = {
          filename: string;
          size: number;
          thumbnail_url?: string;
          original_filename?: string;
          original_size?: number;
        };

        const uploadRes = await api.uploadFiles(refFile ?? undefined, materialFiles, musicFile ?? undefined) as {
          session_id: string;
          clips?: UploadedClipMeta[];
        };
        session_id = uploadRes.session_id;
        setCurrentSessionId(session_id);
        setLastMaterialHash(currentMaterialHash);
        console.log("[STUDIO] Upload complete. New Session ID:", session_id);

        // Update previews with backend thumbnails immediately if available
        if (uploadRes.clips && uploadRes.clips.length > 0) {
          setPreviews(prev => {
            const next = { ...prev };
            uploadRes.clips?.forEach((clip) => {
              // Perfect Match (v12.3): Link using original properties from backend
              if (clip.original_filename && clip.original_size) {
                const key = clip.original_filename + clip.original_size;
                const thumb = clip.thumbnail_url || "";
                const url = resolveAssetUrl(thumb);
                next[key] = url;
              }
            });
            return next;
          });
        }
      }

      setProgress(15);
      setStatusMsg("Synthesizing Blueprint...");

      // 2. Start generation with optional text prompt
      if (!session_id) throw new Error("No active session");
      const genRes = await api.startGeneration(session_id, approvedPrompt || undefined, targetDuration);
      console.log("[STUDIO] Generation started:", genRes);

      const ws = api.connectProgress(session_id);

      if (!ws) {
        // v14.9 Demo Mode Simulation: Success without backend
        if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
          setTimeout(() => {
            setStatusMsg("Protocol Simulation Complete");
            setProgress(100);
            setIsGenerating(false);
            toast.success("Demo execution successful. Loading Vault...");
            router.push(`/vault?filename=result.mp4&type=results`);
          }, 2000);
          return;
        }
        throw new Error("Could not establish communication protocol");
      }

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        setProgress(data.progress * 100);
        setStatusMsg(data.message || "");
        if (data.logs) setLogMessages(data.logs);
        if (data.library_health) setLibraryHealth(data.library_health);
        if (data.blueprint) setBlueprint(data.blueprint);

        // Dynamic Agent Insight parsing from logs
        if (data.message && data.message.includes("Advisor")) {
          setRecommendations(prev => {
            if (!prev.includes(data.message)) return [data.message, ...prev].slice(0, 5);
            return prev;
          });
        }

        if (data.status === "complete") {
          setIsGenerating(false);
          checkStatus(session_id);
        } else if (data.status === "error") {
          setIsGenerating(false);
          setGenerationError(true);
          setStatusMsg("Synthesis Failed");
          toast.error(data.message || "Generation Error via Protocol");
        }
      };
      ws.onerror = () => {
        setGenerationError(true);
        setIsGenerating(false);
        checkStatus(session_id);
      };
    } catch (err) {
      setIsGenerating(false);
      setGenerationError(true);
      const message = err instanceof Error ? err.message : "Process failed.";
      toast.error(message);
      console.error("Studio start failed", err);
    }
  };

  const approvedPrompt = getApprovedPrompt();
  const needsApprovedBrief = activeMode === "text" && Boolean(brief) && !approvedPrompt;
  const canExecute = !isGenerating && !isIdLoading && materialFiles.length > 0 && (
    activeMode === "text" ? Boolean(approvedPrompt) : Boolean(refFile || approvedPrompt)
  );
  const openBriefQuestions = brief?.status === "needs_clarification" ? (brief.questions || []) : [];
  const allBriefQuestionsAnswered = openBriefQuestions.length > 0 && openBriefQuestions.every(q => Boolean(briefAnswers[q.id]));
  const resolvedBriefChoices = brief?.resolved_choices || [];
  const visibleBriefIntake = brief?.intake || {};
  const briefIntakeConfidence = brief?.intake_confidence || {};

  return (
    <div className="min-h-screen bg-[#020306] overflow-x-hidden pt-4 pb-24">
      <div className="max-w-[1700px] mx-auto px-4 sm:px-6 md:px-12 relative transition-all duration-700">

        {/* Hero Section - More Compact */}
        <div className="shrink-0 flex flex-col md:flex-row md:items-end justify-between gap-4 pb-4 border-b border-white/10">
          <div className="space-y-2 max-w-3xl">
            <div className="space-y-0.5 group">
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                  <Wand2 className="h-4 w-4" />
                </div>
                <h1 className="text-3xl font-black tracking-tighter text-white uppercase italic">
                  Studio
                </h1>
              </div>
              <p className="text-[12px] font-black text-indigo-400 uppercase tracking-[0.3em] ml-10">AI Creative Engine</p>
            </div>
            <div className="space-y-1.5 ml-10 border-l-2 border-white/5 pl-6 py-1">
              <p className="text-[14px] text-slate-400 leading-relaxed font-medium">
                MIMIC is a translation engine that uses Gemini 3&apos;s power to convert human creative intent into deterministic editorial structure, executes under real-world constraints, and explains the outcome transparently.
              </p>
            </div>
          </div>
          <div className="hidden md:flex flex-col items-end gap-2 pr-2 group/logic">
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-black text-slate-600 uppercase tracking-widest">Logic Core:</span>
              <span className={cn(
                "text-[9px] font-black uppercase tracking-widest transition-all duration-500",
                refFile && materialFiles.length > 0 ? "text-[#ff007f] shadow-[0_0_10px_#ff007f]" : "text-cyan-500 animate-pulse"
              )}>
                {refFile && materialFiles.length > 0 ? "System Ready" : "Syncing"}
              </span>
            </div>
            <div className="h-1.5 w-40 bg-white/5 rounded-full overflow-hidden border border-white/5 relative">
              <div
                className="h-full transition-all duration-1000 ease-out relative z-10"
                style={{
                  width: refFile && materialFiles.length > 0 ? '100%' : refFile || materialFiles.length > 0 ? '50%' : '10%',
                  background: `linear-gradient(to right, #bf00ff, #00d4ff)`
                }}
              />
              {refFile && materialFiles.length > 0 && (
                <div className="absolute inset-0 bg-[#ff007f]/20 animate-pulse z-20" />
              )}
            </div>
          </div>
        </div>

        {/* Glass Content Interface - Added significant margin top */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6 lg:gap-12 mt-8 sm:mt-12">
          <div className="space-y-12">

            {/* 01. Style Binding - Unified Toggle Interface */}
            <div className="space-y-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "h-1.5 w-1.5 rounded-full shadow-[0_0_12px_rgba(99,102,241,1)]",
                    activeMode === "text" ? "bg-[#ff007f] shadow-[#ff007f]" : "bg-cyan-500 shadow-[#06b6d4]"
                  )} />
                  <h3 className="text-[11px] font-black text-white uppercase tracking-[0.3em]">01. Style Binding</h3>
                </div>

                {/* Mode Toggle */}
                <div className="flex bg-white/5 p-1 rounded-lg border border-white/5">
                  <button
                    onClick={() => setActiveMode("text")}
                    className={cn(
                      "px-4 py-1.5 rounded-md text-[9px] font-black uppercase tracking-widest transition-all",
                      activeMode === "text" ? "bg-[#ff007f] text-white shadow-[0_0_15px_rgba(255,0,127,0.4)]" : "text-slate-500 hover:text-slate-300"
                    )}
                  >
                    Creator Mode
                  </button>
                  <button
                    onClick={() => setActiveMode("video")}
                    className={cn(
                      "px-4 py-1.5 rounded-md text-[9px] font-black uppercase tracking-widest transition-all",
                      activeMode === "video" ? "bg-cyan-500 text-white shadow-[0_0_15px_rgba(0,212,255,0.4)]" : "text-slate-500 hover:text-slate-300"
                    )}
                  >
                    Mimic Mode
                  </button>
                </div>
              </div>

              {/* Unified input box - Grid stacked layers for smooth transition */}
              <div className="relative grid grid-cols-1 grid-rows-1 min-h-[360px] sm:min-h-[420px] rounded-2xl border border-white/10 bg-white/[0.02] overflow-hidden">
                {/* Animated border color overlay */}
                <div className={cn(
                  "absolute inset-0 rounded-2xl pointer-events-none transition-colors duration-500 z-20",
                  activeMode === "text" ? "border border-[#ff007f]/20" : "border border-cyan-500/20"
                )} />

                {/* Text/Creator Mode Layer */}
                <div className={cn(
                  "col-start-1 row-start-1 flex flex-col p-4 sm:p-8 space-y-6 transition-opacity duration-300",
                  activeMode === "text" ? "opacity-100 pointer-events-auto z-10" : "opacity-0 pointer-events-none z-0"
                )}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-full bg-[#ff007f]/10 border border-[#ff007f]/20 flex items-center justify-center">
                        <BrainCircuit className="h-4 w-4 text-[#ff007f]" />
                      </div>
                      <div className="space-y-0.5">
                        <p className="text-[10px] font-black text-white uppercase tracking-widest">Director&apos;s Chat</p>
                        <p className="text-[8px] font-bold text-slate-600 uppercase tracking-tight">Describe your vision below</p>
                      </div>
                    </div>
                  </div>

                  <div className="flex-1 grid grid-cols-1 xl:grid-cols-[minmax(0,0.9fr)_minmax(280px,0.7fr)] gap-4 min-h-0">
                    <div className="bg-white/[0.03] border border-white/10 rounded-2xl rounded-tl-none p-5 relative group/bubble transition-all hover:bg-white/[0.05] flex flex-col min-h-[210px]">
                      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar pr-1 space-y-3">
                        {briefThread.length === 0 ? (
                          <div className="h-full min-h-[120px] flex items-center text-sm font-medium leading-relaxed text-slate-600">
                            Start by telling MIMIC what you want. After that, this becomes a running chat where new messages correct or add to the plan.
                          </div>
                        ) : (
                          briefThread.map((message, index) => (
                            <div
                              key={`${message.role}-${index}-${message.text}`}
                              className={cn(
                                "max-w-[92%] rounded-2xl border px-4 py-3 text-xs font-semibold leading-relaxed",
                                message.role === "user"
                                  ? "ml-auto border-[#ff007f]/20 bg-[#ff007f]/10 text-pink-50"
                                  : "mr-auto border-white/10 bg-black/25 text-slate-300"
                              )}
                            >
                              <div className="mb-1 text-[8px] font-black uppercase tracking-widest text-slate-500">
                                {message.role === "user" ? "You" : "MIMIC"}
                              </div>
                              {message.text}
                            </div>
                          ))
                        )}
                      </div>
                      <textarea
                        value={textPrompt}
                        onChange={(e) => {
                          setTextPrompt(e.target.value);
                          setBriefApproved(false);
                          setBriefAnswers({});
                        }}
                        placeholder={brief ? "Add a correction or extra detail..." : "Tell MIMIC what you want. Example: quick fun uni edit, people first, happy captions, fast but readable."}
                        className="mt-4 h-24 w-full shrink-0 rounded-xl border border-white/10 bg-black/25 px-4 py-3 text-sm font-medium text-slate-300 placeholder:text-slate-700 outline-none resize-none custom-scrollbar leading-relaxed focus:border-[#ff007f]/40"
                      />
                      <div className="absolute -left-[9px] top-0 w-0 h-0 border-t-[10px] border-t-white/10 border-l-[10px] border-l-transparent" />
                      <div className="mt-4 flex items-center justify-between gap-3 border-t border-white/5 pt-4">
                        <span className="text-[8px] font-black uppercase tracking-widest text-slate-600">
                          {brief ? "Type a change, then update the brief" : "Send your first edit idea"}
                        </span>
                        <button
                          type="button"
                          onClick={() => buildCreativeBrief()}
                          disabled={isBriefing || !textPrompt.trim()}
                          className="h-9 px-4 rounded-xl bg-[#ff007f] text-white text-[9px] font-black uppercase tracking-widest hover:bg-[#ff2a94] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 shadow-[0_0_20px_rgba(255,0,127,0.25)]"
                        >
                          {isBriefing ? <Activity className="h-3.5 w-3.5 animate-spin" /> : <BrainCircuit className="h-3.5 w-3.5" />}
                          {brief ? "Send Update" : "Send to MIMIC"}
                        </button>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[#ff007f]/15 bg-black/25 p-4 min-h-[210px] overflow-y-auto custom-scrollbar">
                      {!brief ? (
                        <div className="h-full flex flex-col justify-center gap-4 text-slate-500">
                          <div className="h-10 w-10 rounded-2xl bg-[#ff007f]/10 border border-[#ff007f]/20 flex items-center justify-center">
                            <Sparkles className="h-5 w-5 text-[#ff007f]" />
                          </div>
                          <div>
                            <p className="text-sm font-black text-white">MIMIC will show the plan first.</p>
                            <p className="mt-2 text-xs leading-relaxed">
                              You can correct the vibe, pacing, clips, text, or music before anything renders.
                            </p>
                          </div>
                        </div>
                      ) : (
                        <div className="h-full flex flex-col gap-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-[9px] font-black uppercase tracking-[0.25em] text-[#ff65b5]">MIMIC understands</div>
                              <p className="mt-2 text-sm font-bold leading-snug text-white">{brief.summary}</p>
                            </div>
                            <span className={cn(
                              "shrink-0 rounded-full px-2.5 py-1 text-[8px] font-black uppercase tracking-widest border",
                              briefApproved
                                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                                : openBriefQuestions.length > 0
                                  ? "border-cyan-400/25 bg-cyan-400/10 text-cyan-200"
                                  : "border-amber-400/25 bg-amber-400/10 text-amber-300"
                            )}>
                              {briefApproved ? "Approved" : openBriefQuestions.length > 0 ? "Needs answers" : "Review"}
                            </span>
                          </div>

                          {(brief.assumptions?.length || 0) > 0 && (
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs">
                              <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Assumptions</div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {brief.assumptions?.map((assumption, index) => (
                                  <span key={`${assumption}-${index}`} className="rounded-full border border-white/10 bg-black/30 px-2 py-1 text-[10px] font-semibold text-slate-300">
                                    {assumption}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {resolvedBriefChoices.length > 0 && (
                            <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/[0.07] p-3 text-xs">
                              <div className="text-[8px] font-black uppercase tracking-widest text-emerald-300">Your choices applied</div>
                              <p className="mt-1 text-[11px] leading-relaxed text-emerald-50/75">
                                MIMIC rebuilt the plan and internal edit prompt using these answers.
                              </p>
                              <div className="mt-2 space-y-1.5">
                                {resolvedBriefChoices.map((choice, index) => (
                                  <div key={`${choice}-${index}`} className="rounded-lg border border-emerald-400/10 bg-black/20 px-3 py-2 text-[11px] font-semibold leading-relaxed text-emerald-50">
                                    {choice}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {Object.keys(visibleBriefIntake).length > 0 && (
                            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-xs">
                              <div className="flex items-center justify-between gap-3">
                                <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Edit intake</div>
                                <div className="text-[9px] font-bold text-slate-500">
                                  {openBriefQuestions.length > 0 ? "Needs decisions" : "Ready to approve"}
                                </div>
                              </div>
                              <div className="mt-3 grid grid-cols-1 2xl:grid-cols-2 gap-2">
                                {VISIBLE_INTAKE_FIELDS.map((field) => {
                                  const value = visibleBriefIntake[field];
                                  if (!value) return null;
                                  const confidence = briefIntakeConfidence[field] || "assumed";
                                  return (
                                    <div key={field} className="min-w-0 rounded-xl border border-white/10 bg-black/25 p-3">
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        <div className="min-w-0 text-[8px] font-black uppercase tracking-widest text-slate-500">{BRIEF_INTAKE_LABELS[field]}</div>
                                        <span className={cn(
                                          "shrink-0 rounded-full px-2 py-0.5 text-[8px] font-black uppercase tracking-widest border",
                                          confidence === "confirmed"
                                            ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
                                            : confidence === "missing"
                                              ? "border-amber-400/20 bg-amber-400/10 text-amber-300"
                                              : "border-slate-400/15 bg-slate-400/10 text-slate-400"
                                        )}>
                                          {confidence}
                                        </span>
                                      </div>
                                      <div className="mt-2 min-w-0 break-words text-[11px] font-semibold leading-relaxed text-slate-200">{value}</div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="rounded-xl bg-white/[0.04] border border-white/10 p-3">
                              <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Vibe</div>
                              <div className="mt-1 text-slate-200">{brief.vibe.join(", ")}</div>
                            </div>
                            <div className="rounded-xl bg-white/[0.04] border border-white/10 p-3">
                              <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Pacing</div>
                              <div className="mt-1 text-slate-200 line-clamp-2">{brief.pacing}</div>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                            <div className="rounded-xl bg-white/[0.04] border border-white/10 p-3">
                              <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Prefer</div>
                              <div className="mt-1 text-slate-200 line-clamp-2">{brief.clip_preferences.join(", ")}</div>
                            </div>
                            <div className="rounded-xl bg-white/[0.04] border border-white/10 p-3">
                              <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Avoid</div>
                              <div className="mt-1 text-slate-200 line-clamp-2">{brief.avoid.join(", ")}</div>
                            </div>
                          </div>

                          <div className="rounded-xl bg-white/[0.04] border border-white/10 p-3 text-xs">
                            <div className="text-[8px] font-black uppercase tracking-widest text-slate-500">Text + Music</div>
                            <div className="mt-1 text-slate-200 line-clamp-2">{brief.text_style} · {brief.music_direction}</div>
                          </div>

                          {openBriefQuestions.length > 0 && (
                            <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/[0.07] p-3 text-xs text-cyan-100 space-y-3">
                              <div>
                                <div className="text-[8px] font-black uppercase tracking-widest text-cyan-300">Quick alignment</div>
                                <p className="mt-1 text-[11px] leading-relaxed text-cyan-100/80">
                                  These choices change which clips MIMIC uses and how it cuts the reel.
                                </p>
                              </div>
                              {openBriefQuestions.map((question) => (
                                <div key={question.id} className="rounded-xl border border-white/10 bg-black/25 p-3">
                                  <div className="font-bold leading-snug text-white">{question.question}</div>
                                  {question.impact && (
                                    <div className="mt-1 text-[10px] leading-relaxed text-slate-400">{question.impact}</div>
                                  )}
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {(question.options && question.options.length > 0 ? question.options : ["Use MIMIC's best judgment"]).map((option) => {
                                      const selected = briefAnswers[question.id] === option;
                                      return (
                                        <button
                                          key={option}
                                          type="button"
                                          onClick={() => answerBriefQuestion(question.id, option)}
                                          className={cn(
                                            "rounded-full border px-3 py-1.5 text-[10px] font-bold transition-all",
                                            selected
                                              ? "border-cyan-300 bg-cyan-300 text-black"
                                              : "border-white/10 bg-white/[0.04] text-slate-300 hover:border-cyan-300/50 hover:text-white"
                                          )}
                                        >
                                          {option}
                                        </button>
                                      );
                                    })}
                                  </div>
                                </div>
                              ))}
                              <div className="grid grid-cols-2 gap-2">
                                <button
                                  type="button"
                                  onClick={useBriefDefaults}
                                  disabled={isBriefing}
                                  className="h-9 rounded-xl border border-white/10 bg-white/[0.04] text-[9px] font-black uppercase tracking-widest text-slate-200 hover:bg-white/[0.08] disabled:opacity-40"
                                >
                                  Smart Defaults
                                </button>
                                <button
                                  type="button"
                                  onClick={applyBriefAnswers}
                                  disabled={isBriefing || !allBriefQuestionsAnswered}
                                  className="h-9 rounded-xl bg-cyan-300 text-black text-[9px] font-black uppercase tracking-widest hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                  Apply Answers
                                </button>
                              </div>
                            </div>
                          )}

                          <div className="mt-auto grid grid-cols-2 gap-2 pt-1">
                            <button
                              type="button"
                              onClick={() => setBriefApproved(false)}
                              className="h-9 rounded-xl border border-white/10 bg-white/[0.04] text-[9px] font-black uppercase tracking-widest text-slate-300 hover:bg-white/[0.08]"
                            >
                              Keep Editing
                            </button>
                            <button
                              type="button"
                              onClick={approveBrief}
                              disabled={openBriefQuestions.length > 0}
                              className="h-9 rounded-xl bg-white text-black text-[9px] font-black uppercase tracking-widest hover:bg-[#ff007f] hover:text-white transition-all flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:text-black"
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              {openBriefQuestions.length > 0 ? "Answer First" : "Approve Plan"}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-4 border-t border-white/5">
                    <div className="flex gap-4">
                      <div className="flex items-center gap-2">
                        <div className={cn("h-1 w-1 rounded-full animate-pulse", briefApproved ? "bg-emerald-400" : textPrompt ? "bg-[#ff007f]" : "bg-slate-700")} />
                        <span className="text-[8px] font-black text-slate-600 uppercase tracking-widest">
                          {briefApproved ? "Approved brief ready" : brief ? "Plan needs approval" : "Brief assistant ready"}
                        </span>
                      </div>
                    </div>

                    <button
                      onClick={() => {
                        const input = document.createElement('input');
                        input.type = 'file';
                        input.accept = 'audio/*,video/mp4';
                        input.onchange = (e) => {
                          const file = (e.target as HTMLInputElement).files?.[0];
                          if (file) setMusicFile(file);
                        };
                        input.click();
                      }}
                      className={cn(
                        "px-4 py-2 rounded-xl border transition-all flex items-center gap-3 group/music",
                        musicFile ? "bg-indigo-500/10 border-indigo-500/40 text-indigo-400 shadow-[0_0_15px_rgba(99,102,241,0.1)]" : "bg-white/5 border-white/10 text-slate-500 hover:bg-white/10 hover:border-white/20"
                      )}
                    >
                      {musicFile ? <Zap className="h-3 w-3 animate-pulse" /> : <Plus className="h-3 w-3 group-hover/music:rotate-90 transition-transform" />}
                      <span className="text-[9px] font-black uppercase tracking-widest">
                        {musicFile ? musicFile.name.substring(0, 15) + "..." : "Add Soundtrack"}
                      </span>
                    </button>
                  </div>
                </div>

                {/* Video/Mimic Mode Layer */}
                <div
                  {...getRefProps()}
                  className={cn(
                    "col-start-1 row-start-1 flex flex-col items-center justify-center p-12 cursor-pointer group/drop transition-opacity duration-300",
                    activeMode === "video" ? "opacity-100 pointer-events-auto z-10" : "opacity-0 pointer-events-none z-0"
                  )}
                >
                  <input {...getRefInputProps()} />
                  {refFile ? (
                    <div className="absolute inset-0 group/video">
                      <video src={refVideoUrlRef.current || undefined} className="w-full h-full object-cover opacity-80" />
                      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover/video:opacity-100 transition-all flex flex-col items-center justify-center backdrop-blur-sm">
                        <div className="h-16 w-16 rounded-2xl bg-white/10 border border-white/20 flex items-center justify-center mb-4">
                          <Video className="h-8 w-8 text-cyan-400" />
                        </div>
                        <p className="text-xs font-black text-white uppercase tracking-[0.4em] mb-2">{refFile.name}</p>
                        <button
                          onClick={(e) => { e.stopPropagation(); setRefFile(null); }}
                          className="px-6 py-2 rounded-xl bg-red-600 text-white text-[10px] font-black uppercase tracking-widest hover:bg-red-500 transition-all shadow-2xl"
                        >
                          Replace Reference
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center space-y-6">
                      <div className="h-20 w-20 rounded-3xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mx-auto group-hover/drop:scale-110 group-hover/drop:bg-cyan-500 group-hover/drop:text-white transition-all duration-500 shadow-2xl">
                        <Upload className="h-8 w-8" />
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-black text-white uppercase tracking-[0.4em]">Bind Style Reference</p>
                        <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Drag and drop a video to mimic its DNA</p>
                      </div>
                      <div className="pt-4 flex items-center justify-center gap-3">
                        <div className="px-2 py-1 rounded bg-white/5 border border-white/10 text-[8px] font-black text-slate-500 uppercase">MP4</div>
                        <div className="px-2 py-1 rounded bg-white/5 border border-white/10 text-[8px] font-black text-slate-500 uppercase">MOV</div>
                        <div className="px-2 py-1 rounded bg-white/5 border border-white/10 text-[8px] font-black text-slate-500 uppercase">AVI</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 02. Source Injection - Glass Slate */}
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <div className="h-1.5 w-1.5 rounded-full bg-indigo-500 shadow-[0_0_12px_rgba(99,102,241,1)]" />
                <h3 className="text-[11px] font-black text-white uppercase tracking-[0.3em]">02. Source Injection</h3>
              </div>
              <div
                {...getMaterialProps()}
                className={cn(
                  "min-h-[200px] rounded-xl border transition-all duration-700 flex flex-col items-center justify-center cursor-pointer relative group overflow-hidden",
                  isMaterialDragActive ? "border-cyan-400 bg-cyan-500/10 glow-cyan" :
                    materialFiles.length > 0 ? "border-cyan-500/40 bg-white/[0.05] shadow-[0_0_20px_rgba(0,212,255,0.15)]" :
                      "border-white/10 bg-white/[0.03] hover:bg-white/[0.08] hover:border-cyan-500/30"
                )}
              >
                <input {...getMaterialInputProps()} />
                {materialFiles.length === 0 ? (
                  <div className="text-center space-y-4">
                    <div className="h-12 w-12 rounded-xl bg-white/5 border border-white/10 text-indigo-400/50 flex items-center justify-center mx-auto group-hover:bg-cyan-500 group-hover:text-white group-hover:border-cyan-400 transition-all">
                      <MonitorPlay className="h-6 w-6" />
                    </div>
                    <div>
                      <p className="text-[10px] font-black text-white uppercase tracking-widest mb-1 group-hover:text-cyan-400 transition-colors">Inject Raw Samples</p>
                      <p className="text-[8px] font-bold text-slate-600 uppercase tracking-widest">Multiple video assets</p>
                    </div>
                  </div>
                ) : (
                  <div className="w-full p-6">
                    <div className="grid grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
                      {materialFiles.map((file, i) => {
                        const previewUrl = previews[file.name + file.size];
                        return (
                          <div key={i} className="aspect-square rounded-xl bg-black border border-white/10 overflow-hidden relative group/item shadow-2xl flex items-center justify-center">
                            {previewUrl ? (
                              <Image
                                src={previewUrl}
                                alt={`Preview of ${file.name}`}
                                fill
                                sizes="(max-width: 768px) 25vw, 12vw"
                                unoptimized
                                className="object-cover opacity-90"
                              />
                            ) : isGenerating ? (
                              <div className="flex flex-col items-center justify-center gap-1">
                                <Video className="h-4 w-4 text-cyan-500 animate-pulse" />
                                <span className="text-[6px] font-black text-cyan-500 uppercase tracking-tighter">Processing</span>
                              </div>
                            ) : (
                              <div className="flex flex-col items-center justify-center gap-1">
                                <Video className="h-4 w-4 text-slate-500" />
                                <span className="text-[6px] font-black text-slate-500 uppercase tracking-tighter">Queued</span>
                              </div>
                            )}
                            <button onClick={(e) => { e.stopPropagation(); setMaterialFiles(prev => prev.filter((_, idx) => idx !== i)); }} className="absolute inset-0 bg-red-600 text-white opacity-0 group-hover/item:opacity-100 transition-opacity flex items-center justify-center backdrop-blur-sm shadow-xl z-10"><X className="h-4 w-4" /></button>
                          </div>
                        );
                      })}
                      <div className="aspect-square rounded-xl border border-dashed border-white/10 flex items-center justify-center text-slate-700 hover:border-indigo-500/40 transition-all bg-white/[0.02] active:scale-95 cursor-pointer" onClick={() => {
                        const input = document.createElement('input');
                        input.type = 'file';
                        input.multiple = true;
                        input.accept = 'video/*';
                        input.onchange = (e) => {
                          const files = (e.target as HTMLInputElement).files;
                          if (files) onDropMaterial(Array.from(files));
                        };
                        input.click();
                      }}><Plus className="h-4 w-4" /></div>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      <div className="px-2 py-0.5 rounded bg-indigo-500/20 text-[8px] font-black text-indigo-400 uppercase border border-indigo-500/20">{materialFiles.length} Streams Injected</div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Library Health Panel */}
            {libraryHealth && (
              <div className="glass-premium rounded-xl px-5 py-6 border border-white/5 bg-white/[0.01]">
                <div className="flex items-center gap-3 mb-4">
                  <Activity className="h-3.5 w-3.5 text-cyan-400" />
                  <h3 className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Library Health</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Avg Quality</p>
                    <p className="text-xl font-black text-white font-mono">{libraryHealth.avg_quality.toFixed(1)}<span className="text-[10px] text-slate-600 ml-1">/5</span></p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Asset Count</p>
                    <p className="text-xl font-black text-white font-mono">{libraryHealth.asset_count}</p>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-white/5">
                  <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest mb-2">Energy Distribution</p>
                  <div className="flex gap-1 h-1.5">
                    {['High', 'Medium', 'Low'].map(e => (
                      <div
                        key={e}
                        className={cn(
                          "h-full rounded-full transition-all duration-1000",
                          e === 'High' ? "bg-[#ff007f]" : e === 'Medium' ? "bg-cyan-400" : "bg-indigo-500"
                        )}
                        style={{ width: `${((libraryHealth.energy_distribution[e] || 0) / libraryHealth.asset_count) * 100}%` }}
                      />
                    ))}
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-white/5">
                  <div className="flex items-center justify-between">
                    <p className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Readiness Score</p>
                    <p className="text-[10px] font-black text-cyan-400 font-mono">{Math.round(libraryHealth.confidence_score)}%</p>
                  </div>
                  <div className="h-1 w-full bg-white/5 rounded-full mt-2 overflow-hidden">
                    <div className="h-full bg-cyan-400 transition-all duration-1000" style={{ width: `${libraryHealth.confidence_score}%` }} />
                  </div>
                </div>
              </div>
            )}

            {/* Blueprint Preview Panel */}
            {blueprint && (
              <div className="glass-premium rounded-xl px-5 py-6 border border-indigo-500/20 bg-indigo-500/[0.02] shadow-[0_0_30px_rgba(99,102,241,0.05)]">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <Layers className="h-3.5 w-3.5 text-indigo-400" />
                    <h3 className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Edit Plan</h3>
                  </div>
                  <div className="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-[8px] font-black text-indigo-400 uppercase tracking-widest">Locked In</div>
                </div>
                <div className="space-y-4">
                  <div className="space-y-1">
                    <p className="text-[8px] font-black text-indigo-500 uppercase tracking-widest">The Vibe</p>
                    <p className="text-[11px] font-bold text-slate-300 leading-relaxed uppercase tracking-tight italic">&quot;{blueprint.plan_summary || blueprint.narrative_message}&quot;</p>
                  </div>
                  <div className="space-y-2">
                    <p className="text-[8px] font-black text-indigo-500 uppercase tracking-widest">Story Arc</p>
                    <div className="flex gap-1 overflow-hidden rounded-lg h-8 border border-white/5">
                      {blueprint.segments?.map((seg, i: number) => (
                        <div
                          key={i}
                          className={cn(
                            "h-full flex items-center justify-center text-[7px] font-black transition-all",
                            seg.energy === 'High' ? "bg-[#ff007f] text-white" : seg.energy === 'Medium' ? "bg-cyan-500 text-black" : "bg-indigo-600 text-white"
                          )}
                          style={{ width: `${(seg.duration / blueprint.total_duration) * 100}%` }}
                          title={`${seg.arc_stage}: ${seg.energy}`}
                        >
                          {seg.duration > 1.5 && seg.arc_stage[0]}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Logic Sidebar - Command Center Layout */}
          <div className="space-y-6">
            <div className="glass-premium rounded-xl flex flex-col h-[600px] shadow-2xl border border-white/5 relative overflow-hidden group/telemetry">
              {/* Background Glow */}
              <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full blur-[60px] -mr-16 -mt-16 group-hover/telemetry:bg-cyan-500/20 transition-all duration-1000" />

              <div className="px-5 py-4 border-b border-indigo-500/10 flex items-center justify-between relative z-10">
                <div className="flex items-center gap-3 text-[10px] font-black text-white uppercase tracking-[0.2em]">
                  <Terminal className="h-3.5 w-3.5 text-cyan-400" />
                  <span>AI Reasoning</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {isGenerating && (
                    <div className="flex items-center gap-2 mr-2">
                      <div className="h-1 w-20 bg-white/5 rounded-full overflow-hidden border border-white/5">
                        <div className="h-full bg-cyan-400 transition-all duration-500" style={{ width: `${progress}%` }} />
                      </div>
                      <span className="text-[8px] font-mono text-cyan-400">{Math.round(progress)}%</span>
                    </div>
                  )}
                  <div className={cn("h-1.5 w-1.5 rounded-full glow-cyan", isGenerating ? "bg-cyan-400 animate-pulse" : generationError ? "bg-red-500" : "bg-slate-700")} />
                  <span className={cn("text-[8px] font-black uppercase tracking-widest", generationError ? "text-red-400" : "text-cyan-400/60")}>
                    {isGenerating ? "Processing" : generationError ? "Synthesis Failed" : "Idle"}
                  </span>
                  {generationError && (
                    <button
                      onClick={() => {
                        setGenerationError(false);
                        setIsGenerating(false);
                        setProgress(0);
                        setStatusMsg("Ready");
                      }}
                      className="ml-2 px-2 py-0.5 rounded bg-red-500/10 border border-red-500/20 text-[6px] font-black text-red-500 uppercase hover:bg-red-500/20 transition-all"
                    >
                      Reset Protocol
                    </button>
                  )}
                </div>
              </div>

              <div ref={scrollRef} className="flex-1 overflow-y-auto custom-scrollbar px-5 py-6 space-y-3 font-mono text-[14px] relative z-10 leading-relaxed bg-black/20 overscroll-contain">
                {logMessages.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center opacity-20">
                    <Activity className="h-8 w-8 mb-4 text-indigo-400 animate-pulse" />
                    <p className="font-black uppercase tracking-[0.4em] italic text-[10px]">Awaiting Protocol</p>
                  </div>
                ) : (
                  logMessages.slice(-100).map((msg, i) => (
                    <div key={i} className="flex gap-4 text-slate-400 hover:text-white transition-colors animate-in fade-in slide-in-from-left-2 duration-300">
                      <span className="text-indigo-500/40 shrink-0 select-none font-bold text-[10px] mt-1">{(i + 1).toString().padStart(2, '0')}</span>
                      <span className={cn("inline-block", msg.includes('ERROR') ? 'text-red-500' : msg.includes('GEMINI') ? 'text-cyan-400 font-bold' : '')}>{msg}</span>
                    </div>
                  ))
                )}
                <div />
              </div>

              {/* TACTICAL EXECUTE BUTTON - Permanent Adrenaline State */}
              <div className="p-5 bg-white/[0.02] border-t border-white/5 relative z-10">
                <button
                  onClick={startMimic}
                  disabled={!canExecute}
                  className={cn(
                    "w-full h-14 rounded-xl font-black text-[11px] uppercase tracking-[0.25em] transition-all duration-700 flex flex-col items-center justify-center relative overflow-hidden group/execute border",
                    isGenerating
                      ? "bg-gradient-to-r from-[#ff007f] to-[#bf00ff] border-[#ff007f]/40 text-white animate-pulse"
                      : generationError
                        ? "bg-red-600/20 border-red-500/50 text-red-400 shadow-[0_0_20px_rgba(239,68,68,0.2)] hover:bg-red-600/30"
                        : !canExecute || needsApprovedBrief
                          ? "bg-gradient-to-br from-indigo-500/10 to-cyan-500/10 border-cyan-500/20 text-slate-400 shadow-[0_0_20px_rgba(0,212,255,0.1)] hover:border-cyan-500/40"
                          : "bg-gradient-to-r from-[#00d4ff] via-[#4f46e5] to-[#bf00ff] bg-[length:200%_auto] border-white/30 text-white shadow-[0_0_30px_rgba(0,212,255,0.4)] hover:shadow-[0_0_60px_rgba(0,212,255,0.7)] hover:bg-right hover:scale-[1.02] active:scale-[0.98] animate-pulse-slow"
                  )}
                >
                  {/* Hover Label Layer */}
                  <div className="absolute inset-0 flex items-center justify-center transition-all duration-500 group-hover/execute:-translate-y-full">
                    <div className="flex items-center gap-3">
                      <Sparkles className={cn(
                        "h-4 w-4",
                        isGenerating || isIdLoading ? "text-white animate-spin-slow" :
                          generationError ? "text-red-400 animate-pulse" :
                            canExecute ? "text-white animate-spin-slow" : "text-cyan-400"
                      )} />
                      <span>
                        {isGenerating
                          ? "Synthesizing..."
                          : isIdLoading
                            ? "Binding Style..."
                            : generationError
                              ? "Retry Synthesis"
                              : needsApprovedBrief
                                ? "Approve Plan First"
                                : "Execute Synthesis"}
                      </span>
                    </div>
                  </div>

                  <div className="absolute inset-0 flex flex-col items-center justify-center translate-y-full transition-all duration-500 group-hover/execute:translate-y-0 bg-white/10 backdrop-blur-sm">
                    <span className="text-white">Initialize Gemini 3</span>
                    <span className="text-[8px] opacity-70 tracking-[0.4em] mt-1">Engine Port: 8000 // Primed</span>
                  </div>

                  {/* Charged Visual Effect */}
                  {refFile && materialFiles.length > 0 && !isGenerating && (
                    <div className="absolute inset-0 pointer-events-none">
                      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
                    </div>
                  )}
                </button>
              </div>
            </div>

          </div>
        </div>

        {/* System Protocol Description & Pipeline Preview */}
        <div className="rounded-2xl sm:rounded-[2.5rem] bg-white/[0.02] border border-white/5 p-5 sm:p-10 mt-8 sm:mt-12 space-y-8 sm:space-y-12 shadow-inner group/blueprint relative overflow-hidden">
          <div className="absolute top-0 left-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-[120px] -ml-32 -mt-32" />

          <div className="space-y-8 relative z-10">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-[11px] font-black text-indigo-400 uppercase tracking-[0.5em]">HOW MIMIC WORKS</h3>
                <p className="text-[9px] text-slate-600 uppercase tracking-[0.3em] mt-1">INTENT → EDIT → EXPLANATION</p>
              </div>
              <div className="flex gap-2">
                <div className="h-1 w-6 bg-indigo-500/20 rounded-full" />
                <div className="h-1 w-1 bg-indigo-500/40 rounded-full" />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12">
              <div className="space-y-3 group/bp card-glint p-4 -m-4 hover:border-cyan-500/30 transition-all duration-500">
                <h4 className="text-[11px] font-black text-white uppercase tracking-widest flex items-center gap-3">
                  <div className="h-4 w-4 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 group-hover/bp:bg-cyan-500 group-hover/bp:text-white transition-all duration-500 shadow-[0_0_10px_rgba(34,211,238,0.2)] group-hover/bp:shadow-[0_0_20px_rgba(34,211,238,0.4)]"><Layers className="h-2.5 w-2.5" /></div>
                  INTENT TRANSLATION
                </h4>
                <p className="text-[11px] text-slate-500 leading-relaxed font-bold uppercase tracking-tight group-hover/bp:text-slate-400 transition-colors">
                  MIMIC interprets creative intent—pace, emotion, and narrative arc—and converts it into a structured editorial plan.
                </p>
              </div>
              <div className="space-y-3 group/bp card-glint p-4 -m-4 hover:border-purple-500/30 transition-all duration-500">
                <h4 className="text-[11px] font-black text-white uppercase tracking-widest flex items-center gap-3">
                  <div className="h-4 w-4 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 group-hover/bp:bg-purple-500 group-hover/bp:text-white transition-all duration-500 shadow-[0_0_10px_rgba(191,0,255,0.2)] group-hover/bp:shadow-[0_0_191,0,255,0.4)]"><Zap className="h-2.5 w-2.5" /></div>
                  DETERMINISTIC EDIT EXECUTION
                </h4>
                <p className="text-[11px] text-slate-500 leading-relaxed font-bold uppercase tracking-tight group-hover/bp:text-slate-400 transition-colors">
                  The system selects clips, timings, and transitions under real-world constraints, then executes the edit.
                </p>
              </div>
              <div className="space-y-3 group/bp card-glint p-4 -m-4 hover:border-lime-500/30 transition-all duration-500">
                <h4 className="text-[11px] font-black text-white uppercase tracking-widest flex items-center gap-3">
                  <div className="h-4 w-4 rounded-lg bg-lime-500/10 border border-lime-500/20 flex items-center justify-center text-lime-400 group-hover/bp:bg-lime-500 group-hover/bp:text-white transition-all duration-500 shadow-[0_0_10px_rgba(204,255,0,0.2)] group-hover/bp:shadow-[0_0_204,255,0,0.4)]"><BrainCircuit className="h-2.5 w-2.5" /></div>
                  EXPLAINABLE DECISION MAKING
                </h4>
                <p className="text-[11px] text-slate-500 leading-relaxed font-bold uppercase tracking-tight group-hover/bp:text-slate-400 transition-colors">
                  Every cut is traceable. MIMIC exposes the reasoning behind its editorial decisions.
                </p>
              </div>
            </div>
          </div>

          {/* Pipeline Preview - Conditional Visibility (Active Processing Only) */}
          {isGenerating && (
            <div className="pt-8 border-t border-white/5 space-y-6 relative z-10 animate-in fade-in slide-in-from-bottom-2 duration-1000">
              <div className="flex items-center gap-3">
                <Activity className="h-3.5 w-3.5 text-cyan-400" />
                <p className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Signal Pipeline Architecture</p>
              </div>
              <div className="flex items-center gap-2">
                {[
                  { label: 'Ingestion', color: 'bg-indigo-500', active: true, progress: 100 },
                  { label: 'Temporal Map', color: 'bg-cyan-500', active: progress > 15, progress: progress > 30 ? 100 : (progress - 15) * 6.6 },
                  { label: 'Beat Alignment', color: 'bg-purple-500', active: progress > 40, progress: progress > 60 ? 100 : (progress - 40) * 5 },
                  { label: 'Logic Reasoning', color: 'bg-[#bf00ff]', active: progress > 70, progress: progress > 85 ? 100 : (progress - 70) * 6.6 },
                  { label: 'Final Synthesis', color: 'bg-lime-500', active: progress > 90, progress: (progress - 90) * 10 }
                ].map((step, i) => (
                  <div key={i} className="flex-1 flex flex-col gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-white/5 relative overflow-hidden">
                      {step.active && (
                        <div
                          className={cn("absolute inset-0 transition-all duration-1000", step.color)}
                          style={{ width: `${step.progress}%` }}
                        >
                          <div className="absolute inset-0 bg-white/30 animate-shimmer" />
                        </div>
                      )}
                    </div>
                    {i < 4 && <div className="h-0.5 w-full bg-white/5 hidden" />}
                    <div className="hidden lg:block">
                      <p className={cn(
                        "text-[8px] font-black uppercase tracking-widest transition-colors",
                        step.active ? "text-white" : "text-slate-700"
                      )}>
                        {step.label}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Tier 1 Feature: Pipeline Visualization Modal - REMOVED FOR BETTER UX */}
      </div>
    </div>
  );
}
