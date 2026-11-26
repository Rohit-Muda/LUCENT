# LUCENT Design System

**Source:** Google Stitch MCP Project `LUCENT Academic Productivity Platform` (`projects/13196195984541508041` / Remix `projects/8818115420034895508`)
**Extracted:** 2026-11-27

## Retrieved Stitch Screens & Scope Note

Five approved screens were retrieved via Stitch MCP:
1. `LUCENT Brand Identity Presentation` (`3d9f2286a10a4f9b88d43240f030e400`) — Vector SVG brand specification (Warm Paper & Deep Forest)
2. `LUCENT — Academic Dashboard (Desktop)` (`230f1e2d803a4419b480db8763f3318f`) — Light theme (`Warm Paper`)
3. `LUCENT — Academic Dashboard (Deep Forest Dark)` (`a0039b0fc4c24075bf7871662d4ac401`) — Dark theme (`Deep Forest`)
4. `LUCENT — Structured Study Notes (Desktop)` (`9721f8eed09046fdabf658ab80819585`) — Light theme (`Warm Paper`)
5. `LUCENT — Structured Study Notes (Deep Forest Dark)` (`f8b7fcb52c784100a8914e854693f65a`) — Dark theme (`Deep Forest`)

**MCP Limitation:** Separate Stitch screens were not present in the project for *Upload Lecture*, *Processing Status*, *Transcript Viewer*, *Telugu Explanations*, *Revision Points*, *MCQ Quiz*, *Lecture Library*, or *Lecture Details*. These eight screens extend the exact tokens, shell, cards, tables, buttons, and interaction states extracted from the five retrieved Stitch references while preserving all backend API contracts.

---

## A. Brand Identity

### Logo & Precision Geometric Glyph
Extracted directly from `LUCENT Brand Identity Presentation` (`viewBox="0 0 80 80"`):
- **Outer Diamond:** `<polygon points="40,10 70,40 40,70 10,40" fill="none" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round" />`
- **Inner Facet:** `<polygon points="40,22 58,40 40,58 22,40" fill="currentColor" />`
- **Vertical Axis Beams:**
  - Top: `<line x1="40" y1="12" x2="40" y2="22" stroke="currentColor" stroke-width="3" stroke-linecap="round" />`
  - Bottom: `<line x1="40" y1="58" x2="40" y2="68" stroke="currentColor" stroke-width="3" stroke-linecap="round" />`

### Wordmark & Tagline
- **Wordmark:** `LUCENT` (uppercase, Sora 700, `letter-spacing: 0.14em` in full lockup / `-0.02em` in compact sidebar header).
- **Subtitle / Tagline:** `Turn lectures into clarity` (or `Scholarly Sanctuary` in compact sidebar).
- **Dimensions & Aspect Ratio:**
  - Glyph aspect ratio: `1:1` (`80×80` viewBox).
  - Sidebar lockup icon: `36×36px` (`2.25rem`).
  - Favicon / small badge: `24×24px` (verified down to 24px in Stitch Brand Presentation).
  - Clear space: minimum `12px` (`0.75rem`) around the lockup; `12px` gap between glyph and wordmark.
- **Light & Dark Variants:**
  - **Light (Warm Paper):** Mineral Teal `#247C78` or Deep Forest `#111A1B` glyph with `#202A35` wordmark on `#F5F2EA` / `#FFFFFF`.
  - **Dark (Deep Forest):** Sea-Glass `#80C7B8` glyph with `#E9E6DA` wordmark on `#111A1B` / `#1C2928`.
- **Iconography Style:** Clean `1.75px`–`2px` stroke geometric inline SVG icons (`18px`–`20px` in nav/buttons, `16px` in badges/breadcrumbs) matching the restrained academic aesthetic.

---

## B. Typography System

Loaded from Google Fonts (`Sora`, `DM Sans`, `Newsreader`, `Noto Sans Telugu`), with zero Times New Roman, Georgia, or browser-default serif fallbacks.

| Role | Font Family | Weights | Sizes & Line Heights | Letter Spacing | Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display XL** | `Sora` | `700` | `clamp(28px, 3.2vw, 38px)` / `1.15` | `-0.02em` | Main page titles (Dashboard, Study Workspace, Lecture Title) |
| **Heading LG** | `Sora` | `600–700` | `24px–28px` / `1.25` | `-0.015em` | Major section headings (`1. Introduction...`) |
| **Heading MD** | `Sora` | `600` | `20px` / `1.35` | `-0.01em` | Card group titles (`Ingest Lecture`, `Recent Lecture Archives`) |
| **Heading SM** | `Sora` | `600` | `16px–17px` / `1.4` | `-0.005em` | Card titles, lecture row titles |
| **Interface Body** | `DM Sans` | `400–600` | `14px–15px` / `1.55` | `0` | Sidebar nav, buttons, forms, tables, metadata, general UI |
| **Label / Eyebrow** | `DM Sans` | `600` | `11px–12px` / `1.35` | `0.06em–0.1em` | Uppercase eyebrows, status pills, table headers, TOC label |
| **Editorial Reading** | `Newsreader` | `400–500` | `17px–18px` / `1.7` | `0` | Selectively for long-form study-note summaries, academic quotes, definitions |
| **Telugu Script** | `Noto Sans Telugu` | `400–500` | `15.5px–16px` / `1.85` | `0` | All Telugu-script content, Telugu explanations, bilingual excerpts (`unicode-bidi: plaintext`) |

---

## C. Colour System

### Light Theme — Warm Paper (`:root` / `[data-theme="light"]`)
- **Background (`--bg`):** `#F5F2EA`
- **Primary Surface (`--surface`):** `#FFFFFF`
- **Secondary Surface (`--surface-muted`):** `#EEEAE0`
- **Elevated / Subtle Surface (`--surface-elevated`):** `#FAF8F3`
- **Primary Text (`--text-strong`):** `#202A35`
- **Secondary Text (`--text-muted`):** `#707873`
- **Primary Accent (`--accent`):** `#247C78` (hover: `#1B625F`, subtle: `rgba(36, 124, 120, 0.10)`, on-accent: `#FFFFFF`)
- **Secondary Accent (`--accent-secondary`):** `#C77D5D` (subtle: `rgba(199, 125, 93, 0.12)`)
- **Borders (`--border` / `--border-strong`):** `#E3DED3` / `#CFC8B8`
- **Semantic Status Tokens:**
  - Success / Ready: text `#194B43`, surface `#EDF5F2`, border `#C5DFD6`
  - Warning / Active: text `#784A17`, surface `#FBF3E6`, border `#E8CFAF`
  - Error / Failed: text `#9E2A2B`, surface `#FDF0EF`, border `#F0C4C2`

### Dark Theme — Deep Forest (`[data-theme="dark"]`)
- **Background (`--bg`):** `#111A1B`
- **Primary Surface (`--surface`):** `#1C2928`
- **Secondary Surface (`--surface-muted`):** `#243330`
- **Elevated / Subtle Surface (`--surface-elevated`):** `#162221`
- **Primary Text (`--text-strong`):** `#E9E6DA`
- **Secondary Text (`--text-muted`):** `#A5B2AA`
- **Primary Accent (`--accent`):** `#80C7B8` (hover: `#97D5C8`, subtle: `rgba(128, 199, 184, 0.14)`, on-accent: `#0F1B1A`)
- **Secondary Accent (`--accent-secondary`):** `#D6A36A` (subtle: `rgba(214, 163, 106, 0.14)`)
- **Borders (`--border` / `--border-strong`):** `#30403C` / `#415550`
- **Semantic Status Tokens:**
  - Success / Ready: text `#80C7B8`, surface `#18312D`, border `#2A4E47`
  - Warning / Active: text `#D6A36A`, surface `#312617`, border `#543F22`
  - Error / Failed: text `#F29B9B`, surface `#351B1C`, border `#5C2D2F`

---

## D. Layout and Components

- **Sidebar:** Fixed left rail on desktop (`264px` / `16.5rem` wide; collapses to a slide-over drawer + mobile menu trigger below `960px`). Houses LUCENT brand lockup, tagline card (*"Turn lectures into clarity"*), primary navigation links (`Dashboard`, `Upload lecture`, `Lecture history`), and bilingual `EN + TE` archive indicator at bottom.
- **Top Header:** Sticky `64px` (`4rem`) bar with translucent backdrop (`backdrop-filter: blur(12px)`), breadcrumb / context indicator on the left, and theme toggle pill (`Warm Paper` / `Deep Forest`) + optional `Sign out` action on the right.
- **Main Content Area:** Max width `1160px`, centered with `32px` desktop padding (`20px` tablet, `16px` mobile).
- **Study Notes Reading Layout:** Two-column layout with a `220px` sticky Table of Contents + Key Telugu Gloss card on the left and a `max-width: 720px` editorial reading canvas on the right (`40px` padding on desktop).
- **Grid & Spacing Scale:** `4px` base unit (`4, 8, 12, 16, 20, 24, 32, 48px`). Dashboard uses a 12-column grid (`5 cols` quick-upload / pipeline summary + `7 cols` recent/featured study workspace).
- **Border Radius & Borders:** `8px` inputs/buttons/nav items, `12px` cards/tables/sub-blocks, `16px` hero/featured panels, `9999px` status pills & theme pill. `1px` solid borders (`--border`).
- **Shadows:** Restrained ambient shadow (`0 2px 10px rgba(32, 42, 53, 0.04)` light; `0 4px 16px rgba(0, 0, 0, 0.24)` dark).
- **Buttons:** Primary (`--accent` fill, `--on-accent` text, `40px` height), Secondary (`--surface` fill, `--border-strong` border, `40px` height), Small (`32px` height).
- **Inputs:** `40px`–`42px` height, `8px` radius, `1px solid var(--border)` with `--accent` focus ring.
- **Tables & Lists:** Clean horizontal rows with subtle `--surface-muted` hover state and uppercase `11px` DM Sans column headers.
- **Responsive Breakpoints:** Desktop (`> 960px` persistent sidebar), Tablet (`<= 960px` collapsible sidebar drawer), Mobile (`<= 640px` stacked actions & single-column grids).

---

## E. Interaction States

- **Default:** Clean surface contrast with `1px` border (`--border`).
- **Hover:** Smooth `150ms` transition to `--surface-muted` or `--accent-hover`, border shifts to `--border-strong` or `--accent`.
- **Active:** Sidebar active link uses `--accent` fill with high-contrast `--on-accent` text; lecture sub-tabs use a `2px` bottom `--accent` indicator.
- **Focus:** Accessible `2px`–`3px` `--accent` focus-visible outline with `2px` offset.
- **Disabled:** `0.55` opacity, `cursor: not-allowed`, no hover transform.
- **Loading:** Animated circular spinner (`--accent` top border) + contextual status message.
- **Success / Warning / Error / Empty / Selected:** Mapped directly to semantic surface + border + text tokens above; quiz options highlight selected (`--accent-subtle`), correct (`--success-surface`), and wrong (`--danger-surface`) states cleanly without leaking pre-submission answers.
