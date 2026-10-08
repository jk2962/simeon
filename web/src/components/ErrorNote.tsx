// A plain inline error. Grayscale like everything else: no red.
export function ErrorNote({ message }: { message: string }) {
  return (
    <p role="alert" className="max-w-prose border-l-2 border-ink bg-surface px-4 py-3 text-sm">
      {message}
    </p>
  );
}
