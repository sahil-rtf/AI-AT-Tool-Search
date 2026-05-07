"use client";

import { useState } from "react";
import { Navigation } from "@/components/navigation";
import { SyncControls } from "@/components/sheets/sync-controls";
import { SheetTable } from "@/components/sheets/sheet-table";
import type { ATTool } from "@/lib/types";

interface SheetData {
  metadata: {
    title: string;
    sheetNames: string[];
  };
  tools: ATTool[];
  count: number;
}

export default function SheetsPage() {
  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheetData, setSheetData] = useState<SheetData | null>(null);

  const fetchSheetData = async (id: string) => {
    const response = await fetch(`/api/sheets?spreadsheetId=${encodeURIComponent(id)}`);
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Failed to fetch sheet data");
    }

    return response.json() as Promise<SheetData>;
  };

  const handleConnect = async () => {
    if (!spreadsheetId) return;

    setIsConnecting(true);
    setError(null);

    try {
      const data = await fetchSheetData(spreadsheetId);
      setSheetData(data);
      setIsConnected(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect to sheet");
      setIsConnected(false);
      setSheetData(null);
    } finally {
      setIsConnecting(false);
    }
  };

  const handleRefresh = async () => {
    if (!spreadsheetId || !isConnected) return;

    setIsRefreshing(true);
    setError(null);

    try {
      const data = await fetchSheetData(spreadsheetId);
      setSheetData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh sheet data");
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground">Google Sheets Sync</h1>
          <p className="text-muted-foreground">
            Connect and manage your AT tools database in Google Sheets
          </p>
        </div>

        <div className="space-y-6">
          <SyncControls
            spreadsheetId={spreadsheetId}
            onSpreadsheetIdChange={setSpreadsheetId}
            onConnect={handleConnect}
            onRefresh={handleRefresh}
            isConnecting={isConnecting}
            isRefreshing={isRefreshing}
            isConnected={isConnected}
            error={error}
            sheetTitle={sheetData?.metadata.title}
          />

          <SheetTable
            tools={sheetData?.tools || []}
            isLoading={isConnecting || isRefreshing}
            sheetTitle={sheetData?.metadata.title}
          />
        </div>
      </main>
    </div>
  );
}
