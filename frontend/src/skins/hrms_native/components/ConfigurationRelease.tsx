import { useQuery } from '@tanstack/react-query';
import { request } from '../../../core/services/api/client';

type ReleaseStatus = {
  application_revision: string;
  releases: { name: string; status: string; checksum: string | null; verified_at: string | null; pending: string | null }[];
};

export function ConfigurationRelease() {
  const status = useQuery({
    queryKey: ['hrms', 'configuration-release'],
    queryFn: () => request<ReleaseStatus>('/hrms/configuration-release'),
    staleTime: 0,
  });
  const frontend = import.meta.env.VITE_HRMS_RELEASE_SHA || 'development';
  return <section className="hrms-surface mt-6 p-6" aria-label="Release information">
    <h2 className="text-lg font-semibold">Release information</h2>
    {status.isPending ? <p role="status">Loading release information…</p> : status.isError ?
      <div role="alert"><p>Release information could not be loaded.</p><button onClick={() => void status.refetch()}>Retry</button></div> : <>
        <dl className="mt-3 grid gap-2 text-sm">
          <div><dt className="text-slate-500">Interface version</dt><dd className="break-all">{frontend}</dd></div>
          <div><dt className="text-slate-500">Application version</dt><dd className="break-all">{status.data.application_revision}</dd></div>
        </dl>
        {frontend !== 'development' && status.data.application_revision !== 'development' && frontend !== status.data.application_revision &&
          <p role="alert" className="mt-3 text-amber-700">The interface and application are running different releases.</p>}
        {!status.data.releases.length ? <p className="mt-3 text-slate-600">Configuration promotion has not been set up. Settings are managed separately in this environment.</p> :
          status.data.releases.map(release => <div key={release.name} className="mt-4 rounded-xl border border-slate-200 p-4">
            <p className="font-semibold">{release.name} · {release.status.replaceAll('_', ' ')}</p>
            {release.verified_at && <p className="text-sm text-slate-600">Last verified: {new Date(release.verified_at).toLocaleString()}</p>}
            {release.checksum && <p className="break-all text-xs text-slate-500">Configuration checksum: {release.checksum}</p>}
            {release.pending && <p role="alert">Needs review: {release.pending}</p>}
          </div>)}
        <p className="mt-3 text-sm text-slate-500">This shows the last recorded promotion. A configuration comparison is needed to check subsequent Settings changes.</p>
      </>}
  </section>;
}
