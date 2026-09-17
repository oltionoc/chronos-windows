import clsx from 'clsx';

// Skeleton Loader — DESIGN_SPEC §6.27
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded-sm bg-neutral-100', className)} />;
}

export function KeyValueGridSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i}>
          <Skeleton className="mb-2 h-3 w-24" />
          <Skeleton className="h-4 w-36" />
        </div>
      ))}
    </div>
  );
}
