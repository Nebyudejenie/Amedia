/**
 * Catch-all proxy: forwards /api/proxy/<path> to FastAPI with the Bearer
 * token from the httpOnly cookie attached. The browser never holds the JWT.
 */
import { NextRequest, NextResponse } from 'next/server';
import { API_URL, getTokens } from '@/lib/auth-server';

async function proxy(request: NextRequest, { params }: { params: { path: string[] } }) {
  const { accessToken } = getTokens();
  const targetUrl = `${API_URL}/${params.path.join('/')}${request.nextUrl.search}`;

  const headers: Record<string, string> = {};
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  const contentType = request.headers.get('content-type');
  if (contentType) headers['Content-Type'] = contentType;

  const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.text();

  const backend = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    // Never follow redirects from the backend
    redirect: 'manual',
  });

  const responseBody = await backend.text();
  const response = new NextResponse(responseBody || null, {
    status: backend.status,
    headers: {
      'Content-Type': backend.headers.get('content-type') ?? 'application/json',
    },
  });

  // Pass through pagination header
  const totalCount = backend.headers.get('x-total-count');
  if (totalCount) response.headers.set('X-Total-Count', totalCount);

  return response;
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };
