import { Link } from 'react-router-dom';

export interface BreadcrumbSegment {
  label: string;
  to?: string;
}

// Breadcrumb — DESIGN_SPEC §6.20
export function Breadcrumb({ segments }: { segments: BreadcrumbSegment[] }) {
  return (
    <nav className="flex items-center gap-1.5 text-caption text-neutral-500">
      {segments.map((seg, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-neutral-300">/</span>}
          {seg.to ? (
            <Link to={seg.to} className="hover:text-primary-600 hover:underline">
              {seg.label}
            </Link>
          ) : (
            <span className="font-medium text-neutral-800">{seg.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
