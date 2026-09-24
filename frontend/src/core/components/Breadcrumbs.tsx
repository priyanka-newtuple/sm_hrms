import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { BreadcrumbItem } from '../../shared/hooks/useBreadcrumbs';

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

export default function Breadcrumbs({ items, className }: BreadcrumbsProps) {
  if (items.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className={cn('flex items-center gap-1', className)}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && (
              <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 opacity-40" />
            )}
            {isLast ? (
              <span className="text-sm font-semibold">
                {item.label}
              </span>
            ) : item.href ? (
              <Link
                to={item.href}
                className="text-sm opacity-70 transition-opacity hover:opacity-100"
              >
                {item.label}
              </Link>
            ) : (
              <span className="text-sm opacity-70">{item.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
