import loginBg from "@/skins/hrms/assets/login_page.png";
import { Badge } from "@/skins/hrms/components/Badge";
import { PublicContent, PublicHero, PublicPageLayout } from "@/skins/hrms/components/PublicPageLayout";

export { ReferralsPage } from "./ReferralsPage";
export { LdCalendarPage } from "./LdCalendarPage";
export { OrganizationPoliciesPage } from "./OrganizationPoliciesPage";
export { TravelRequestPage } from "./TravelRequestPage";

const OPEN_ROLES = [
  {
    id: "fe",
    title: "Frontend Engineer",
    team: "Product",
    location: "Bengaluru",
    type: "Full-time",
    referral: "₹25,000",
  },
  {
    id: "de",
    title: "Senior Data Engineer",
    team: "Data",
    location: "Bengaluru / Hybrid",
    type: "Full-time",
    referral: "₹40,000",
  },
  {
    id: "pd",
    title: "Product Designer",
    team: "Design",
    location: "Remote (India)",
    type: "Full-time",
    referral: "₹25,000",
  },
  {
    id: "pp",
    title: "People Partner",
    team: "People",
    location: "Bengaluru",
    type: "Full-time",
    referral: "₹20,000",
  },
];

export function OpenPositionsPage() {
  return (
    <PublicPageLayout>
      <PublicHero
        image={loginBg}
        kicker="Careers"
        title="Open Positions"
        accent="Find your next role."
        blurb="Roles currently hiring at Newtuple. Browse freely — you do not need to sign in to view openings."
      />
      <PublicContent>
        <div className="grid gap-4 sm:grid-cols-2">
          {OPEN_ROLES.map((role) => (
            <div key={role.id} className="rounded-card bg-white p-6 shadow-lg shadow-gray-900/5">
              <h2 className="text-base font-semibold text-gray-900">{role.title}</h2>
              <p className="mt-1 text-sm font-light text-gray-600">
                {role.team} · {role.location}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge tone="info">{role.type}</Badge>
                <Badge tone="neutral">Open</Badge>
              </div>
            </div>
          ))}
        </div>
      </PublicContent>
    </PublicPageLayout>
  );
}
