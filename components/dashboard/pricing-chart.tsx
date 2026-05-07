"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Cell, Pie, PieChart } from "recharts";
import type { AnalyticsData } from "@/lib/types";

interface PricingChartProps {
  data: AnalyticsData | null;
  isLoading: boolean;
}

const COLORS = [
  "var(--chart-2)", // Free - teal
  "var(--chart-3)", // Freemium - amber
  "var(--chart-5)", // Paid - red
];

const chartConfig = {
  Free: {
    label: "Free",
    color: "var(--chart-2)",
  },
  Freemium: {
    label: "Freemium",
    color: "var(--chart-3)",
  },
  Paid: {
    label: "Paid",
    color: "var(--chart-5)",
  },
} satisfies ChartConfig;

export function PricingChart({ data, isLoading }: PricingChartProps) {
  const chartData = data
    ? Object.entries(data.toolsByPricing).map(([name, value]) => ({
        name,
        value,
      }))
    : [];

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Pricing Distribution</CardTitle>
        <CardDescription className="text-muted-foreground">
          Tools by pricing model
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[300px] animate-pulse rounded bg-muted" />
        ) : (
          <ChartContainer config={chartConfig} className="mx-auto h-[300px] w-full max-w-[300px]">
            <PieChart>
              <ChartTooltip content={<ChartTooltipContent hideLabel />} />
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                labelLine={false}
              >
                {chartData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
