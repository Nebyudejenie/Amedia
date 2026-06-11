import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MetricCard } from '@/components/dashboard/MetricCard';

describe('MetricCard', () => {
  it('renders label and compact number', () => {
    render(<MetricCard label="Content Analyzed" value={12345} />);
    expect(screen.getByText('Content Analyzed')).toBeInTheDocument();
    expect(screen.getByText('12.3K')).toBeInTheDocument();
  });

  it('renders dash for null values', () => {
    render(<MetricCard label="Videos" value={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders an accessible progress bar in percent mode', () => {
    render(<MetricCard label="Usage" value={72} percent />);
    const bar = screen.getByRole('progressbar', { name: 'Usage' });
    expect(bar).toHaveAttribute('aria-valuenow', '72');
    expect(screen.getByText('72%')).toBeInTheDocument();
  });

  it('shows hint text when provided', () => {
    render(<MetricCard label="Subs" value={3} hint="Webhook subscriptions" />);
    expect(screen.getByText('Webhook subscriptions')).toBeInTheDocument();
  });
});
