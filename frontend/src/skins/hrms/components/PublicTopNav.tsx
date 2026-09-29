import { NavLink } from "react-router-dom";

import logo from "@/skins/hrms/assets/newtuple-wordmark.png";

const NAV_LINK_CLASS =
  "whitespace-nowrap rounded-full px-2 py-1.5 text-[11px] font-medium transition-colors duration-hover ease-brand sm:px-3 sm:py-2 sm:text-sm";

export const PUBLIC_NAV = [
  { label: "Organization Policies", to: "/organization-policies" },
  { label: "Travel Request", to: "/travel-request" },
  { label: "Open Positions / Referrals", to: "/referrals" },
  { label: "L&D calendar", to: "/ld-calendar" },
  { label: "Holiday calendar", to: "/holidays" },
  { label: "Tiffin Tuple", href: "https://internalapps.newtuple.com/" },
  { label: "Templates", href: "https://drive.google.com/drive/folders/17COpLtuSfClDYcWGzLOKYktXLrKF1Pb_" }
] as const;

export function PublicTopNav() {
  return (
    <header className="relative z-20 shrink-0 border-b border-white/60 bg-white/90 backdrop-blur">
      <div className="flex min-h-14 flex-wrap items-center justify-between gap-x-3 gap-y-2 px-3 py-2 sm:px-6 lg:px-12 xl:px-20">
        <NavLink to="/login" className="shrink-0" aria-label="Newtuple HRMS">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-cobalt text-xs font-semibold text-white sm:hidden">
            N
          </span>
          <img src={logo} alt="Newtuple" className="hidden h-7 w-auto sm:block" />
        </NavLink>
        <nav className="flex min-w-0 flex-wrap items-center justify-end gap-0.5 sm:gap-1">
          {PUBLIC_NAV.map((item) =>
            "href" in item ? (
              <a
                key={item.href}
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className={`${NAV_LINK_CLASS} text-gray-900 hover:bg-gray-50 hover:text-cobalt`}
              >
                {item.label}
              </a>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `${NAV_LINK_CLASS} ${
                    isActive ? "bg-cobalt text-white" : "text-gray-900 hover:bg-gray-50 hover:text-cobalt"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ),
          )}
        </nav>
      </div>
    </header>
  );
}
