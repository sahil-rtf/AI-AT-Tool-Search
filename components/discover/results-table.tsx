"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, Play, Download } from "lucide-react";
import type { ATTool } from "@/lib/types";

interface ResultsTableProps {
  tools: ATTool[];
  onExportToSheets: () => void;
  isExporting: boolean;
}

export function ResultsTable({ tools, onExportToSheets, isExporting }: ResultsTableProps) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-foreground">Discovered Tools</CardTitle>
            <CardDescription className="text-muted-foreground">
              {tools.length} tools ready for export
            </CardDescription>
          </div>
          {tools.length > 0 && (
            <Button
              onClick={onExportToSheets}
              disabled={isExporting}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Download className="mr-2 h-4 w-4" />
              {isExporting ? "Exporting..." : "Export to Sheets"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {tools.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-muted-foreground">
            No tools discovered yet. Run a discovery to find new AT tools.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-muted-foreground">Name</TableHead>
                  <TableHead className="text-muted-foreground">Category</TableHead>
                  <TableHead className="text-muted-foreground">Pricing</TableHead>
                  <TableHead className="text-muted-foreground">Platforms</TableHead>
                  <TableHead className="text-muted-foreground text-right">Links</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tools.map((tool, index) => (
                  <TableRow key={index} className="border-border hover:bg-secondary/50">
                    <TableCell>
                      <div>
                        <div className="font-medium text-foreground">{tool.name}</div>
                        <div className="text-xs text-muted-foreground line-clamp-1">
                          {tool.description}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {tool.category.split("(")[0].trim().substring(0, 20)}...
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={
                          tool.pricing === "Free"
                            ? "bg-chart-2/20 text-chart-2"
                            : tool.pricing === "Freemium"
                            ? "bg-chart-3/20 text-chart-3"
                            : "bg-chart-5/20 text-chart-5"
                        }
                      >
                        {tool.pricing}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {tool.platforms.slice(0, 3).map((platform) => (
                          <Badge
                            key={platform}
                            variant="outline"
                            className="border-border text-muted-foreground text-xs"
                          >
                            {platform}
                          </Badge>
                        ))}
                        {tool.platforms.length > 3 && (
                          <Badge variant="outline" className="border-border text-muted-foreground text-xs">
                            +{tool.platforms.length - 3}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        {tool.youtubeVideo && (
                          <a
                            href={tool.youtubeVideo}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-destructive hover:text-destructive/80"
                          >
                            <Play className="h-4 w-4" />
                          </a>
                        )}
                        <a
                          href={tool.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
