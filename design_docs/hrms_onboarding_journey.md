# Onboarding configuration

Onboarding is configured through native Settings. The custom HRMS journey, checklist UI, account orchestration, document endpoints and first-login access gate have been removed. The old onboarding UI and endpoints remain retired.

Existing native employee accounts, records, forms and workflow definitions are preserved for administrator configuration and audit. The HRMS installer no longer seeds the custom journey definitions or permissions. Native roles and permissions govern access.

Local email remains captured at http://localhost:8025; no external mail is sent by the local capture service.

HR Cockpit → Onboarding provides Add employee. It renders HRMS.Employee through the shared configured form renderer, with native role and employee relationship options. Saving uses public native APIs to create the employee and pending user; it creates no onboarding case, checklist, or custom journey.
