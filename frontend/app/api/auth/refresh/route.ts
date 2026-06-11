/** POST /api/auth/refresh — exchange refresh cookie for a new access token. */
import { NextResponse } from 'next/server';
import { API_URL, getTokens, setAuthCookies, clearAuthCookies } from '@/lib/auth-server';

export async function POST() {
  const { refreshToken } = getTokens();

  if (!refreshToken) {
    return NextResponse.json({ detail: 'No refresh token' }, { status: 401 });
  }

  const backend = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const data = await backend.json().catch(() => ({}));

  if (!backend.ok) {
    const response = NextResponse.json({ detail: 'Session expired' }, { status: 401 });
    clearAuthCookies(response);
    return response;
  }

  const response = NextResponse.json({ ok: true });
  setAuthCookies(response, data.access_token, data.refresh_token ?? refreshToken, true);
  return response;
}
