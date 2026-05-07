"use client";

import useSWR from "swr";
import { Navigation } from "@/components/navigation";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { CategoryChart } from "@/components/dashboard/category-chart";
import { PricingChart } from "@/components/dashboard/pricing-chart";
import { RecentToolsTable } from "@/components/dashboard/recent-tools-table";
import type { AnalyticsData } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((res) => res.json());

export default function AnalyticsPage() {
  const { data, error, isLoading } = useSWR<AnalyticsData>("/api/analytics", fetcher, {
    refreshInterval: 30000,
  });

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground">Analytics Dashboard</h1>
          <p className="text-muted-foreground">
            Overview of your assistive technology tools database
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
            Failed to load analytics data. Showing sample data instead.
          </div>
        )}

        <div className="space-y-6">
          <StatsCards data={data || null} isLoading={isLoading} />

          <div className="grid gap-6 lg:grid-cols-2">
            <CategoryChart data={data || null} isLoading={isLoading} />
            <PricingChart data={data || null} isLoading={isLoading} />
          </div>

          <RecentToolsTable data={data || null} isLoading={isLoading} />
        </div>
      </main>
    </div>
  );
}
