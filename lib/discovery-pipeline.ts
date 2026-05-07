import type { ATTool, DiscoveryJob, LogEntry, DiscoveryStep } from "./types";
import { discoverToolsForCategory, validateAndEnrichTool, findYouTubeVideo } from "./gemini";

// In-memory store for discovery jobs (in production, use Redis or a database)
const jobs = new Map<string, DiscoveryJob>();

export function createJob(categories: string[]): DiscoveryJob {
  const id = `job_${Date.now()}_${Math.random().toString(36).substring(7)}`;
  const job: DiscoveryJob = {
    id,
    status: "pending",
    categories,
    currentStep: "idle",
    toolsFound: [],
    logs: [],
    startedAt: new Date().toISOString(),
  };
  jobs.set(id, job);
  return job;
}

export function getJob(id: string): DiscoveryJob | undefined {
  return jobs.get(id);
}

export function updateJob(id: string, updates: Partial<DiscoveryJob>): void {
  const job = jobs.get(id);
  if (job) {
    Object.assign(job, updates);
  }
}

export function addLog(id: string, level: LogEntry["level"], message: string): void {
  const job = jobs.get(id);
  if (job) {
    job.logs.push({
      timestamp: new Date().toISOString(),
      level,
      message,
    });
  }
}

export function setStep(id: string, step: DiscoveryStep): void {
  const job = jobs.get(id);
  if (job) {
    job.currentStep = step;
  }
}

function parseJsonSafe(text: string): unknown {
  // Remove markdown code blocks if present
  let cleaned = text.trim();
  if (cleaned.startsWith("```json")) {
    cleaned = cleaned.slice(7);
  } else if (cleaned.startsWith("```")) {
    cleaned = cleaned.slice(3);
  }
  if (cleaned.endsWith("```")) {
    cleaned = cleaned.slice(0, -3);
  }
  cleaned = cleaned.trim();
  
  try {
    return JSON.parse(cleaned);
  } catch {
    console.error("Failed to parse JSON:", cleaned.substring(0, 200));
    return null;
  }
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function runFirstPass(
  jobId: string,
  categories: string[],
  onProgress?: (tool: ATTool) => void
): Promise<ATTool[]> {
  setStep(jobId, "first_pass");
  addLog(jobId, "info", `Starting first pass for ${categories.length} categories`);
  
  const allTools: ATTool[] = [];
  const existingNames: string[] = [];

  for (const category of categories) {
    addLog(jobId, "info", `Searching category: ${category}`);
    
    try {
      const response = await discoverToolsForCategory(category, existingNames);
      const parsed = parseJsonSafe(response);
      
      if (Array.isArray(parsed)) {
        for (const tool of parsed) {
          if (tool.name && tool.website) {
            const atTool: ATTool = {
              name: tool.name,
              description: tool.description || "",
              category: tool.category || category,
              website: tool.website,
              pricing: tool.pricing || "Unknown",
              platforms: Array.isArray(tool.platforms) ? tool.platforms : [],
              aiVerified: false,
              humanVerified: false,
            };
            allTools.push(atTool);
            existingNames.push(tool.name);
            addLog(jobId, "success", `Found: ${tool.name}`);
            onProgress?.(atTool);
          }
        }
      }
    } catch (error) {
      addLog(jobId, "error", `Error in category ${category}: ${error instanceof Error ? error.message : "Unknown error"}`);
    }

    // Rate limiting - wait between categories
    await delay(2000);
  }

  addLog(jobId, "info", `First pass complete. Found ${allTools.length} tools.`);
  return allTools;
}

export async function runSecondPass(
  jobId: string,
  tools: ATTool[],
  onProgress?: (tool: ATTool, index: number) => void
): Promise<ATTool[]> {
  setStep(jobId, "second_pass");
  addLog(jobId, "info", `Starting second pass: validating ${tools.length} tools`);
  
  const validatedTools: ATTool[] = [];

  for (let i = 0; i < tools.length; i++) {
    const tool = tools[i];
    addLog(jobId, "info", `Validating: ${tool.name} (${i + 1}/${tools.length})`);

    try {
      const response = await validateAndEnrichTool(tool);
      const parsed = parseJsonSafe(response) as {
        isValid?: boolean;
        name?: string;
        description?: string;
        category?: string;
        website?: string;
        pricing?: string;
        platforms?: string[];
      } | null;

      if (parsed?.isValid !== false) {
        const validatedTool: ATTool = {
          ...tool,
          name: parsed?.name || tool.name,
          description: parsed?.description || tool.description,
          category: parsed?.category || tool.category,
          website: parsed?.website || tool.website,
          pricing: (parsed?.pricing as ATTool["pricing"]) || tool.pricing,
          platforms: parsed?.platforms || tool.platforms,
          aiVerified: true,
        };
        validatedTools.push(validatedTool);
        addLog(jobId, "success", `Validated: ${validatedTool.name}`);
        onProgress?.(validatedTool, i);
      } else {
        addLog(jobId, "warning", `Skipped invalid tool: ${tool.name}`);
      }
    } catch (error) {
      addLog(jobId, "error", `Error validating ${tool.name}: ${error instanceof Error ? error.message : "Unknown error"}`);
      // Keep the tool but mark as not AI verified
      validatedTools.push(tool);
    }

    // Rate limiting
    await delay(1500);
  }

  addLog(jobId, "info", `Second pass complete. ${validatedTools.length} tools validated.`);
  return validatedTools;
}

export async function runThirdPass(
  jobId: string,
  tools: ATTool[],
  onProgress?: (tool: ATTool, index: number) => void
): Promise<ATTool[]> {
  setStep(jobId, "third_pass");
  addLog(jobId, "info", `Starting third pass: finding YouTube videos for ${tools.length} tools`);
  
  const enrichedTools: ATTool[] = [];

  for (let i = 0; i < tools.length; i++) {
    const tool = tools[i];
    addLog(jobId, "info", `Finding video for: ${tool.name} (${i + 1}/${tools.length})`);

    try {
      const response = await findYouTubeVideo(tool.name, tool.category);
      const parsed = parseJsonSafe(response) as {
        found?: boolean;
        videoUrl?: string | null;
      } | null;

      const enrichedTool: ATTool = {
        ...tool,
        youtubeVideo: parsed?.found && parsed?.videoUrl ? parsed.videoUrl : undefined,
      };
      enrichedTools.push(enrichedTool);
      
      if (parsed?.found) {
        addLog(jobId, "success", `Found video for: ${tool.name}`);
      } else {
        addLog(jobId, "info", `No video found for: ${tool.name}`);
      }
      onProgress?.(enrichedTool, i);
    } catch (error) {
      addLog(jobId, "error", `Error finding video for ${tool.name}: ${error instanceof Error ? error.message : "Unknown error"}`);
      enrichedTools.push(tool);
    }

    // Rate limiting
    await delay(1000);
  }

  addLog(jobId, "info", `Third pass complete. Pipeline finished!`);
  return enrichedTools;
}

export async function runFullPipeline(
  jobId: string,
  categories: string[],
  onToolFound?: (tool: ATTool) => void,
  onStepChange?: (step: DiscoveryStep) => void
): Promise<ATTool[]> {
  const job = getJob(jobId);
  if (!job) throw new Error("Job not found");

  updateJob(jobId, { status: "running" });

  try {
    // First Pass
    onStepChange?.("first_pass");
    const firstPassTools = await runFirstPass(jobId, categories, onToolFound);
    updateJob(jobId, { toolsFound: firstPassTools });

    // Second Pass
    onStepChange?.("second_pass");
    const secondPassTools = await runSecondPass(jobId, firstPassTools, (tool) => {
      onToolFound?.(tool);
    });
    updateJob(jobId, { toolsFound: secondPassTools });

    // Third Pass
    onStepChange?.("third_pass");
    const finalTools = await runThirdPass(jobId, secondPassTools, (tool) => {
      onToolFound?.(tool);
    });
    
    // Complete
    onStepChange?.("complete");
    updateJob(jobId, {
      status: "completed",
      toolsFound: finalTools,
      currentStep: "complete",
      completedAt: new Date().toISOString(),
    });

    return finalTools;
  } catch (error) {
    updateJob(jobId, {
      status: "failed",
      error: error instanceof Error ? error.message : "Unknown error",
    });
    throw error;
  }
}
