import { sourceMeta } from '../data/mockData';
import type { SourceType } from '../data/types';
import { cx } from '../lib/cx';

/** A coloured pill showing where a memory came from (Article / Web Link / ...). */
export default function SourceBadge({ type }: { type: SourceType }) {
  const meta = sourceMeta[type];
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        meta.badgeClass,
      )}
    >
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}
