import type { ReactNode } from "react";

import curves from "@/skins/hrms/assets/geometric-curves-strip.png";
import { PublicTopNav } from "@/skins/hrms/components/PublicTopNav";

export function PublicPageLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-[#F8F4EF]">
      <PublicTopNav />
      {children}
      <PublicFooter />
    </div>
  );
}

export function PublicHero({
  image,
  kicker,
  title,
  accent,
  blurb,
  children,
  imageClass = "inset-0 h-full w-full object-[70%_center]",
  overlayClass = "bg-gradient-to-r from-[#F8F4EF] via-[#F8F4EF]/90 to-transparent",
}: {
  image: string;
  kicker: string;
  title: string;
  accent?: string;
  blurb: string;
  children?: ReactNode;
  imageClass?: string;
  overlayClass?: string;
}) {
  return (
    <section className="relative overflow-hidden">
      <img src={image} alt="" className={`absolute max-w-none object-cover ${imageClass}`} />
      <div className={`absolute inset-0 ${overlayClass}`} />
      <div className="relative mx-auto max-w-6xl px-6 py-14 sm:px-8 lg:py-20">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-cobalt">{kicker}</p>
        <h1 className="mt-3 max-w-md text-4xl font-semibold leading-tight tracking-tight text-gray-900 sm:text-5xl">
          {title}
          {accent ? <span className="mt-1 block text-cobalt">{accent}</span> : null}
        </h1>
        <p className="mt-4 max-w-md text-sm font-light leading-relaxed text-gray-600 sm:text-base">{blurb}</p>
        {children}
      </div>
    </section>
  );
}

export function PublicContent({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className="relative z-10 mx-auto w-full max-w-6xl flex-1 px-6 pb-10 sm:px-8">
      <div className={`-mt-8 ${className}`}>{children}</div>
    </div>
  );
}

export function SignInToActNotice({ action }: { action: string }) {
  return (
    <p className="rounded-xl bg-cobalt/5 px-3 py-2 text-sm text-gray-700">
      Sign in with your Newtuple account to {action}. You can read this page without signing in.
    </p>
  );
}

export function PublicFooter() {
  return (
    <footer className="mt-auto w-full">
      <img src={curves} alt="" className="block h-24 w-full object-fill sm:h-28" />
    </footer>
  );
}
