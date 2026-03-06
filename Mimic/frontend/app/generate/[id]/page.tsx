"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ProgressTracker } from "@/components/ProgressTracker";
import { Button } from "@/components/ui/button";
import { generateVideo, getStatus } from "@/lib/api";
import { toast } from "sonner";

export default function GeneratePage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const { id: sessionId } = use(params);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      if (started || !sessionId || sessionId === "undefined") return;
      setStarted(true);
      try {
        const result = await generateVideo(sessionId);
        console.log("Generation started:", result);
      } catch (e: unknown) {
        console.error("Failed to start generation:", e);
        // Don't reset started - prevent infinite retry loop
        const msg = e instanceof Error ? e.message : "Failed to start generation. Please try uploading again.";
        toast.error(msg);
      }
    }

    start();

    const interval = setInterval(async () => {
      if (!sessionId || sessionId === "undefined") return;
      try {
        const status = await getStatus(sessionId);
        if (cancelled) return;

        if (status.status === "complete") {
          clearInterval(interval);
          router.push(`/result/${sessionId}`);
        }

        if (status.status === "error") {
          clearInterval(interval);
          toast.error(status.error || "Generation failed");
        }
      } catch {
        // ignore transient errors
      }
    }, 1000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [router, sessionId, started]);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-6 py-16 space-y-10">
        <div className="flex items-center justify-end">
          <Button variant="secondary" onClick={() => router.push("/upload")}>
            Cancel
          </Button>
        </div>
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">✨ Creating Your Video...</h1>
          <p className="text-muted-foreground">Powered by Gemini 3 Flash Preview</p>
        </div>
        <ProgressTracker sessionId={sessionId} />
      </div>
    </main>
  );
}