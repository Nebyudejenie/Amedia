import type { Metadata } from 'next';
import { Card } from '@/components/ui/Card';
import { ContentUploadForm } from '@/components/forms/ContentUploadForm';

export const metadata: Metadata = { title: 'Add content' };

export default function NewContentPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Add content</h1>
        <p className="mt-1 text-sm text-gray-500">
          Connect a source or enter content manually. Required fields are marked *.
        </p>
      </div>
      <Card>
        <ContentUploadForm />
      </Card>
    </div>
  );
}
