export interface ATTool {
  id?: string;
  name: string;
  description: string;
  category: string;
  website: string;
  pricing: "Free" | "Paid" | "Freemium" | "Unknown";
  platforms: string[];
  youtubeVideo?: string;
  aiVerified: boolean;
  humanVerified: boolean;
  dateAdded?: string;
}

export interface DiscoveryJob {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  categories: string[];
  currentStep: DiscoveryStep;
  toolsFound: ATTool[];
  logs: LogEntry[];
  startedAt: string;
  completedAt?: string;
  error?: string;
}

export type DiscoveryStep = 
  | "idle"
  | "first_pass"
  | "second_pass" 
  | "third_pass"
  | "complete";

export interface LogEntry {
  timestamp: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
}

export interface AnalyticsData {
  totalTools: number;
  toolsByCategory: Record<string, number>;
  toolsByPricing: Record<string, number>;
  toolsByPlatform: Record<string, number>;
  recentTools: ATTool[];
}

export const AT_CATEGORIES = [
  "Alternative and Augmentative Communication (AAC)",
  "Screen Readers and Text-to-Speech",
  "Speech Recognition and Voice Control",
  "Magnification and Visual Enhancements",
  "Reading and Literacy Support",
  "Writing and Typing Assistance",
  "Hearing Assistance and Captioning",
  "Motor and Mobility Assistance",
  "Cognitive and Learning Support",
  "Switch Access and Alternative Input",
  "Braille Technology",
  "Environmental Control and Smart Home",
] as const;

export type ATCategory = typeof AT_CATEGORIES[number];
