export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-900 via-gray-900 to-gray-950 p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-white">Arada Intelligence OS</h1>
          <p className="mt-1 text-sm text-gray-400">Content intelligence, automated</p>
        </div>
        <div className="rounded-2xl bg-white p-8 shadow-2xl dark:bg-gray-800">{children}</div>
      </div>
    </main>
  );
}
