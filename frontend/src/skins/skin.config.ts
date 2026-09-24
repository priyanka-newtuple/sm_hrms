/**
 * Default Skin Configuration
 *
 * Single source of truth for branding, navigation, entity types, board
 * stages, static lists, and runtime env vars. Change this file to
 * re-skin the platform (ATS → PMO → CRM, …) without touching
 * individual components.
 *
 * When creating a new skin for a customer deployment, copy this file to
 * e.g. `skins/resolveriq/skin.config.ts` and update the values there.
 * Do NOT leave any Tailwind class names in stateColors or StageConfig.color
 * — use raw CSS color values (hex / hsl / oklch) only.
 */

import { House, Settings, Layers, Waypoints, Megaphone } from 'lucide-react';
import type { SkinManifest } from './types';

/** Runtime environment variables, centralised from import.meta.env */
export const env = {
  bypassAuth: import.meta.env.VITE_BYPASS_AUTH === 'true',
  googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '',
  devProxyTarget: import.meta.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001',
  apiBase: import.meta.env.VITE_API_BASE_URL ?? '/api',
  bypassOrgId: import.meta.env.VITE_BYPASS_ORG_ID ?? '11111111-1111-1111-1111-111111111111',
  // Number of activity timeline events to load per page.
  timelinePageSize: Number(import.meta.env.VITE_TIMELINE_PAGE_SIZE) || 25,
} as const;

export const skin: SkinManifest = {
  // Must match the skinId prop passed to <SkinProvider> in main.tsx
  id: "state-machine",

  // This deployment composes workflow state fields from the shared Field and
  // Method libraries (see the Method Library panel on a workflow state), so it
  // opts into both library sections in Settings.
  optionalSettingsTabs: ["fields", "methods"],

  branding: {
    name: "State Machine",
    shortName: "NSM",
    logoText: "N",
    logoUrl: "",
    primaryColor: "cobalt",
    copyrightOwner: "State Machine",
    releaseDate: "March 18, 2026",
  },

  navigation: [
    { path: "/dashboard", label: "Dashboard", icon: House },
    {
      path: "/workflows",
      label: "Workflows",
      icon: Waypoints,
      showPipelineSubmenu: true,
    },
    { path: "/records", label: "Records", icon: Layers },
    {
      path: "/changelogs",
      label: "What's New",
      icon: Megaphone,
      position: "bottom",
    },
    {
      path: "/settings",
      label: "Settings",
      icon: Settings,
      position: "bottom",
    },
  ],

  entityTypes: [
    {
      entityType: "Application",
      schemaName: "application",
      schemaVersion: 1,
      machineName: "ats_application",
      machineVersion: 1,
      label: "Application",
      labelPlural: "Applications",
    },
    {
      entityType: "Job",
      schemaName: "job",
      schemaVersion: 1,
      label: "Job",
      labelPlural: "Jobs",
    },
    {
      entityType: "Candidate",
      schemaName: "candidate",
      schemaVersion: 1,
      label: "Candidate",
      labelPlural: "Candidates",
    },
    {
      entityType: "Requisition",
      schemaName: "requisition",
      schemaVersion: 1,
      label: "Requisition",
      labelPlural: "Requisitions",
    },
  ],

  board: {
    entityType: "Application",
    machineName: "ats_application",
    terminalStates: ["REJECTED", "WITHDRAWN"],

    // Tailwind equivalents for reference:
    //   gray-400 → #9ca3af   blue-400 → #60a5fa   indigo-400 → #818cf8
    //   purple-400 → #c084fc  amber-400 → #fbbf24  orange-400 → #fb923c
    //   green-500 → #22c55e   red-400 → #f87171    gray-300 → #d1d5db
    fallbackStages: [
      { state: "APPLIED", label: "Applied", color: "#9ca3af" },
      { state: "SCREENING", label: "Screening", color: "#60a5fa" },
      { state: "ASSIGNMENT", label: "Assignment", color: "#818cf8" },
      { state: "PANEL", label: "Panel", color: "#c084fc" },
      { state: "OFFER", label: "Offer", color: "#fbbf24" },
      { state: "BGV", label: "BGV", color: "#fb923c" },
      { state: "JOINED", label: "Joined", color: "#22c55e" },
    ],

    viewLabels: { kanban: "Board", list: "Table" },

    stateColors: {
      APPLIED: "#9ca3af",
      SCREENING: "#60a5fa",
      ASSIGNMENT: "#818cf8",
      PANEL: "#c084fc",
      OFFER: "#fbbf24",
      BGV: "#fb923c",
      JOINED: "#22c55e",
      REJECTED: "#f87171",
      WITHDRAWN: "#d1d5db",
    },
  },

  entityViews: [
    {
      entityType: "Application",
      titleField: "candidate_name",
      subtitleField: "job_title",
      listFields: [
        { source: "candidate_name", label: "Candidate", type: "text" },
        { source: "job_title", label: "Position", type: "text" },
      ],
      detailFields: [
        { source: "candidate_name", label: "Candidate Name", type: "text" },
        { source: "candidate_email", label: "Email", type: "email" },
        { source: "candidate_phone", label: "Phone", type: "phone" },
        { source: "job_title", label: "Position", type: "text" },
        { source: "job_department", label: "Department", type: "text" },
        { source: "candidate_source", label: "Source", type: "text" },
      ],
    },
    {
      entityType: "Job",
      titleField: "title",
      subtitleField: "department",
      listFields: [
        { source: "title", label: "Job Title", type: "text" },
        { source: "department", label: "Department", type: "text" },
        { source: "location", label: "Location", type: "text" },
        { source: "status", label: "Status", type: "badge" },
      ],
      detailFields: [
        { source: "title", label: "Job Title", type: "text" },
        { source: "department", label: "Department", type: "text" },
        { source: "location", label: "Location", type: "text" },
        { source: "hiring_manager", label: "Hiring Manager", type: "text" },
        { source: "status", label: "Status", type: "badge" },
      ],
    },
    {
      entityType: "Candidate",
      titleField: "name",
      subtitleField: "email",
      listFields: [
        { source: "name", label: "Name", type: "text" },
        { source: "email", label: "Email", type: "email" },
        { source: "source", label: "Source", type: "text" },
      ],
      detailFields: [
        { source: "name", label: "Full Name", type: "text" },
        { source: "email", label: "Email", type: "email" },
        { source: "phone", label: "Phone", type: "phone" },
        { source: "source", label: "Source", type: "text" },
      ],
    },
  ],

  staticLists: {
    departments: [
      "Engineering",
      "Product",
      "Design",
      "Data",
      "Marketing",
      "Sales",
      "Operations",
      "HR",
      "Finance",
    ],
    locations: [
      "San Francisco, CA",
      "New York, NY",
      "Austin, TX",
      "Seattle, WA",
      "Remote",
      "London, UK",
      "Berlin, Germany",
    ],
    sources: [
      "LinkedIn",
      "Indeed",
      "Glassdoor",
      "Referral",
      "Company Website",
      "Job Fair",
      "Recruiter",
      "Other",
    ],
    jobStatuses: ["OPEN", "ON_HOLD", "CLOSED"],
  },
};
