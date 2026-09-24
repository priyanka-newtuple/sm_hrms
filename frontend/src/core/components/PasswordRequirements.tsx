import { Check } from 'lucide-react';

interface Props {
  password: string;
}

const SPECIAL_CHAR_RE = /[!@#$%^&*(),.?":{}|<>\[\]\\;'`~\-_+=^]/;

const STRENGTH_LABELS = ['', 'Very Weak', 'Weak', 'Fair', 'Good', 'Strong'];
const STRENGTH_BAR_COLORS = ['', 'bg-destructive', 'bg-orange-400', 'bg-yellow-400', 'bg-lime-500', 'bg-success'];
const STRENGTH_TEXT_COLORS = ['', 'text-destructive', 'text-orange-500', 'text-yellow-500', 'text-lime-600', 'text-success'];

function getStrengthScore(pwd: string): number {
  if (!pwd) return 0;
  let score = 0;
  if (pwd.length >= 8) score++;
  if (pwd.length >= 12) score++;
  if (SPECIAL_CHAR_RE.test(pwd)) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  return score;
}

export default function PasswordRequirements({ password }: Props) {
  if (!password) return null;

  const hasMinLength = password.length >= 8;
  const hasSpecialChar = SPECIAL_CHAR_RE.test(password);
  const hasUppercase = /[A-Z]/.test(password);
  const score = getStrengthScore(password);

  return (
    <div className="mt-3 bg-muted/50 rounded-xl p-4 space-y-3">
      <div>
        <p className="text-sm font-semibold text-foreground mb-2">Your Password must include</p>
        <ul className="space-y-1.5">
          <li aria-label={`At least 8 characters: ${hasMinLength ? 'met' : 'not met'}`} className="flex items-center gap-2 text-sm text-foreground">
            <Check
              aria-hidden={true}
              className={`w-4 h-4 flex-shrink-0 transition-colors ${hasMinLength ? 'text-cobalt' : 'text-muted-foreground/60'}`}
              strokeWidth={2.5}
            />
            At least 8 characters
          </li>
          <li aria-label={`At least one uppercase letter: ${hasUppercase ? 'met' : 'not met'}`} className="flex items-center gap-2 text-sm text-foreground">
            <Check
              aria-hidden={true}
              className={`w-4 h-4 flex-shrink-0 transition-colors ${hasUppercase ? 'text-cobalt' : 'text-muted-foreground/60'}`}
              strokeWidth={2.5}
            />
            At least one uppercase letter
          </li>
          <li aria-label={`At least one special character: ${hasSpecialChar ? 'met' : 'not met'}`} className="flex items-center gap-2 text-sm text-foreground">
            <Check
              aria-hidden={true}
              className={`w-4 h-4 flex-shrink-0 transition-colors ${hasSpecialChar ? 'text-cobalt' : 'text-muted-foreground/60'}`}
              strokeWidth={2.5}
            />
            At least one special character
          </li>
        </ul>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-semibold text-foreground">Password Strength</p>
          <span className={`text-sm font-medium transition-colors ${STRENGTH_TEXT_COLORS[score]}`}>
            {STRENGTH_LABELS[score]}
          </span>
        </div>
        <div className="flex gap-1.5">
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                i <= score ? STRENGTH_BAR_COLORS[score] : 'bg-accent'
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function isPasswordValid(password: string): boolean {
  return (
    password.length >= 8 &&
    /[A-Z]/.test(password) &&
    SPECIAL_CHAR_RE.test(password)
  );
}
