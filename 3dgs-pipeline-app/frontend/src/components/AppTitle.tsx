import React from 'react';
import { useVersion } from '@/hooks/useVersion';

/**
 * App name, version and commit, centred in the top bar.
 *
 * Absolutely positioned rather than a third flex child: the two groups
 * flanking it change width (project name, step number, the Abort button), and
 * a centred flex item would drift with them.
 */
const AppTitle: React.FC = () => {
  const version = useVersion();

  const label = version?.version ? `v${version.version}` : null;
  const commit = version?.commit_short ?? null;

  return (
    <div className="pointer-events-none absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 select-none items-baseline gap-2 md:flex">
      <span className="text-sm font-semibold tracking-wide text-slate-200">
        {version?.name ?? '3DGS Pipeline App'}
      </span>
      {label && <span className="text-sm font-medium text-slate-400">{label}</span>}
      {commit && (
        <a
          href={version?.commit_url ?? undefined}
          target="_blank"
          rel="noreferrer"
          // Without a URL (no GitHub remote) it is a plain label, not a dead link.
          className={`pointer-events-auto rounded border border-slate-600 bg-slate-900/60 px-1.5 py-[1px] font-mono text-[10px] leading-4 text-slate-400 ${
            version?.commit_url ? 'hover:border-slate-500 hover:text-slate-200' : 'cursor-default'
          }`}
          title={
            [version?.commit, version?.branch && `branch ${version.branch}`, version?.commit_date]
              .filter(Boolean)
              .join('\n') || undefined
          }
          onClick={(e) => {
            if (!version?.commit_url) e.preventDefault();
          }}
        >
          {commit}
        </a>
      )}
    </div>
  );
};

export default AppTitle;
