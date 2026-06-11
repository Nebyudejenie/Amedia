/** POST /api/auth/register — proxy to FastAPI, store tokens in httpOnly cookies. */
import { NextRequest, NextResponse } from 'next/server';
import { API_URL, setAuthCookies } from '@/lib/auth-server';

export async function POST(request: NextRequest) {
  const body = await request.json();

  const backend = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: body.email,
      password: body.password,
      full_name: body.full_name,
    }),
  });

  const data = await backend.json().catch(() => ({}));

  if (!backend.ok) {
    return NextResponse.json(
      { detail: data.detail ?? 'Registration failed' },
      { status: backend.status }
    );
  }

  const response = NextResponse.json({ user: data.user }, { status: 201 });
  setAuthCookies(response, data.tokens.access_token, data.tokens.refresh_token, true);
  return response;
}
