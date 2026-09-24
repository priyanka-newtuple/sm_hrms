import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Styled table primitives — the Attio-style grid look shared by every data
 * table on the platform. Full-bleed (no card wrapper), hairline dividers on
 * both axes, plain header with muted labels.
 *
 * Use these directly for tables too bespoke for `<DataTable>`; use `DataTable`
 * for anything that is a list of records.
 */

type TableProps = React.ComponentProps<'table'> & {
  /** Classes for the scroll container that wraps the table. */
  containerClassName?: string;
  /** Styles for the scroll container — e.g. a `maxHeight` that makes rows scroll. */
  containerStyle?: React.CSSProperties;
};

function Table({ className, containerClassName, containerStyle, ...props }: TableProps) {
  return (
    <div
      data-slot="table-container"
      className={cn('w-full overflow-auto', containerClassName)}
      style={containerStyle}
    >
      <table
        data-slot="table"
        className={cn('w-full caption-bottom border-collapse text-sm', className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<'thead'>) {
  return (
    <thead
      data-slot="table-header"
      className={cn('[&_tr]:border-b [&_tr]:border-border/60', className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<'tbody'>) {
  return (
    <tbody
      data-slot="table-body"
      className={cn('[&_tr:last-child]:border-0', className)}
      {...props}
    />
  );
}

function TableFooter({ className, ...props }: React.ComponentProps<'tfoot'>) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn('border-t border-border/60 text-[12px] text-muted-foreground/70', className)}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<'tr'>) {
  return (
    <tr
      data-slot="table-row"
      className={cn('border-b border-border/50 transition-colors', className)}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<'th'>) {
  return (
    <th
      data-slot="table-head"
      scope="col"
      className={cn(
        'h-9 border-r border-border/50 px-3 text-left align-middle text-[13px] font-normal text-muted-foreground last:border-r-0',
        '[&:has([role=checkbox])]:w-9 [&:has([role=checkbox])]:pr-0',
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<'td'>) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        'border-r border-border/50 px-3 py-2 align-middle last:border-r-0',
        '[&:has([role=checkbox])]:pr-0 [&_svg]:[stroke-width:1.75]',
        className,
      )}
      {...props}
    />
  );
}

export { Table, TableHeader, TableBody, TableFooter, TableRow, TableHead, TableCell };
