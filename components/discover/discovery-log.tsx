"use client";

import { useEffect, useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { LogEntry } from "@/lib/types";

interface DiscoveryLogProps {
  logs: LogEntry[];
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function DiscoveryLog({ logs }: DiscoveryLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-foreground">Discovery Log</CardTitle>
        <CardDescription className="text-muted-foreground">
          Real-time updates from the pipeline
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[300px] rounded-md border border-border bg-background p-4" ref={scrollRef}>
          {logs.length === 0 ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              No logs yet. Start a discovery to see progress.
            </div>
          ) : (
            <div className="space-y-2 font-mono text-sm">
              {logs.map((log, index) => (
                <div key={index} className="flex gap-3">
                  <span className="shrink-0 text-muted-foreground">
                    {formatTime(log.timestamp)}
                  </span>
                  <span
                    className={cn(
                      "shrink-0 w-16",
                      log.level === "success" && "text-chart-2",
                      log.level === "error" && "text-destructive",
                      log.level === "warning" && "text-chart-3",
                      log.level === "info" && "text-chart-1"
                    )}
                  >
                    [{log.level.toUpperCase()}]
                  </span>
                  <span className="text-foreground">{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
