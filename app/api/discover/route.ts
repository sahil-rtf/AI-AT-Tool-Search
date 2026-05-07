import { NextResponse } from "next/server";
import { createJob, runFullPipeline, updateJob } from "@/lib/discovery-pipeline";
import type { ATCategory } from "@/lib/types";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { categories } = body as { categories: ATCategory[] };

    if (!categories || !Array.isArray(categories) || categories.length === 0) {
      return NextResponse.json(
        { error: "Please select at least one category" },
        { status: 400 }
      );
    }

    // Create a new job
    const job = createJob(categories);

    // Start the pipeline in the background
    runFullPipeline(job.id, categories).catch((error) => {
      console.error("Pipeline error:", error);
      updateJob(job.id, {
        status: "failed",
        error: error instanceof Error ? error.message : "Unknown error",
      });
    });

    return NextResponse.json({
      jobId: job.id,
      message: "Discovery pipeline started",
    });
  } catch (error) {
    console.error("Error starting discovery:", error);
    return NextResponse.json(
      { error: "Failed to start discovery pipeline" },
      { status: 500 }
    );
  }
}
