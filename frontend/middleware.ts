/**
 * Edge middleware: protects /dashboard/*, refreshes tokens near expiry.
 *
 * Flow on every request to a protected route:
 *  1. No access token + no refresh token  → redirect to /auth/login
 *  2. Access token valid and not near expiry → continue
 *  3. Access token missing/expiring within 5 min + refresh token present
 *     → call backend /auth/refresh, set new cookie, continue
 *  4. Refresh fails → clear cookies, redirect to /auth/login
 */
import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL ?? 'http://192.168.1.200:8000';
const ACCESS_COOKIE = 'arada_access';
const REFRESH_COOKIE = 'arada_refresh';
const REFRESH_THRESHOLD_SECONDS = 5 * 60; // refresh 5 minutes before expiry

const PROTECTED_PREFIXES = ['/dashboard'];
const AUTH_PAGES = ['/auth/login', '/auth/register'];

function decodeExp(token: string): number {
  try {
    const part = token.split('.')[1];
    if (!part) return 0;
    const payload = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp ?? 0;
  } catch {
    return 0;
  }
}

function redirectToLogin(request: NextRequest, expired = false): NextResponse {
  const url = new URL('/auth/login', request.url);
  url.searchParams.set('next', request.nextUrl.pathname);
  if (expired) url.searchParams.set('expired', '1');
  const response = NextResponse.redirect(url);
  response.cookies.set(ACCESS_COOKIE, '', { maxAge: 0, path: '/' });
  response.cookies.set(REFRESH_COOKIE, '', { maxAge: 0, path: '/' });
  return response;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;

  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  // Already authenticated users skip the login/register pages
  if (isAuthPage && accessToken) {
    const secondsLeft = decodeExp(accessToken) - Math.floor(Date.now() / 1000);
    if (secondsLeft > 0) {
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }
  }

  if (!isProtected) return NextResponse.next();

  // --- Protected route ---
  if (!accessToken && !refreshToken) return redirectToLogin(request);

  const secondsLeft = accessToken ? decodeExp(accessToken) - Math.floor(Date.now() / 1000) : 0;

  // Token healthy: continue
  if (secondsLeft > REFRESH_THRESHOLD_SECONDS) return NextResponse.next();

  // Token expiring/expired: try refresh
  if (!refreshToken) return redirectToLogin(request, true);

  try {
    const refreshed = await fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!refreshed.ok) return redirectToLogin(request, true);

    const data = await refreshed.json();
    const response = NextResponse.next();
    response.cookies.set(ACCESS_COOKIE, data.access_token, {
      httpOnly: true,
      secure: process.env.COOKIE_SECURE === 'true',
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60,
    });
    return response;
  } catch {
    return redirectToLogin(request, true);
  }
}

export const config = {
  matcher: ['/dashboard/:path*', '/auth/login', '/auth/register'],
};
