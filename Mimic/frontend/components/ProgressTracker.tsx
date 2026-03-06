"use client";

import { useEffect, useMemo, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

interface ProgressStep {
  id: string;
  title: string;
  subtitle?: string;
  status: "pending" | "active" | "complete" | "error";
}

interface ProgressTrackerProps {
  sessionId: string;
}

export function ProgressTracker({ sessionId }: ProgressTrackerProps) {
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState("");
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const baseSteps = useMemo<ProgressStep[]>(
    () => [
      { id: "analyze_ref", title: "Analyzing reference", status: "pending" },
      { id: "analyze_clips", title: "Analyzing clips", status: "pending" },
      { id: "matching", title: "Creating sequence", status: "pending" },
      { id: "rendering", title: "Rendering video", status: "pending" },
      { id: "complete", title: "Finishing up", status: "pending" },
    ],
    []
  );

  const [steps, setSteps] = useState<ProgressStep[]>(baseSteps);

  useEffect(() => {
    if (!sessionId || sessionId === "undefined") return;

    let ws: WebSocket | null = null;
    let reconnectTimeout: NodeJS.Timeout | null = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;

    const connect = () => {
      try {
        const wsUrl = `ws://localhost:8000/ws/progress/${sessionId}`;
        console.log("Connecting to WebSocket:", wsUrl);
        console.log("Session ID:", sessionId);

        // Verify session exists before connecting
        if (!sessionId || sessionId === "undefined" || sessionId === "null") {
          console.error("Invalid session ID, cannot connect WebSocket");
          return;
        }

        // Verify WebSocket URL is valid
        if (!wsUrl || !wsUrl.startsWith("ws://") && !wsUrl.startsWith("wss://")) {
          console.error("Invalid WebSocket URL:", wsUrl);
          setConnectionError("Invalid WebSocket URL. Check API configuration.");
          return;
        }

        console.log("Creating WebSocket connection...");
        ws = api.connectProgress(sessionId);
        if (!ws) return;

        ws.onopen = () => {
          console.log("WebSocket connected successfully");
          reconnectAttempts = 0;
          setConnectionError(null);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            const p = Math.max(0, Math.min(1, Number(data.progress ?? 0)));
            setProgress(p * 100);
            setCurrentStep(String(data.message ?? ""));

            setSteps((prev) => {
              const currentActiveIndex = Math.min(Math.floor(p * prev.length), prev.length - 1);

              return prev.map((step, index) => {
                if (index < currentActiveIndex) return { ...step, status: "complete" as const };
                if (index === currentActiveIndex) return { ...step, status: "active" as const };
                return { ...step, status: "pending" as const };
              });
            });

            if (data.status === "complete" || data.status === "error") {
              ws?.close(1000, "Done");
            }
          } catch (e) {
            console.error("WebSocket message parse error:", e);
          }
        };

        ws.onerror = (error) => {
          console.error("WebSocket error:", error);
          console.error("WebSocket state:", ws?.readyState);
          console.error("WebSocket URL:", wsUrl);
          console.error("Session ID:", sessionId);

          // WebSocket errors don't provide detailed info, but we can check the state
          if (ws?.readyState === WebSocket.CLOSED) {
            const errorMsg = `Cannot connect to ${wsUrl}. Make sure backend is running on port 8000.`;
            console.error(errorMsg);
            setConnectionError(errorMsg);
          } else {
            setConnectionError("WebSocket connection failed. Check console for details.");
          }
        };

        ws.onclose = (event) => {
          console.log("WebSocket closed", event.code, event.reason);

          if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            console.log(`Reconnecting WebSocket (attempt ${reconnectAttempts}/${maxReconnectAttempts})...`);
            reconnectTimeout = setTimeout(connect, 2000);
          }
        };
      } catch (error) {
        console.error("Failed to create WebSocket:", error);
        if (reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++;
          reconnectTimeout = setTimeout(connect, 2000);
        }
      }
    };

    // Wait a bit longer for session to be created and generation to start
    setTimeout(connect, 1500);

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close(1000, "Component unmounted");
      }
    };
  }, [sessionId]);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold">Creating Your Video...</h3>
          <span className="text-sm text-muted-foreground">{Math.round(progress)}%</span>
        </div>
        <Progress value={progress} className="h-2" />
        {currentStep && (
          <p className="mt-2 text-sm text-muted-foreground">{currentStep}</p>
        )}
        {connectionError && (
          <p className="mt-2 text-sm text-red-500">{connectionError}</p>
        )}
      </div>

      <div className="space-y-3">
        {steps.map((step) => (
          <div key={step.id} className="flex items-start gap-3">
            <div className="mt-0.5">
              {step.status === "complete" && (
                <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center">
                  <Check className="w-3 h-3 text-white" />
                </div>
              )}
              {step.status === "active" && (
                <Loader2 className="w-5 h-5 text-primary animate-spin" />
              )}
              {step.status === "pending" && (
                <div className="w-5 h-5 rounded-full border-2 border-border" />
              )}
            </div>
            <div>
              <p
                className={[
                  "font-medium",
                  step.status === "complete"
                    ? "text-emerald-500"
                    : step.status === "active"
                      ? "text-primary"
                      : "text-muted-foreground",
                ].join(" ")}
              >
                {step.title}
              </p>
              {step.subtitle && (
                <p className="text-sm text-muted-foreground">{step.subtitle}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


