"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { VideoComparison } from "@/components/VideoComparison";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getDownloadUrl, getStatus } from "@/lib/api";

export default function ResultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: sessionId } = use(params);
  const [status, setStatus] = useState<unknown>(null);

  type StatusLike = {
    blueprint?: unknown;
  };

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const s = await getStatus(sessionId);
      if (!cancelled) setStatus(s);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const outputUrl = useMemo(() => getDownloadUrl(sessionId), [sessionId]);
  const referenceUrl = useMemo(() => {
    try {
      return sessionStorage.getItem(`mimic_reference_url_${sessionId}`) || "";
    } catch {
      return "";
    }
  }, [sessionId]);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-6 py-12 space-y-8">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-tight">🎉 Your Video is Ready!</h1>
            <p className="text-muted-foreground">Session: {sessionId}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button asChild>
              <a href={outputUrl}>Download</a>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/upload">New Project</Link>
            </Button>
          </div>
        </div>

        <Card className="bg-card border-border p-6 space-y-6">
          <VideoComparison referenceUrl={referenceUrl} outputUrl={outputUrl} />
        </Card>

        <Card className="bg-card border-border p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="font-semibold">🧠 AI Analysis</div>
            <Link href="/history" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              View History →
            </Link>
          </div>
          <Separator />
          <pre className="text-xs whitespace-pre-wrap text-muted-foreground">
            {status
              ? JSON.stringify(((status as StatusLike).blueprint ?? status), null, 2)
              : "Loading..."}
          </pre>
        </Card>
      </div>
    </main>
  );
}


