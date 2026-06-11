/** POST /api/auth/login — proxy to FastAPI, store tokens in httpOnly cookies. */
import { NextRequest, NextResponse } from 'next/server';
import { API_URL, setAuthCookies } from '@/lib/auth-server';

export async function POST(request: NextRequest) {
  const { email, password, rememberMe = false } = await request.json();

  const backend = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  const data = await backend.json().catch(() => ({}));

  if (!backend.ok) {
    return NextResponse.json(
      { detail: data.detail ?? 'Login failed' },
      { status: backend.status }
    );
  }

  // Tokens never reach the browser JS — only the user object does
  const response = NextResponse.json({ user: data.user });
  setAuthCookies(response, data.tokens.access_token, data.tokens.refresh_token, rememberMe);
  return response;
}
