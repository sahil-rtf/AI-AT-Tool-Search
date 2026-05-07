"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { RefreshCw, Link2, CheckCircle2, AlertCircle } from "lucide-react";

interface SyncControlsProps {
  spreadsheetId: string;
  onSpreadsheetIdChange: (id: string) => void;
  onConnect: () => void;
  onRefresh: () => void;
  isConnecting: boolean;
  isRefreshing: boolean;
  isConnected: boolean;
  error?: string | null;
  sheetTitle?: string;
}

export function SyncControls({
  spreadsheetId,
  onSpreadsheetIdChange,
  onConnect,
  onRefresh,
  isConnecting,
  isRefreshing,
  isConnected,
  error,
  sheetTitle,
}: SyncControlsProps) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Google Sheets Connection</CardTitle>
        <CardDescription className="text-muted-foreground">
          Connect to your AT tools spreadsheet
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="spreadsheetId" className="text-foreground">
            Spreadsheet ID
          </Label>
          <div className="flex gap-2">
            <Input
              id="spreadsheetId"
              placeholder="Enter Google Sheets ID..."
              value={spreadsheetId}
              onChange={(e) => onSpreadsheetIdChange(e.target.value)}
              className="bg-background border-border text-foreground placeholder:text-muted-foreground"
            />
            <Button
              onClick={onConnect}
              disabled={!spreadsheetId || isConnecting}
              className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0"
            >
              <Link2 className="mr-2 h-4 w-4" />
              {isConnecting ? "Connecting..." : "Connect"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Find the ID in your Google Sheets URL: docs.google.com/spreadsheets/d/
            <span className="text-chart-1">SPREADSHEET_ID</span>/edit
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {isConnected && !error && (
          <div className="flex items-center justify-between rounded-lg bg-chart-2/10 px-4 py-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-chart-2" />
              <span className="text-sm text-chart-2">
                Connected to: {sheetTitle || "Google Sheet"}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="text-chart-2 hover:text-chart-2 hover:bg-chart-2/20"
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        )}

        <div className="rounded-lg border border-border bg-secondary/30 p-4">
          <h4 className="text-sm font-medium text-foreground mb-2">Setup Instructions</h4>
          <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside">
            <li>Create a Google Cloud service account</li>
            <li>Enable Google Sheets API in your project</li>
            <li>Share your spreadsheet with the service account email</li>
            <li>Add the service account JSON as GOOGLE_SERVICE_ACCOUNT env var</li>
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
