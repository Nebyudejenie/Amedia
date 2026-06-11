/** POST /api/auth/logout — revoke token on backend, clear cookies. */
import { NextResponse } from 'next/server';
import { API_URL, getTokens, clearAuthCookies } from '@/lib/auth-server';

export async function POST() {
  const { accessToken } = getTokens();

  // Best-effort backend revocation; cookies are cleared regardless
  if (accessToken) {
    await fetch(`${API_URL}/auth/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    }).catch(() => {});
  }

  const response = NextResponse.json({ ok: true });
  clearAuthCookies(response);
  return response;
}
