"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Navigation } from "@/components/navigation";
import { CategorySelector } from "@/components/discover/category-selector";
import { PipelineProgress } from "@/components/discover/pipeline-progress";
import { DiscoveryLog } from "@/components/discover/discovery-log";
import { ResultsTable } from "@/components/discover/results-table";
import { Button } from "@/components/ui/button";
import { Play, Square } from "lucide-react";
import { AT_CATEGORIES } from "@/lib/types";
import type { ATCategory, ATTool, DiscoveryJob, DiscoveryStep, LogEntry } from "@/lib/types";

export default function DiscoverPage() {
  const [selectedCategories, setSelectedCategories] = useState<ATCategory[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState<DiscoveryStep>("idle");
  const [tools, setTools] = useState<ATTool[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const handleCategoryToggle = useCallback((category: ATCategory) => {
    setSelectedCategories((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category]
    );
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedCategories([...AT_CATEGORIES]);
  }, []);

  const handleClearAll = useCallback(() => {
    setSelectedCategories([]);
  }, []);

  const pollJobStatus = useCallback(async (id: string) => {
    try {
      const response = await fetch(`/api/discover/status/${id}`);
      if (!response.ok) return;

      const job: DiscoveryJob = await response.json();
      
      setCurrentStep(job.currentStep);
      setTools(job.toolsFound);
      setLogs(job.logs);

      if (job.status === "completed" || job.status === "failed") {
        setIsRunning(false);
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    } catch (error) {
      console.error("Error polling job status:", error);
    }
  }, []);

  const startDiscovery = async () => {
    if (selectedCategories.length === 0) return;

    setIsRunning(true);
    setCurrentStep("first_pass");
    setTools([]);
    setLogs([]);

    try {
      const response = await fetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categories: selectedCategories }),
      });

      if (!response.ok) {
        throw new Error("Failed to start discovery");
      }

      const { jobId: newJobId } = await response.json();
      setJobId(newJobId);

      // Start polling for updates
      pollingRef.current = setInterval(() => {
        pollJobStatus(newJobId);
      }, 2000);
    } catch (error) {
      console.error("Error starting discovery:", error);
      setIsRunning(false);
      setCurrentStep("idle");
      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          level: "error",
          message: error instanceof Error ? error.message : "Failed to start discovery",
        },
      ]);
    }
  };

  const stopDiscovery = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setIsRunning(false);
    setCurrentStep("idle");
  };

  const handleExportToSheets = async () => {
    if (tools.length === 0) return;

    setIsExporting(true);
    try {
      const response = await fetch("/api/sheets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tools }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Failed to export to sheets");
      }

      const result = await response.json();
      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          level: "success",
          message: result.message,
        },
      ]);
    } catch (error) {
      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          level: "error",
          message: error instanceof Error ? error.message : "Failed to export to sheets",
        },
      ]);
    } finally {
      setIsExporting(false);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Tool Discovery</h1>
            <p className="text-muted-foreground">
              AI-powered discovery of assistive technology tools
            </p>
          </div>
          <div className="flex gap-3">
            {isRunning ? (
              <Button
                onClick={stopDiscovery}
                variant="outline"
                className="border-destructive text-destructive hover:bg-destructive/10"
              >
                <Square className="mr-2 h-4 w-4" />
                Stop
              </Button>
            ) : (
              <Button
                onClick={startDiscovery}
                disabled={selectedCategories.length === 0}
                className="bg-primary text-primary-foreground hover:bg-primary/90"
              >
                <Play className="mr-2 h-4 w-4" />
                Start Discovery
              </Button>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <CategorySelector
            selectedCategories={selectedCategories}
            onCategoryToggle={handleCategoryToggle}
            onSelectAll={handleSelectAll}
            onClearAll={handleClearAll}
            disabled={isRunning}
          />

          {(isRunning || currentStep !== "idle") && (
            <PipelineProgress currentStep={currentStep} toolsFound={tools.length} />
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <DiscoveryLog logs={logs} />
            <ResultsTable
              tools={tools}
              onExportToSheets={handleExportToSheets}
              isExporting={isExporting}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
