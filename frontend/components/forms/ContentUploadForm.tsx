'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Controller } from 'react-hook-form';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { TagInput } from '@/components/ui/TagInput';
import { Modal } from '@/components/ui/Modal';
import { api } from '@/lib/api';
import { useZodForm } from '@/lib/use-zod-form';
import { applyApiError } from '@/lib/form-errors';
import { contentUploadSchema, type ContentUploadInput } from '@/lib/validators';

const SOURCE_OPTIONS = [
  { value: 'rss', label: 'RSS Feed' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'manual', label: 'Manual entry' },
];

const CONTENT_TYPE_OPTIONS = [
  { value: 'article', label: 'Article' },
  { value: 'video', label: 'Video' },
  { value: 'podcast', label: 'Podcast' },
  { value: 'newsletter', label: 'Newsletter' },
  { value: 'social_post', label: 'Social post' },
];

const TAG_SUGGESTIONS = [
  'tech', 'ai', 'news', 'business', 'finance', 'health',
  'sports', 'entertainment', 'science', 'politics', 'tutorial',
];

export function ContentUploadForm() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    control,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(contentUploadSchema, {
    defaultValues: {
      source_type: 'rss',
      content_type: 'article',
      tags: [],
      publish_now: true,
    },
  });

  const sourceType = watch('source_type');
  const publishNow = watch('publish_now');
  const title = watch('title', '');

  const onSubmit = async (data: ContentUploadInput) => {
    setFormError(null);
    try {
      const payload = {
        title: data.title,
        description: data.description || undefined,
        source_type: data.source_type,
        url: data.source_type === 'manual' ? undefined : data.source_url,
        content_type: data.content_type,
        tags: data.tags,
        scheduled_at: data.publish_now
          ? null
          : new Date(`${data.schedule_date}T${data.schedule_time}`).toISOString(),
      };
      const created = await api.post<{ id?: string; content_id?: string }>(
        '/content/sources',
        payload
      );
      setCreatedId(created.id ?? created.content_id ?? 'created');
    } catch (err) {
      const message = applyApiError(err, setError);
      if (message) setFormError(message);
    }
  };

  return (
    <>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
        {formError && (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
            {formError}
          </div>
        )}

        <div className="space-y-1">
          <Input
            label="Title *"
            placeholder="My content source"
            aria-required
            error={errors.title?.message}
            {...register('title')}
          />
          <p className={`text-right text-xs ${title.length > 180 ? 'text-orange-500' : 'text-gray-400'}`}>
            {title.length} / 200
          </p>
        </div>

        <Textarea
          label="Description"
          placeholder="What is this content about? (optional)"
          maxChars={5000}
          error={errors.description?.message}
          {...register('description')}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select
            label="Source type *"
            options={SOURCE_OPTIONS}
            aria-required
            error={undefined}
            {...register('source_type')}
          />
          <Select
            label="Content type *"
            options={CONTENT_TYPE_OPTIONS}
            aria-required
            {...register('content_type')}
          />
        </div>

        {/* URL only applies to non-manual sources */}
        {sourceType !== 'manual' && (
          <Input
            label="Source URL *"
            type="url"
            placeholder="https://example.com/feed.xml"
            aria-required
            error={errors.source_url?.message}
            {...register('source_url')}
          />
        )}

        <Controller
          control={control}
          name="tags"
          render={({ field }) => (
            <TagInput
              label="Tags"
              value={field.value}
              onChange={field.onChange}
              suggestions={TAG_SUGGESTIONS}
              error={errors.tags?.message}
            />
          )}
        />

        {/* Publish now vs schedule */}
        <div className="space-y-3 rounded-lg border border-gray-200 p-4 dark:border-gray-700">
          <label className="flex items-center justify-between text-sm font-medium text-gray-700 dark:text-gray-300">
            Publish immediately
            <input
              type="checkbox"
              role="switch"
              className="h-5 w-9 cursor-pointer appearance-none rounded-full bg-gray-300 transition-colors
                checked:bg-brand-600 before:block before:h-4 before:w-4 before:translate-x-0.5 before:translate-y-0.5
                before:rounded-full before:bg-white before:transition-transform checked:before:translate-x-[18px]"
              {...register('publish_now')}
            />
          </label>

          {!publishNow && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input
                label="Date *"
                type="date"
                aria-required
                error={errors.schedule_date?.message}
                {...register('schedule_date')}
              />
              <Input
                label="Time *"
                type="time"
                aria-required
                error={errors.schedule_time?.message}
                {...register('schedule_time')}
              />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" isLoading={isSubmitting}>
            {isSubmitting ? 'Creating…' : publishNow ? 'Create & publish' : 'Schedule content'}
          </Button>
        </div>
      </form>

      {/* Success confirmation */}
      <Modal
        open={createdId !== null}
        onClose={() => router.push('/dashboard/content')}
        title="Content created 🎉"
      >
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Your content source was created{publishNow ? ' and queued for analysis' : ' and scheduled'}.
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={() => router.push('/dashboard/content')}>
            Back to content
          </Button>
          <Button onClick={() => router.push(`/dashboard/content?item=${createdId}`)}>
            View details
          </Button>
        </div>
      </Modal>
    </>
  );
}
