"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { DiscoveryStep } from "@/lib/types";
import { cn } from "@/lib/utils";

interface PipelineProgressProps {
  currentStep: DiscoveryStep;
  toolsFound: number;
}

const steps: { key: DiscoveryStep; label: string; description: string }[] = [
  { key: "first_pass", label: "First Pass", description: "Discovering new tools" },
  { key: "second_pass", label: "Second Pass", description: "Validating & enriching" },
  { key: "third_pass", label: "Third Pass", description: "Finding videos" },
  { key: "complete", label: "Complete", description: "Pipeline finished" },
];

function getStepStatus(step: DiscoveryStep, currentStep: DiscoveryStep): "pending" | "active" | "complete" {
  const stepOrder = ["idle", "first_pass", "second_pass", "third_pass", "complete"];
  const stepIndex = stepOrder.indexOf(step);
  const currentIndex = stepOrder.indexOf(currentStep);

  if (currentStep === "complete") return "complete";
  if (stepIndex < currentIndex) return "complete";
  if (stepIndex === currentIndex) return "active";
  return "pending";
}

function getProgressPercentage(currentStep: DiscoveryStep): number {
  switch (currentStep) {
    case "idle":
      return 0;
    case "first_pass":
      return 25;
    case "second_pass":
      return 50;
    case "third_pass":
      return 75;
    case "complete":
      return 100;
    default:
      return 0;
  }
}

export function PipelineProgress({ currentStep, toolsFound }: PipelineProgressProps) {
  const progress = getProgressPercentage(currentStep);

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-foreground">Pipeline Progress</CardTitle>
            <CardDescription className="text-muted-foreground">
              {currentStep === "idle"
                ? "Ready to start discovery"
                : currentStep === "complete"
                ? "Discovery complete!"
                : "Running discovery pipeline..."}
            </CardDescription>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-foreground">{toolsFound}</div>
            <div className="text-xs text-muted-foreground">tools found</div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <Progress value={progress} className="h-2 bg-secondary" />

        <div className="grid gap-4 sm:grid-cols-4">
          {steps.map((step) => {
            const status = getStepStatus(step.key, currentStep);
            return (
              <div
                key={step.key}
                className={cn(
                  "flex items-start gap-3 rounded-lg p-3 transition-colors",
                  status === "active" && "bg-secondary",
                  status === "complete" && "opacity-60"
                )}
              >
                <div className="mt-0.5">
                  {status === "complete" ? (
                    <CheckCircle2 className="h-5 w-5 text-chart-2" />
                  ) : status === "active" ? (
                    <Loader2 className="h-5 w-5 animate-spin text-chart-1" />
                  ) : (
                    <Circle className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
                <div>
                  <div className="font-medium text-foreground">{step.label}</div>
                  <div className="text-xs text-muted-foreground">{step.description}</div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
