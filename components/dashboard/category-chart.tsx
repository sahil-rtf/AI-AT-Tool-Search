"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Bar, BarChart, XAxis, YAxis } from "recharts";
import type { AnalyticsData } from "@/lib/types";

interface CategoryChartProps {
  data: AnalyticsData | null;
  isLoading: boolean;
}

const chartConfig = {
  count: {
    label: "Tools",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig;

export function CategoryChart({ data, isLoading }: CategoryChartProps) {
  const chartData = data
    ? Object.entries(data.toolsByCategory)
        .map(([name, count]) => ({
          name: name.split("(")[0].trim().substring(0, 20) + (name.length > 20 ? "..." : ""),
          fullName: name,
          count,
        }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
    : [];

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Tools by Category</CardTitle>
        <CardDescription className="text-muted-foreground">
          Distribution of tools across AT categories
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[300px] animate-pulse rounded bg-muted" />
        ) : (
          <ChartContainer config={chartConfig} className="h-[300px] w-full">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 0, right: 16 }}
            >
              <XAxis type="number" hide />
              <YAxis
                dataKey="name"
                type="category"
                tickLine={false}
                axisLine={false}
                width={140}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
              />
              <ChartTooltip
                content={<ChartTooltipContent />}
                cursor={{ fill: "var(--muted)", opacity: 0.3 }}
              />
              <Bar
                dataKey="count"
                fill="var(--chart-1)"
                radius={[0, 4, 4, 0]}
              />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
