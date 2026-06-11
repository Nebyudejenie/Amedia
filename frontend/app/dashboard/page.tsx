'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { MetricCard } from '@/components/dashboard/MetricCard';
import { DataTable, type Column } from '@/components/dashboard/DataTable';
import { StatusBadge } from '@/components/dashboard/StatusBadge';
import { TrendLineChart, SourcePieChart } from '@/components/charts/LazyCharts';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { useApi } from '@/lib/hooks';
import { relativeTime, truncate } from '@/lib/format';
import { useAuthStore } from '@/stores/auth';
import type { ContentItem, DashboardStats, TrendPoint, SourceSlice } from '@/lib/types';

interface OverviewResponse {
  stats?: DashboardStats;
  trends?: TrendPoint[];
  sources?: SourceSlice[];
}

interface ItemsResponse {
  items?: ContentItem[];
}

const ACTIVITY_COLUMNS: Column<ContentItem>[] = [
  {
    key: 'title',
    header: 'Title',
    render: (row) => (
      <span className="font-medium text-gray-900 dark:text-white">{truncate(row.title, 50)}</span>
    ),
  },
  {
    key: 'source',
    header: 'Source',
    hideOnMobile: true,
    render: (row) => <span className="uppercase text-gray-500">{row.source_type}</span>,
  },
  {
    key: 'status',
    header: 'Status',
    render: (row) => <StatusBadge status={row.status} />,
  },
  {
    key: 'created',
    header: 'Date',
    hideOnMobile: true,
    render: (row) => <span className="text-gray-500">{relativeTime(row.created_at)}</span>,
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const overview = useApi<OverviewResponse>('/analytics/dashboard');
  const recent = useApi<ItemsResponse>('/content/items?limit=10');

  const stats = overview.data?.stats;
  const recentItems = useMemo(() => recent.data?.items ?? [], [recent.data]);

  return (
    <div className="space-y-6">
      {/* Header + quick actions */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Welcome back{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''} 👋
          </h1>
          <p className="mt-1 text-sm text-gray-500">Here&apos;s what&apos;s happening in your workspace.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => router.push('/dashboard/content?add=1')}>
            + Upload Content
          </Button>
          <Button size="sm" variant="secondary" onClick={() => router.push('/dashboard/content')}>
            Run Analysis
          </Button>
          <Button size="sm" variant="secondary" onClick={() => router.push('/dashboard/analytics')}>
            View Reports
          </Button>
        </div>
      </div>

      {/* Metric cards: 1 col mobile → 2 cols tablet → 4 cols desktop */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {overview.isLoading ? (
          <>
            <CardSkeleton /><CardSkeleton /><CardSkeleton /><CardSkeleton />
          </>
        ) : (
          <>
            <MetricCard
              label="Content Analyzed"
              value={stats?.total_content ?? 0}
              hint="All time"
            />
            <MetricCard
              label="Videos Generated"
              value={stats?.total_videos ?? 0}
              hint="All time"
            />
            <MetricCard
              label="This Month's Usage"
              value={stats?.usage_percent ?? 0}
              percent
              hint="Of plan limit"
            />
            <MetricCard
              label="Active Subscriptions"
              value={stats?.active_subscriptions ?? 0}
              hint="Webhook subscriptions"
            />
          </>
        )}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Analysis trends (30 days)">
          {overview.data?.trends?.length ? (
            <TrendLineChart
              data={overview.data.trends}
              series={[{ key: 'value', label: 'Analyses' }]}
            />
          ) : (
            <EmptyState
              title="No trend data yet"
              description="Trends appear after your first content analyses."
            />
          )}
        </Card>

        <Card title="Content sources">
          {overview.data?.sources?.length ? (
            <SourcePieChart data={overview.data.sources} />
          ) : (
            <EmptyState
              title="No sources connected"
              description="Connect RSS, Telegram or YouTube to see the distribution."
              action={
                <Link href="/dashboard/content" className="text-sm font-medium text-brand-600 hover:underline">
                  Add a source →
                </Link>
              }
            />
          )}
        </Card>
      </div>

      {/* Recent activity */}
      <Card title="Recent activity" className="p-0 [&>h3]:px-6 [&>h3]:pt-6">
        <DataTable
          columns={ACTIVITY_COLUMNS}
          rows={recentItems}
          isLoading={recent.isLoading}
          error={recent.error}
          onRetry={recent.refetch}
          emptyTitle="No activity yet"
          emptyDescription="Content you ingest and analyze will appear here."
          onRowClick={(row) => router.push(`/dashboard/content?item=${row.id}`)}
        />
      </Card>
    </div>
  );
}
