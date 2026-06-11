import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DataTable, type Column } from '@/components/dashboard/DataTable';

interface Row {
  id: string;
  name: string;
}

const columns: Column<Row>[] = [
  { key: 'name', header: 'Name', render: (r) => r.name },
];

const rows: Row[] = [
  { id: '1', name: 'Alpha' },
  { id: '2', name: 'Beta' },
];

describe('DataTable', () => {
  it('renders rows and headers', () => {
    render(<DataTable columns={columns} rows={rows} />);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('shows loading skeleton', () => {
    render(<DataTable columns={columns} rows={[]} isLoading />);
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  it('shows error state with retry', async () => {
    const onRetry = vi.fn();
    render(<DataTable columns={columns} rows={[]} error="Network error" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Network error');
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('shows empty state when no rows', () => {
    render(<DataTable columns={columns} rows={[]} emptyTitle="No content found" />);
    expect(screen.getByText('No content found')).toBeInTheDocument();
  });

  it('fires onRowClick', async () => {
    const onRowClick = vi.fn();
    render(<DataTable columns={columns} rows={rows} onRowClick={onRowClick} />);
    await userEvent.click(screen.getByText('Alpha'));
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });

  it('supports select-all + per-row selection', async () => {
    const toggle = vi.fn();
    const toggleAll = vi.fn();
    render(
      <DataTable
        columns={columns}
        rows={rows}
        selection={{ isSelected: () => false, toggle, toggleAll, allSelected: false }}
      />
    );

    await userEvent.click(screen.getByRole('checkbox', { name: /select all/i }));
    expect(toggleAll).toHaveBeenCalledWith(['1', '2']);

    await userEvent.click(screen.getByRole('checkbox', { name: /select row 1/i }));
    expect(toggle).toHaveBeenCalledWith('1');
  });
});
