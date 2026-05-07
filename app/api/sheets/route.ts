import { NextResponse } from "next/server";
import { fetchToolsFromSheet, appendToolsToSheet, getSheetMetadata } from "@/lib/sheets";
import type { ATTool } from "@/lib/types";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const spreadsheetId = searchParams.get("spreadsheetId") || process.env.GOOGLE_SHEETS_ID;

    if (!spreadsheetId) {
      return NextResponse.json(
        { error: "No spreadsheet ID provided" },
        { status: 400 }
      );
    }

    const metadataOnly = searchParams.get("metadataOnly") === "true";

    if (metadataOnly) {
      const metadata = await getSheetMetadata(spreadsheetId);
      return NextResponse.json(metadata);
    }

    const tools = await fetchToolsFromSheet(spreadsheetId);
    const metadata = await getSheetMetadata(spreadsheetId);

    return NextResponse.json({
      metadata,
      tools,
      count: tools.length,
    });
  } catch (error) {
    console.error("Error fetching from sheets:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to fetch from Google Sheets" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { tools, spreadsheetId } = body as {
      tools: ATTool[];
      spreadsheetId?: string;
    };

    const sheetId = spreadsheetId || process.env.GOOGLE_SHEETS_ID;

    if (!sheetId) {
      return NextResponse.json(
        { error: "No spreadsheet ID provided" },
        { status: 400 }
      );
    }

    if (!tools || !Array.isArray(tools) || tools.length === 0) {
      return NextResponse.json(
        { error: "No tools provided" },
        { status: 400 }
      );
    }

    const rowsAdded = await appendToolsToSheet(sheetId, tools);

    return NextResponse.json({
      success: true,
      rowsAdded,
      message: `Successfully added ${rowsAdded} tools to the spreadsheet`,
    });
  } catch (error) {
    console.error("Error writing to sheets:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to write to Google Sheets" },
      { status: 500 }
    );
  }
}
