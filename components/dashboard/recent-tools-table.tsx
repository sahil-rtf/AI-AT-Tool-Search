"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Circle, ExternalLink } from "lucide-react";
import type { AnalyticsData } from "@/lib/types";

interface RecentToolsTableProps {
  data: AnalyticsData | null;
  isLoading: boolean;
}

export function RecentToolsTable({ data, isLoading }: RecentToolsTableProps) {
  const tools = data?.recentTools || [];

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Recent Additions</CardTitle>
        <CardDescription className="text-muted-foreground">
          Latest tools added to the database
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground">Name</TableHead>
                <TableHead className="text-muted-foreground">Category</TableHead>
                <TableHead className="text-muted-foreground">Pricing</TableHead>
                <TableHead className="text-muted-foreground">Verified</TableHead>
                <TableHead className="text-muted-foreground text-right">Link</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tools.length === 0 ? (
                <TableRow className="border-border hover:bg-secondary/50">
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No tools found. Run a discovery to add tools.
                  </TableCell>
                </TableRow>
              ) : (
                tools.map((tool, index) => (
                  <TableRow key={index} className="border-border hover:bg-secondary/50">
                    <TableCell className="font-medium text-foreground">
                      {tool.name}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {tool.category.split("(")[0].trim().substring(0, 25)}
                      {tool.category.length > 25 ? "..." : ""}
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
                      <div className="flex items-center gap-2">
                        {tool.aiVerified ? (
                          <CheckCircle2 className="h-4 w-4 text-chart-2" />
                        ) : (
                          <Circle className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span className="text-xs text-muted-foreground">
                          {tool.aiVerified ? "AI" : ""}
                          {tool.aiVerified && tool.humanVerified ? " + " : ""}
                          {tool.humanVerified ? "Human" : ""}
                          {!tool.aiVerified && !tool.humanVerified ? "Pending" : ""}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <a
                        href={tool.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
