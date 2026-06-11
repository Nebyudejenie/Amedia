'use client';

/** Drag-and-drop image upload with preview + client-side validation. */
import { useCallback, useRef, useState } from 'react';

interface FileDropzoneProps {
  label?: string;
  /** Current image URL (existing avatar) shown until a new file is picked. */
  currentUrl?: string | null;
  onFile: (file: File, previewUrl: string) => void;
  accept?: string[];
  maxSizeMb?: number;
}

export function FileDropzone({
  label = 'Upload image',
  currentUrl,
  onFile,
  accept = ['image/jpeg', 'image/png'],
  maxSizeMb = 5,
}: FileDropzoneProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File | undefined) => {
      setError(null);
      if (!file) return;

      if (!accept.includes(file.type)) {
        setError(`Only ${accept.map((t) => t.split('/')[1]).join(', ')} files are allowed`);
        return;
      }
      if (file.size > maxSizeMb * 1024 * 1024) {
        setError(`File must be under ${maxSizeMb}MB`);
        return;
      }

      const url = URL.createObjectURL(file);
      setPreview(url);
      onFile(file, url);
    },
    [accept, maxSizeMb, onFile]
  );

  const shown = preview ?? currentUrl;

  return (
    <div className="space-y-1">
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</p>

      <div
        role="button"
        tabIndex={0}
        aria-label={`${label} — drag and drop or browse`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files[0]);
        }}
        className={`flex cursor-pointer items-center gap-4 rounded-xl border-2 border-dashed p-4 transition-colors
          ${dragging ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-gray-300 hover:border-gray-400 dark:border-gray-600'}`}
      >
        {shown ? (
          // eslint-disable-next-line @next/next/no-img-element -- object URLs / external avatars
          <img src={shown} alt="Preview" className="h-16 w-16 rounded-full border object-cover" />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700">
            <svg className="h-6 w-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
          </div>
        )}
        <div className="text-sm">
          <p className="font-medium text-brand-600">Click to browse</p>
          <p className="text-gray-500">or drag &amp; drop · JPEG/PNG · max {maxSizeMb}MB</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={accept.join(',')}
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>

      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
