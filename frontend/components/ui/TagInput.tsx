'use client';

/** Multi-select tag input with autocomplete suggestions + free entry. */
import { useId, useMemo, useRef, useState } from 'react';

interface TagInputProps {
  label?: string;
  value: string[];
  onChange: (tags: string[]) => void;
  suggestions?: string[];
  placeholder?: string;
  maxTags?: number;
  error?: string;
}

export function TagInput({
  label,
  value,
  onChange,
  suggestions = [],
  placeholder = 'Add a tag…',
  maxTags = 10,
  error,
}: TagInputProps) {
  const [draft, setDraft] = useState('');
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const matches = useMemo(() => {
    const q = draft.trim().toLowerCase();
    if (!q) return [];
    return suggestions
      .filter((s) => s.toLowerCase().includes(q) && !value.includes(s))
      .slice(0, 6);
  }, [draft, suggestions, value]);

  const addTag = (raw: string) => {
    const tag = raw.trim().toLowerCase().replace(/\s+/g, '-');
    if (!tag || value.includes(tag) || value.length >= maxTags) return;
    onChange([...value, tag]);
    setDraft('');
  };

  const removeTag = (tag: string) => onChange(value.filter((t) => t !== tag));

  return (
    <div className="space-y-1">
      {label && (
        <label htmlFor={`${listId}-input`} className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
        </label>
      )}

      <div
        className={`flex flex-wrap items-center gap-1.5 rounded-lg border bg-white px-2 py-1.5
          focus-within:ring-2 focus-within:ring-brand-500 dark:bg-gray-800
          ${error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}`}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700"
          >
            {tag}
            <button
              type="button"
              aria-label={`Remove tag ${tag}`}
              onClick={() => removeTag(tag)}
              className="hover:text-brand-900"
            >
              ✕
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          id={`${listId}-input`}
          value={draft}
          placeholder={value.length === 0 ? placeholder : ''}
          role="combobox"
          aria-expanded={focused && matches.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          onChange={(e) => setDraft(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault();
              addTag(matches[0] && draft && matches[0].startsWith(draft) ? matches[0] : draft);
            } else if (e.key === 'Backspace' && !draft && value.length > 0) {
              removeTag(value[value.length - 1]!);
            }
          }}
          className="min-w-[100px] flex-1 border-none bg-transparent px-1 py-0.5 text-sm focus:outline-none dark:text-white"
        />
      </div>

      {focused && matches.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800"
        >
          {matches.map((s) => (
            <li key={s} role="option" aria-selected={false}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  addTag(s);
                }}
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-600">{error}</p>
      )}
      {value.length >= maxTags && (
        <p className="text-xs text-gray-400">Maximum {maxTags} tags</p>
      )}
    </div>
  );
}
