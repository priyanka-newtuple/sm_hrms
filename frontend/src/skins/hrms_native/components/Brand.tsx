import { ArrowUpRight, BookOpen, BriefcaseBusiness, CalendarDays, FileText } from 'lucide-react';
import { Link, Outlet } from 'react-router-dom';
import { BrandWave } from './BrandWave';

export const informationCategories = [
  { id: 'policies', title: 'Policies', description: 'Our policies, clearly explained.', icon: FileText, types: ['HRMS.Policy'] },
  { id: 'learning', title: 'Learning & development', description: 'Make room for your next skill.', icon: BookOpen, types: ['HRMS.LearningEvent'] },
  { id: 'holidays', title: 'Holiday calendar', description: 'Plan ahead for the year.', icon: CalendarDays, types: ['HRMS.HolidayCalendar'] },
  { id: 'careers', title: 'Careers', description: 'Explore roles and opportunities.', icon: BriefcaseBusiness, types: ['HRMS.JobDescription', 'HRMS.JobOpening'] },
];

export function BrandLogo() {
  return <span className="hrms-logo"><img src="/hrms-brand/newtuple-logo.png" alt="Newtuple" /></span>;
}

export function BrandFooter({ compact = false }: { compact?: boolean }) {
  return <footer className={`hrms-brand-footer${compact ? ' hrms-brand-footer--compact' : ''}`}>
    {compact ? <BrandWave /> : <div className="hrms-footer-curves" aria-hidden="true" />}
  </footer>;
}

export function PublicLayout() {
  return <div className="hrms-brand hrms-public-shell"><header className="hrms-public-header"><Link to="/login" aria-label="Newtuple home"><BrandLogo /></Link><span className="hrms-product-label">People & workplace</span><Link className="hrms-outline-button" to="/public">Explore Newtuple <ArrowUpRight size={16} aria-hidden="true" /></Link></header><div className="hrms-public-body"><Outlet /></div><BrandFooter /></div>;
}

export function InformationLinks() {
  return <nav className="hrms-resource-grid" aria-label="Explore public information">{informationCategories.map(({ id, title, description, icon: Icon }) => <Link className="hrms-resource-card" key={id} to={`/public?category=${id}`}><Icon size={25} strokeWidth={1.25} aria-hidden="true" /><ArrowUpRight className="hrms-card-arrow" size={18} aria-hidden="true" /><h3>{title}</h3><p>{description}</p></Link>)}</nav>;
}
