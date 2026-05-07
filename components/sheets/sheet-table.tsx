"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, CheckCircle2, Circle } from "lucide-react";
import type { ATTool } from "@/lib/types";

interface SheetTableProps {
  tools: ATTool[];
  isLoading: boolean;
  sheetTitle?: string;
}

export function SheetTable({ tools, isLoading, sheetTitle }: SheetTableProps) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">
          {sheetTitle || "Sheet Data"}
        </CardTitle>
        <CardDescription className="text-muted-foreground">
          {tools.length} tools in the database
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : tools.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-muted-foreground">
            No tools found. Configure your Google Sheets connection first.
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
                  <TableHead className="text-muted-foreground">Verified</TableHead>
                  <TableHead className="text-muted-foreground text-right">Link</TableHead>
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
                      {tool.category.split("(")[0].trim().substring(0, 20)}
                      {tool.category.length > 20 ? "..." : ""}
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
                        {tool.platforms.slice(0, 2).map((platform) => (
                          <Badge
                            key={platform}
                            variant="outline"
                            className="border-border text-muted-foreground text-xs"
                          >
                            {platform}
                          </Badge>
                        ))}
                        {tool.platforms.length > 2 && (
                          <Badge variant="outline" className="border-border text-muted-foreground text-xs">
                            +{tool.platforms.length - 2}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {tool.aiVerified ? (
                          <CheckCircle2 className="h-4 w-4 text-chart-2" />
                        ) : (
                          <Circle className="h-4 w-4 text-muted-foreground" />
                        )}
                        {tool.humanVerified && (
                          <CheckCircle2 className="h-4 w-4 text-chart-1" />
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <a
                        href={tool.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
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
