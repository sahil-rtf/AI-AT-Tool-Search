import { NextResponse } from "next/server";
import { fetchToolsFromSheet } from "@/lib/sheets";
import type { AnalyticsData } from "@/lib/types";

export async function GET() {
  try {
    const spreadsheetId = process.env.GOOGLE_SHEETS_ID;

    if (!spreadsheetId) {
      // Return mock data if no spreadsheet is configured
      return NextResponse.json(getMockAnalytics());
    }

    const tools = await fetchToolsFromSheet(spreadsheetId);

    // Calculate analytics
    const toolsByCategory: Record<string, number> = {};
    const toolsByPricing: Record<string, number> = {};
    const toolsByPlatform: Record<string, number> = {};

    for (const tool of tools) {
      // Category
      toolsByCategory[tool.category] = (toolsByCategory[tool.category] || 0) + 1;

      // Pricing
      toolsByPricing[tool.pricing] = (toolsByPricing[tool.pricing] || 0) + 1;

      // Platforms
      for (const platform of tool.platforms) {
        toolsByPlatform[platform] = (toolsByPlatform[platform] || 0) + 1;
      }
    }

    // Get recent tools (last 10)
    const recentTools = tools.slice(-10).reverse();

    const analytics: AnalyticsData = {
      totalTools: tools.length,
      toolsByCategory,
      toolsByPricing,
      toolsByPlatform,
      recentTools,
    };

    return NextResponse.json(analytics);
  } catch (error) {
    console.error("Error fetching analytics:", error);
    // Return mock data on error
    return NextResponse.json(getMockAnalytics());
  }
}

function getMockAnalytics(): AnalyticsData {
  return {
    totalTools: 156,
    toolsByCategory: {
      "Alternative and Augmentative Communication (AAC)": 24,
      "Screen Readers and Text-to-Speech": 18,
      "Speech Recognition and Voice Control": 15,
      "Magnification and Visual Enhancements": 12,
      "Reading and Literacy Support": 22,
      "Writing and Typing Assistance": 19,
      "Hearing Assistance and Captioning": 14,
      "Motor and Mobility Assistance": 8,
      "Cognitive and Learning Support": 16,
      "Switch Access and Alternative Input": 5,
      "Braille Technology": 3,
    },
    toolsByPricing: {
      Free: 52,
      Freemium: 68,
      Paid: 36,
    },
    toolsByPlatform: {
      iOS: 89,
      Android: 72,
      Web: 104,
      Windows: 65,
      Mac: 48,
    },
    recentTools: [
      {
        name: "Proloquo2Go",
        description: "AAC app for people who cannot speak",
        category: "Alternative and Augmentative Communication (AAC)",
        website: "https://www.assistiveware.com/products/proloquo2go",
        pricing: "Paid",
        platforms: ["iOS"],
        aiVerified: true,
        humanVerified: true,
        dateAdded: "2024-01-15",
      },
      {
        name: "NVDA",
        description: "Free, open source screen reader for Windows",
        category: "Screen Readers and Text-to-Speech",
        website: "https://www.nvaccess.org/",
        pricing: "Free",
        platforms: ["Windows"],
        aiVerified: true,
        humanVerified: true,
        dateAdded: "2024-01-14",
      },
      {
        name: "Dragon NaturallySpeaking",
        description: "Industry-leading speech recognition software",
        category: "Speech Recognition and Voice Control",
        website: "https://www.nuance.com/dragon.html",
        pricing: "Paid",
        platforms: ["Windows", "Mac"],
        aiVerified: true,
        humanVerified: false,
        dateAdded: "2024-01-13",
      },
    ],
  };
}
