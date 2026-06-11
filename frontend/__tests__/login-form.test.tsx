import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LoginForm } from '@/components/auth/LoginForm';

describe('LoginForm', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders email, password, remember-me and submit', () => {
    render(<LoginForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /remember me/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /forgot password/i })).toBeInTheDocument();
  });

  it('shows validation errors for empty submission', async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
  });

  it('rejects malformed email', async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), 'not-an-email');
    await user.type(screen.getByLabelText(/^password$/i), 'somepassword');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
  });

  it('submits credentials to /api/auth/login', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ user: { id: '1', email: 'a@b.co', is_admin: false, is_active: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), 'a@b.co');
    await user.type(screen.getByLabelText(/^password$/i), 'SuperSecure123!');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/login',
        expect.objectContaining({ method: 'POST' })
      );
    });

    const body = JSON.parse((fetchMock.mock.calls[0]![1] as RequestInit).body as string);
    expect(body.email).toBe('a@b.co');
    expect(body.password).toBe('SuperSecure123!');
  });

  it('displays backend error on 401', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid credentials' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText(/email/i), 'a@b.co');
    await user.type(screen.getByLabelText(/^password$/i), 'WrongPassword1!');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid credentials/i);
  });
});
