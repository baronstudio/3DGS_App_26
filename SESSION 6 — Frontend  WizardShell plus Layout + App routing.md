## CONTEXT
Project: 3DGS Pipeline Web App — React + TypeScript
After Session 5: pipelineStore + hooks fully implemented.
Current files (need full implementation):
- components/wizard/WizardShell.tsx → <div>Wizard Shell</div>
- components/wizard/StepNav.tsx → <div>Step Navigator</div>
- pages/MainPage.tsx → 2-col layout with hardcoded dummy components
- App.tsx → setup screen bypassed (const proceeded = true)

## TASK

### 1. components/wizard/WizardShell.tsx
Main layout: 3-zone layout using CSS grid or flexbox

Layout specification:
  ┌─────────────────────────────────────────────────────────────┐
  │  TOP BAR: [ProjectName] > Step N/6  │  [⬛ ABORT]          │
  ├──────────┬──────────────────────────┬──────────────────────┤
  │ StepNav  │   Current Step Content   │  LiveLog (toggle)    │
  │ (200px)  │   (flex-1)               │  (300px, collapsible)│
  └──────────┴──────────────────────────┴──────────────────────┘

- TopBar: shows currentProjectId name (from store), step X/6, global Abort button
  Abort calls controlPipeline(id, "abort") and confirms with a dialog first
- StepNav: imported from StepNav.tsx
- Main content: renders the correct step component based on currentStep from store
  Import all 6 step components lazily (React.lazy + Suspense)
- Right panel (LiveLog): uses LiveLog panel component, collapsible with a toggle button
  Default: visible on desktop, hidden on mobile
- Background: bg-slate-900, accent color #00D4FF for active elements

### 2. components/wizard/StepNav.tsx
Vertical sidebar navigator:

Steps definition:
  1: { icon: Upload, label: "Import", key: "import" }
  2: { icon: Film, label: "Extract Frames", key: "extract" }
  3: { icon: Crosshair, label: "RC Alignment", key: "rc" }
  4: { icon: Cpu, label: "LFS Training", key: "lfs" }
  5: { icon: Package, label: "Export", key: "export" }
  6: { icon: Box, label: "Blender Scene", key: "blender" }

Each step item:
  - Icon (lucide-react)
  - Label
  - Status badge: "pending" (grey) | "running" (cyan pulse) | "done" (green ✓) | "error" (red ✗)
  - Clickable only if step <= max(done steps) + 1 (bypass: allow all clicks in dev mode)
  - Currently active step: cyan border-l-2, brighter text
  - Read stepStatuses from pipelineStore

### 3. pages/MainPage.tsx
Replace current layout with WizardShell:
  import WizardShell from '@/components/wizard/WizardShell'
  export const MainPage = () => <WizardShell />

### 4. App.tsx
Restore setup screen flow:
  - Show SetupScreen if settings not loaded OR if it's first run (no projects yet AND no stubs disabled)
  - After user clicks "Proceed", show MainPage (which renders WizardShell)
  - Initialize useWebSocket() at App level (so WS connects once globally)
  - Initialize useProjects() to pre-fetch projects list

## CONSTRAINTS
- Use lucide-react for all icons (already installed)
- Use shadcn/ui components: Button, Badge, Separator
- Tailwind classes only (no inline styles except for the accent color #00D4FF via style prop)
- All step imports via React.lazy to avoid loading all steps at once
- The "running" status badge should have a CSS pulse animation (animate-pulse)