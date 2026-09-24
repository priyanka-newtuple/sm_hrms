/** GitHub's official mark, sourced from the `simple-icons` package. `currentColor` fill so it adapts to whatever tile/theme colors it's placed on. */

import { siGithub } from 'simple-icons';

interface GitHubLogoProps {
  className?: string;
}

export default function GitHubLogo({ className }: GitHubLogoProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d={siGithub.path} />
    </svg>
  );
}
