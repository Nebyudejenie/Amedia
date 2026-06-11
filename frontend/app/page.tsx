import { redirect } from 'next/navigation';
import { getTokens } from '@/lib/auth-server';

export default function Home() {
  const { accessToken, refreshToken } = getTokens();
  redirect(accessToken || refreshToken ? '/dashboard' : '/auth/login');
}
