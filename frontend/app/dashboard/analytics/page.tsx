'use client';

import { useMemo, useState } from 'react';

import { TrendLineChart, BreakdownBarChart, SourcePieChart } from '@/components/charts/LazyCharts';
import { DataTable, type Column } from '@/components/dashboard/DataTable';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { EmptyState } from '@/components/ui/EmptyState';
import { useApi } from '@/lib/hooks';
import { compactNumber, truncate } from '@/lib/format';
import type { TrendPoint, SourceSlice, TopPerformer } from '@/lib/types';

// Up to 3 metrics can be plotted at once
const METRICS = [
  { key: 'sentiment', label: 'Sentiment', color: '#4f46e5' },
  { key: 'engagement', label: 'Engagement', color: '#10b981' },
  { key: 'reach', label: 'Reach', color: '#f59e0b' },
] as const;

const RANGE_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
];

const BREAKDOWN_OPTIONS = [
  { value: 'source', label: 'By content source' },
  { value: 'sentiment', label: 'Sentiment distribution' },
];

interface AnalyticsResponse {
  trends?: TrendPoint[];
  by_source?: SourceSlice[];
  sentiment_distribution?: SourceSlice[];
  top_performers?: TopPerformer[];
}

const PERFORMER_COLUMNS: Column<TopPerformer>[] = [
  {
    key: 'title',
    header: 'Title',
    render: (row) => (
      <span className="font-medium text-gray-900 dark:text-white">{truncate(row.title, 50)}</span>
    ),
  },
  {
    key: 'engagement',
    header: 'Engagement',
    render: (row) => <span>{(row.engagement * 100).toFixed(1)}%</span>,
  },
  {
    key: 'reach',
    header: 'Reach',
    hideOnMobile: true,
    render: (row) => <span>{compactNumber(row.reach)}</span>,
  },
  {
    key: 'sentiment',
    header: 'Sentiment',
    render: (row) => (
      <span className={row.sentiment >= 0 ? 'text-green-600' : 'text-red-600'}>
        {row.sentiment >= 0 ? '+' : ''}{row.sentiment.toFixed(2)}
      </span>
    ),
  },
];

export default function AnalyticsPage() {
  const [days, setDays] = useState('30');
  const [breakdown, setBreakdown] = useState('source');
  // Which of the 3 metric series are visible on the trend chart
  const [activeMetrics, setActiveMetrics] = useState<Set<string>>(
    new Set(METRICS.map((m) => m.key))
  );

  const { data, isLoading, error, refetch } = useApi<AnalyticsResponse>(
    `/analytics/dashboard?days=${days}`
  );

  const toggleMetric = (key: string) => {
    setActiveMetrics((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key); // keep at least one series visible
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const visibleSeries = useMemo(
    () => METRICS.filter((m) => activeMetrics.has(m.key)),
    [activeMetrics]
  );

  const breakdownData =
    breakdown === 'source' ? data?.by_source : data?.sentiment_distribution;

  return (
    <div className="space-y-6">
      {/* Header + selectors */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Analytics</h1>
        <div className="flex flex-wrap gap-3">
          <Select
            aria-label="Date range"
            options={RANGE_OPTIONS}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
          <Select
            aria-label="Breakdown type"
            options={BREAKDOWN_OPTIONS}
            value={breakdown}
            onChange={(e) => setBreakdown(e.target.value)}
          />
        </div>
      </div>

      {/* Metric toggles — click to show/hide a series */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Toggle metrics">
        {METRICS.map((metric) => {
          const active = activeMetrics.has(metric.key);
          return (
            <button
              key={metric.key}
              onClick={() => toggleMetric(metric.key)}
              aria-pressed={active}
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                active
                  ? 'border-transparent text-white'
                  : 'border-gray-300 bg-white text-gray-500 dark:border-gray-600 dark:bg-gray-800'
              }`}
              style={active ? { backgroundColor: metric.color } : undefined}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: active ? '#fff' : metric.color }}
              />
              {metric.label}
            </button>
          );
        })}
      </div>

      {/* Multi-series trend chart */}
      <Card title={`Trends — last ${days} days`}>
        {data?.trends?.length ? (
          <TrendLineChart data={data.trends} series={visibleSeries} />
        ) : (
          <EmptyState
            title={isLoading ? 'Loading…' : error ?? 'No analytics data yet'}
            description="Charts populate once content analysis starts producing metrics."
          />
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Breakdown chart */}
        <Card title={breakdown === 'source' ? 'Performance by source' : 'Sentiment distribution'}>
          {breakdownData?.length ? (
            breakdown === 'source' ? (
              <BreakdownBarChart data={breakdownData} />
            ) : (
              <SourcePieChart data={breakdownData} />
            )
          ) : (
            <EmptyState title="No breakdown data" description="Connect sources to see this chart." />
          )}
        </Card>

        {/* Top performers */}
        <Card title="Top performing content" className="p-0 [&>h3]:px-6 [&>h3]:pt-6">
          <DataTable
            columns={PERFORMER_COLUMNS}
            rows={data?.top_performers ?? []}
            isLoading={isLoading}
            error={error}
            onRetry={refetch}
            emptyTitle="No performance data"
            emptyDescription="Your best content will rank here after publishing."
          />
        </Card>
      </div>
    </div>
  );
}
