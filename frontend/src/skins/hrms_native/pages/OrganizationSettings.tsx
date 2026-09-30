import { useHrmsOrganization } from '../capabilities';

export default function OrganizationSettings() {
  const organization = useHrmsOrganization();
  if (organization.isPending) return <p role="status">Loading organization…</p>;
  if (organization.isError) return <div role="alert"><p>Organization details could not be loaded.</p><button onClick={() => void organization.refetch()}>Retry</button></div>;
  const org = organization.data;
  return <section className="rounded-3xl border bg-white p-8">
    <h1 className="text-3xl font-light">Organization</h1>
    <p className="my-4 text-slate-600">Your HRMS tenant. Users, roles, forms and workflows belong to this organization.</p>
    <dl className="grid gap-4">
      {Object.entries({Name: org.name, 'Tenant ID': org.id, Slug: org.slug, 'Email domain': org.domain || 'Not configured', Status: org.status}).map(([label, value]) =>
        <div key={label}><dt className="text-sm text-slate-500">{label}</dt><dd className="break-all font-medium">{value}</dd></div>)}
    </dl>
  </section>;
}
