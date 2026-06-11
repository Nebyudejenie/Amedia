'use client';

/**
 * Recharts implementations. Imported only via next/dynamic (LazyCharts.tsx)
 * so the ~100kb recharts bundle never blocks initial page load.
 */
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell, BarChart, Bar, ResponsiveContainer,
} from 'recharts';
import type { TrendPoint, SourceSlice } from '@/lib/types';
import { shortDate } from '@/lib/format';

const PALETTE = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

export interface SeriesDef {
  key: string;
  label: string;
  color?: string;
}

export function TrendLineChartImpl({
  data,
  series,
}: {
  data: TrendPoint[];
  series: SeriesDef[];
}) {
  return (
    <ResponsiveContainer width="100%" height={288}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          labelFormatter={(label) => shortDate(String(label))}
          formatter={(value, name) => [Number(value ?? 0).toLocaleString(), String(name)]}
        />
        <Legend />
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color ?? PALETTE[i % PALETTE.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function SourcePieChartImpl({ data }: { data: SourceSlice[] }) {
  return (
    <ResponsiveContainer width="100%" height={288}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={100} paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(value) => Number(value ?? 0).toLocaleString()} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function BreakdownBarChartImpl({ data }: { data: SourceSlice[] }) {
  return (
    <ResponsiveContainer width="100%" height={288}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip formatter={(value) => Number(value ?? 0).toLocaleString()} />
        <Bar dataKey="value" fill="#4f46e5" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
