import { google } from "googleapis";
import type { ATTool } from "./types";

function getAuth() {
  const serviceAccountJson = process.env.GOOGLE_SERVICE_ACCOUNT;
  if (!serviceAccountJson) {
    throw new Error("GOOGLE_SERVICE_ACCOUNT environment variable is not set");
  }

  let credentials;
  try {
    // Try parsing as JSON directly first
    credentials = JSON.parse(serviceAccountJson);
  } catch {
    // If that fails, try base64 decoding
    try {
      credentials = JSON.parse(Buffer.from(serviceAccountJson, "base64").toString());
    } catch {
      throw new Error("GOOGLE_SERVICE_ACCOUNT must be valid JSON or base64-encoded JSON");
    }
  }

  return new google.auth.GoogleAuth({
    credentials,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
}

export async function getSheets() {
  const auth = getAuth();
  return google.sheets({ version: "v4", auth });
}

export async function fetchToolsFromSheet(
  spreadsheetId: string,
  range = "Sheet1!A2:L"
): Promise<ATTool[]> {
  const sheets = await getSheets();
  
  const response = await sheets.spreadsheets.values.get({
    spreadsheetId,
    range,
  });

  const rows = response.data.values || [];
  
  return rows.map((row, index) => ({
    id: `sheet-${index}`,
    name: row[0] || "",
    description: row[1] || "",
    category: row[2] || "",
    website: row[3] || "",
    pricing: (row[4] as ATTool["pricing"]) || "Unknown",
    platforms: row[5] ? row[5].split(",").map((p: string) => p.trim()) : [],
    youtubeVideo: row[6] || undefined,
    aiVerified: row[7]?.toLowerCase() === "true",
    humanVerified: row[8]?.toLowerCase() === "true",
    dateAdded: row[9] || undefined,
  }));
}

export async function appendToolsToSheet(
  spreadsheetId: string,
  tools: ATTool[],
  range = "Sheet1!A:L"
): Promise<number> {
  const sheets = await getSheets();
  
  const values = tools.map((tool) => [
    tool.name,
    tool.description,
    tool.category,
    tool.website,
    tool.pricing,
    tool.platforms.join(", "),
    tool.youtubeVideo || "",
    tool.aiVerified ? "TRUE" : "FALSE",
    tool.humanVerified ? "FALSE" : "FALSE",
    new Date().toISOString().split("T")[0],
  ]);

  const response = await sheets.spreadsheets.values.append({
    spreadsheetId,
    range,
    valueInputOption: "USER_ENTERED",
    requestBody: {
      values,
    },
  });

  return response.data.updates?.updatedRows || 0;
}

export async function getSheetMetadata(spreadsheetId: string) {
  const sheets = await getSheets();
  
  const response = await sheets.spreadsheets.get({
    spreadsheetId,
  });

  return {
    title: response.data.properties?.title || "Unknown",
    sheetNames: response.data.sheets?.map((s) => s.properties?.title) || [],
  };
}
