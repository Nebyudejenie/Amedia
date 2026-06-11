import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ContentUploadForm } from '@/components/forms/ContentUploadForm';

describe('ContentUploadForm', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders all base fields', () => {
    render(<ContentUploadForm />);
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/source type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/content type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/source url/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/publish immediately/i)).toBeInTheDocument();
  });

  it('shows a live character counter for the title', async () => {
    const user = userEvent.setup();
    render(<ContentUploadForm />);
    await user.type(screen.getByLabelText(/title/i), 'Hello');
    expect(screen.getByText('5 / 200')).toBeInTheDocument();
  });

  it('requires source URL for RSS but hides it for manual entry', async () => {
    const user = userEvent.setup();
    render(<ContentUploadForm />);

    // Submit with empty URL while source=rss → field error
    await user.type(screen.getByLabelText(/title/i), 'My feed');
    await user.click(screen.getByRole('button', { name: /create & publish/i }));
    expect(await screen.findByText(/source url is required/i)).toBeInTheDocument();

    // Switching to manual hides the URL field entirely
    await user.selectOptions(screen.getByLabelText(/source type/i), 'manual');
    expect(screen.queryByLabelText(/source url/i)).not.toBeInTheDocument();
  });

  it('rejects malformed URLs', async () => {
    const user = userEvent.setup();
    render(<ContentUploadForm />);

    await user.type(screen.getByLabelText(/title/i), 'My feed');
    await user.type(screen.getByLabelText(/source url/i), 'not-a-url');
    await user.click(screen.getByRole('button', { name: /create & publish/i }));

    expect(await screen.findByText(/valid http\(s\) url/i)).toBeInTheDocument();
  });

  it('reveals date/time pickers when scheduling', async () => {
    const user = userEvent.setup();
    render(<ContentUploadForm />);

    expect(screen.queryByLabelText(/date/i)).not.toBeInTheDocument();
    await user.click(screen.getByLabelText(/publish immediately/i));
    expect(screen.getByLabelText(/date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/time/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /schedule content/i })).toBeInTheDocument();
  });

  it('submits valid data to the content endpoint', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'c-123' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const user = userEvent.setup();
    render(<ContentUploadForm />);

    await user.type(screen.getByLabelText(/title/i), 'Tech news feed');
    await user.type(screen.getByLabelText(/source url/i), 'https://example.com/feed.xml');
    await user.click(screen.getByRole('button', { name: /create & publish/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/proxy/content/sources',
        expect.objectContaining({ method: 'POST' })
      );
    });

    const body = JSON.parse((fetchMock.mock.calls[0]![1] as RequestInit).body as string);
    expect(body.title).toBe('Tech news feed');
    expect(body.url).toBe('https://example.com/feed.xml');
    expect(body.scheduled_at).toBeNull();

    // Success confirmation modal appears
    expect(await screen.findByText(/content created/i)).toBeInTheDocument();
  });

  it('shows API error without leaving the page', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Workspace limit reached' }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const user = userEvent.setup();
    render(<ContentUploadForm />);

    await user.type(screen.getByLabelText(/title/i), 'Feed');
    await user.type(screen.getByLabelText(/source url/i), 'https://example.com/x');
    await user.click(screen.getByRole('button', { name: /create & publish/i }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    // Form still present
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
  });
});
