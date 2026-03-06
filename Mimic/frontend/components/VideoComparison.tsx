"use client";

import { useRef, useState } from "react";
import { Play, Pause } from "lucide-react";
import { Button } from "@/components/ui/button";

interface VideoComparisonProps {
  referenceUrl: string;
  outputUrl: string;
}

export function VideoComparison({ referenceUrl, outputUrl }: VideoComparisonProps) {
  const refVideoRef = useRef<HTMLVideoElement>(null);
  const outputVideoRef = useRef<HTMLVideoElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const togglePlay = () => {
    if (isPlaying) {
      refVideoRef.current?.pause();
      outputVideoRef.current?.pause();
    } else {
      refVideoRef.current?.play();
      if (syncEnabled) outputVideoRef.current?.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleSyncSeek = (time: number) => {
    if (refVideoRef.current) refVideoRef.current.currentTime = time;
    if (syncEnabled && outputVideoRef.current) outputVideoRef.current.currentTime = time;
    setCurrentTime(time);
  };

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-2 gap-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">📹 Reference Structure</h3>
          </div>
          <div className="relative aspect-video bg-black rounded-lg overflow-hidden border border-border">
            <video
              ref={refVideoRef}
              src={referenceUrl}
              className="w-full h-full"
              onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
              onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
              controls={false}
            />
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">✨ Your Generated Video</h3>
          </div>
          <div className="relative aspect-video bg-black rounded-lg overflow-hidden border border-border">
            <video ref={outputVideoRef} src={outputUrl} className="w-full h-full" controls={false} />
          </div>
        </div>
      </div>

      <div className="flex flex-col items-center gap-4">
        <div className="flex items-center justify-center gap-4">
          <Button onClick={togglePlay} size="lg" className="w-32">
            {isPlaying ? <Pause className="w-5 h-5 mr-2" /> : <Play className="w-5 h-5 mr-2" />}
            {isPlaying ? "Pause" : "Play"}
          </Button>

          <Button
            variant={syncEnabled ? "default" : "secondary"}
            onClick={() => setSyncEnabled(!syncEnabled)}
          >
            Sync Playback
          </Button>
        </div>

        <div className="w-full max-w-xl">
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.1}
            value={currentTime}
            onChange={(e) => handleSyncSeek(Number(e.target.value))}
            className="w-full"
          />
          <p className="text-center text-sm text-muted-foreground mt-2">
            {Math.floor(currentTime)}s / {Math.floor(duration)}s
          </p>
        </div>
      </div>
    </div>
  );
}


