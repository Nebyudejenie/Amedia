'use client';

/** Queue a video and poll its pipeline progress until complete/failed. */
import { useCallback, useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Spinner } from '@/components/ui/Spinner';
import { api, ApiError } from '@/lib/api';

type Status = 'queued' | 'generating' | 'complete' | 'failed';

interface VideoStatus {
  id: string;
  status: Status;
  stage: string;
  progress_label: string;
  duration_seconds: number | null;
  file_size_mb: number | null;
  error_message: string | null;
  playback_url?: string | null;
}

// Ordered stages → drives the progress bar fill
const STAGES = ['queued', 'script', 'images', 'audio', 'compose', 'upload', 'done'];

interface Props {
  articleId?: string;
  defaultTitle?: string;
}

export function VideoGenerator({ articleId, defaultTitle }: Props) {
  const [tone, setTone] = useState('professional');
  const [voice, setVoice] = useState('female');
  const [video, setVideo] = useState<VideoStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(
    (videoId: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const v = await api.get<VideoStatus>(`/api/v1/videos/${videoId}`);
          setVideo(v);
          if (v.status === 'complete' || v.status === 'failed') stopPolling();
        } catch {
          // transient error — keep polling
        }
      }, 3000);
    },
    [stopPolling]
  );

  useEffect(() => stopPolling, [stopPolling]);

  async function handleGenerate() {
    setSubmitting(true);
    setError(null);
    setVideo(null);
    try {
      const res = await api.post<{ video_id: string; status: Status }>(
        '/api/v1/videos/generate',
        { article_id: articleId, title: defaultTitle, tone, voice }
      );
      setVideo({
        id: res.video_id,
        status: 'queued',
        stage: 'queued',
        progress_label: 'Queued…',
        duration_seconds: null,
        file_size_mb: null,
        error_message: null,
      });
      poll(res.video_id);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 403
          ? e.message // monthly limit / upgrade hint
          : 'Could not start video generation. Try again.'
      );
    } finally {
      setSubmitting(false);
    }
  }

  const busy = video && (video.status === 'queued' || video.status === 'generating');
  const stageIndex = video ? Math.max(0, STAGES.indexOf(video.stage)) : 0;
  const progressPct = busy ? Math.round((stageIndex / (STAGES.length - 1)) * 100) : 0;

  return (
    <div className="space-y-4 rounded-xl border border-gray-200 p-5 dark:border-gray-700">
      <div className="grid grid-cols-2 gap-3">
        <Select
          label="Tone"
          value={tone}
          onChange={(e) => setTone(e.target.value)}
          disabled={!!busy}
          options={[
            { value: 'professional', label: 'Professional' },
            { value: 'casual', label: 'Casual' },
            { value: 'educational', label: 'Educational' },
          ]}
        />
        <Select
          label="Voice"
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          disabled={!!busy}
          options={[
            { value: 'female', label: 'Female' },
            { value: 'male', label: 'Male' },
          ]}
        />
      </div>

      <Button onClick={handleGenerate} disabled={submitting || !!busy} className="w-full">
        {submitting || busy ? <Spinner className="mr-2 h-4 w-4" /> : null}
        {busy ? 'Generating…' : 'Generate video'}
      </Button>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {busy && (
        <div className="space-y-2">
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className="h-full bg-brand-600 transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="text-sm text-gray-500">{video?.progress_label}</p>
        </div>
      )}

      {video?.status === 'complete' && (
        <div className="space-y-3">
          {video.playback_url && (
            <video controls className="w-full rounded-lg" src={video.playback_url} />
          )}
          <div className="flex gap-2">
            {video.playback_url && (
              <a
                href={video.playback_url}
                download
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
              >
                Download MP4
              </a>
            )}
            <button
              onClick={() => video.playback_url && navigator.clipboard.writeText(video.playback_url)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm dark:border-gray-600"
            >
              Copy link
            </button>
          </div>
          <p className="text-xs text-gray-400">
            {video.duration_seconds}s · {video.file_size_mb}MB
          </p>
        </div>
      )}

      {video?.status === 'failed' && (
        <p className="text-sm text-red-600">
          Generation failed: {video.error_message ?? 'unknown error'}
        </p>
      )}
    </div>
  );
}
