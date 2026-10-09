import { PageHero } from '../components/PageHero';
import { WorkFromHome } from './WorkFromHome';
export default function WorkFromHomePage() {
  return <main className="hrms-workspace-page"><PageHero title="Work from Home" intro="Request remote days and see the work location calendar." illustration="employees" /><WorkFromHome /></main>;
}
