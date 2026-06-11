'use client';

/** Lazy chart entrypoints — recharts loads only when a chart scrolls into view. */
import dynamic from 'next/dynamic';
import { ChartSkeleton } from '@/components/ui/Skeleton';

export const TrendLineChart = dynamic(
  () => import('./ChartImpl').then((m) => m.TrendLineChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> }
);

export const SourcePieChart = dynamic(
  () => import('./ChartImpl').then((m) => m.SourcePieChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> }
);

export const BreakdownBarChart = dynamic(
  () => import('./ChartImpl').then((m) => m.BreakdownBarChartImpl),
  { ssr: false, loading: () => <ChartSkeleton /> }
);
