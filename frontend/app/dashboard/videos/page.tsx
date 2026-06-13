'use client';

/** Video studio: generate a new video and browse previously generated ones. */
import { useEffect, useState } from 'react';

import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { VideoGenerator } from '@/components/videos/VideoGenerator';
import { api } from '@/lib/api';

interface VideoRow {
  id: string;
  title: string;
  status: 'queued' | 'generating' | 'complete' | 'failed';
  progress_label: string;
  duration_seconds: number | null;
  file_size_mb: number | null;
  playback_url?: string | null;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  complete: 'text-green-600',
  failed: 'text-red-600',
  generating: 'text-blue-600',
  queued: 'text-gray-500',
};

export default function VideosPage() {
  const [videos, setVideos] = useState<VideoRow[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const res = await api.get<{ videos: VideoRow[] }>('/api/v1/videos');
      setVideos(res.videos);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // Refresh the list periodically so in-flight jobs update
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">Video Studio</h1>
        <p className="text-sm text-gray-500">Turn an article into a narrated 90-second video.</p>
      </div>

      <Card>
        <h2 className="mb-3 text-lg font-medium">New video</h2>
        <VideoGenerator />
      </Card>

      <Card>
        <h2 className="mb-3 text-lg font-medium">Your videos</h2>
        {loading ? (
          <Spinner className="mx-auto my-8 h-6 w-6" />
        ) : videos.length === 0 ? (
          <EmptyState title="No videos yet" description="Generate your first video above." />
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {videos.map((v) => (
              <li key={v.id} className="flex items-center justify-between py-3">
                <div className="min-w-0">
                  <p className="truncate font-medium text-gray-900 dark:text-white">{v.title}</p>
                  <p className={`text-xs ${STATUS_STYLE[v.status] ?? 'text-gray-500'}`}>
                    {v.status === 'complete'
                      ? `${v.duration_seconds}s · ${v.file_size_mb}MB`
                      : v.progress_label}
                  </p>
                </div>
                {v.status === 'complete' && v.playback_url && (
                  <a
                    href={v.playback_url}
                    className="shrink-0 text-sm font-medium text-brand-600 hover:underline"
                  >
                    Open
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
