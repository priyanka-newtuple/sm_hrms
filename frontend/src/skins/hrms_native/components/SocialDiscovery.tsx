import { ArrowUpRight } from 'lucide-react';
import { siYoutube, siInstagram, siX } from 'simple-icons';

// Only verified or owner-provided account URLs belong here. Never guess handles.
const channels = [
  { id: 'linkedin', name: 'LinkedIn', label: 'Ideas & milestones', description: 'Follow our people, progress and perspectives.', action: 'Follow Newtuple', href: 'https://www.linkedin.com/company/newtuple/posts/', path: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.35V9h3.414v1.561h.049c.476-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.124 2.062 2.062 0 0 1 0 4.124zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z' },
  { id: 'youtube', name: 'YouTube', label: 'Watch & learn', description: 'A closer look at ideas in action.', action: 'Watch our channel', href: 'https://www.youtube.com/@NewtupleTechnologies', path: siYoutube.path },
  { id: 'instagram', name: 'Instagram', label: 'Life at Newtuple', description: 'The people and moments behind the work.', action: 'Explore our stories', href: 'https://www.instagram.com/newtupletechnologies/', path: siInstagram.path },
  { id: 'x', name: 'X', label: 'Join the conversation', description: 'Fresh thoughts, shared with the world.', action: 'Follow along', href: 'https://x.com/newtuple', path: siX.path },
];

export function SocialDiscovery() {
  return <div className="hrms-social-grid" aria-label="Newtuple on social media">
    {channels.map(channel => {
      const content = <>
        <div className="hrms-social-top"><span className="hrms-social-logo"><svg viewBox="0 0 24 24" aria-hidden="true"><path d={channel.path} /></svg></span><span className="hrms-social-name">{channel.name}</span>{channel.href && <ArrowUpRight className="hrms-social-arrow" size={18} aria-hidden="true" />}</div>
        <h3>{channel.label}</h3>
        {!channel.href && <span className="hrms-social-action">Link coming soon</span>}
      </>;
      return channel.href ? <a key={channel.id} className={`hrms-social-card hrms-social-${channel.id}`} href={channel.href} target="_blank" rel="noopener noreferrer" aria-label={`Newtuple on ${channel.name} (opens in a new tab)`}>{content}</a>
        : <div key={channel.id} className={`hrms-social-card hrms-social-${channel.id}`} aria-label={`Newtuple on ${channel.name}: link coming soon`}>{content}</div>;
    })}
  </div>;
}
