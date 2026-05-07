"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Database, Layers, DollarSign, Monitor } from "lucide-react";
import type { AnalyticsData } from "@/lib/types";

interface StatsCardsProps {
  data: AnalyticsData | null;
  isLoading: boolean;
}

export function StatsCards({ data, isLoading }: StatsCardsProps) {
  const stats = [
    {
      title: "Total Tools",
      value: data?.totalTools || 0,
      icon: Database,
      description: "Assistive technology tools cataloged",
    },
    {
      title: "Categories",
      value: data ? Object.keys(data.toolsByCategory).length : 0,
      icon: Layers,
      description: "Different AT categories covered",
    },
    {
      title: "Free Tools",
      value: data?.toolsByPricing?.Free || 0,
      icon: DollarSign,
      description: "Tools available at no cost",
    },
    {
      title: "Platforms",
      value: data ? Object.keys(data.toolsByPlatform).length : 0,
      icon: Monitor,
      description: "Supported platforms",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.title} className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {stat.title}
            </CardTitle>
            <stat.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-20 animate-pulse rounded bg-muted" />
            ) : (
              <>
                <div className="text-2xl font-bold text-foreground">{stat.value}</div>
                <p className="text-xs text-muted-foreground">{stat.description}</p>
              </>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
