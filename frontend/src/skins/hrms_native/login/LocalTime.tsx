import { useEffect, useState } from 'react';

const formatter = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/** Viewer's local date and time, refreshed every 30 seconds. */
export function LocalTime() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return <time className="hrms-login-time" dateTime={now.toISOString()}><i aria-hidden="true" />{formatter.format(now)}</time>;
}
