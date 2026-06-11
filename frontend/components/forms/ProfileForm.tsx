'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { FileDropzone } from '@/components/ui/FileDropzone';
import { api, ApiError, type User } from '@/lib/api';
import { useZodForm } from '@/lib/use-zod-form';
import { profileSchema, type ProfileInput } from '@/lib/validators';
import { relativeTime } from '@/lib/format';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';

export function ProfileForm() {
  const { user, setUser } = useAuthStore();
  const addToast = useUiStore((s) => s.addToast);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isDirty },
  } = useZodForm(profileSchema, {
    defaultValues: {
      full_name: user?.full_name ?? '',
      bio: '',
    },
  });

  const hasChanges = isDirty || avatarFile !== null;

  const onSubmit = async (data: ProfileInput) => {
    try {
      // 1. Avatar first (multipart) — endpoint may not exist yet
      if (avatarFile) {
        const formData = new FormData();
        formData.append('file', avatarFile);
        try {
          await fetch('/api/proxy/api/v1/users/me/avatar', {
            method: 'POST',
            body: formData,
          });
        } catch {
          addToast('Avatar upload not available yet — saved profile fields only', 'info');
        }
      }

      // 2. Profile fields
      const updated = await api.patch<User>('/api/v1/users/me', {
        full_name: data.full_name,
        ...(data.bio ? { bio: data.bio } : {}),
      });
      setUser(updated);
      setAvatarFile(null);
      setLastSaved(new Date());
      addToast('Profile updated', 'success');
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Update failed', 'error');
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <FileDropzone
        label="Avatar"
        currentUrl={
          user?.avatar_url ?? `https://api.dicebear.com/8.x/initials/svg?seed=${user?.email}`
        }
        onFile={(file) => setAvatarFile(file)}
      />

      <Input label="Email" value={user?.email ?? ''} disabled />

      <Input
        label="Full name *"
        aria-required
        placeholder="Your name"
        error={errors.full_name?.message}
        {...register('full_name')}
      />

      <Textarea
        label="Bio"
        placeholder="A short description about you (optional)"
        maxChars={500}
        error={errors.bio?.message}
        {...register('bio')}
      />

      <div className="flex items-center justify-between">
        <Button type="submit" isLoading={isSubmitting} disabled={!hasChanges}>
          {isSubmitting ? 'Saving…' : 'Save changes'}
        </Button>
        {lastSaved && (
          <p className="text-xs text-gray-400">Last updated {relativeTime(lastSaved)}</p>
        )}
      </div>
    </form>
  );
}
