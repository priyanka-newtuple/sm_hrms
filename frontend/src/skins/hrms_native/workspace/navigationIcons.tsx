import { forwardRef, useImperativeHandle, useState, type HTMLAttributes } from 'react';
import { Building2, CalendarClock, ClipboardList, ContactRound, FileSignature, House, Laptop, Mail, Megaphone, Network, Bot, UserRoundMinus, UserRoundCog, type LucideIcon } from 'lucide-react';
import { type AnimatedIconHandle } from '../animated-icons';

// Adapt Lucide outline glyphs to the shared navigation icon interface.
function navigationIcon(name: string, Glyph: LucideIcon) {
  const Icon = forwardRef<AnimatedIconHandle, HTMLAttributes<HTMLDivElement> & { size?: number }>(({ size = 19, ...props }, ref) => {
    const [active, setActive] = useState(false);
    useImperativeHandle(ref, () => ({ startAnimation: () => setActive(true), stopAnimation: () => setActive(false) }), []);
    return <div {...props}><Glyph size={size} strokeWidth={2} className={`motion-safe:transition-transform motion-safe:duration-150 ${active ? 'motion-safe:-translate-y-px' : ''}`}  /></div>;
  });
  Icon.displayName = name;
  return Icon;
}
export const TaskMenuIcon = navigationIcon('TaskMenuIcon', ClipboardList);
export const HrMenuIcon = navigationIcon('HrMenuIcon', UserRoundCog);
export const OffboardingMenuIcon = navigationIcon('OffboardingMenuIcon', UserRoundMinus);
export const OfferMenuIcon = navigationIcon('OfferMenuIcon', FileSignature);
export const PublishingMenuIcon = navigationIcon('PublishingMenuIcon', Megaphone);
export const CustomerMenuIcon = navigationIcon('CustomerMenuIcon', Building2);
export const AllocationMenuIcon = navigationIcon('AllocationMenuIcon', Network);
export const AssetMenuIcon = navigationIcon('AssetMenuIcon', Laptop);
export const LeaveMenuIcon = navigationIcon('LeaveMenuIcon', CalendarClock);
export const HomeMenuIcon = navigationIcon('HomeMenuIcon', House);
export const AgentMenuIcon = navigationIcon('AgentMenuIcon', Bot);
export const DirectoryMenuIcon = navigationIcon('DirectoryMenuIcon', ContactRound);
export const MailMenuIcon = navigationIcon('MailMenuIcon', Mail);
