# Monthly Close Assistant — Front-End Design System Prompts

Run these after the core dashboard (step 13 in the main build sequence) already
works functionally. These prompts implement the "ledger" design system: a calm,
financial-instrument-panel look instead of default Django/Bootstrap styling.
Review each step visually before moving to the next.

---

## D1. Design Tokens & Base Styles

```
Create a single CSS file (static/css/tokens.css) defining this design system as
CSS custom properties:

Colors:
--color-ink: #1C2B3A        (primary text, headers)
--color-paper: #F7F5F0      (page background)
--color-slate: #5B6B7A      (secondary text, muted UI)
--color-flag: #C9762B       (open/unreviewed flags only)
--color-confirmed: #3A6B4C  (approved/reconciled states only)
--color-rejected: #8B3A3A   (rejected states, a muted brick red consistent
  with the rest of the palette)
--color-hairline: #DDD8CC   (border/divider color, warm light gray)

Typography:
--font-display: "Source Serif 4", Georgia, serif   (page title, month label only)
--font-body: "IBM Plex Sans", -apple-system, sans-serif  (everything else,
  including all table data, buttons, labels)
Import both via Google Fonts in base.html, with font-display: swap.

Set up a type scale using these custom properties: --text-xs, --text-sm,
--text-base, --text-lg, --text-xl, --text-2xl, with --text-2xl reserved for
the page title only.

Spacing: define --space-1 through --space-8 on a 4px base scale (4, 8, 12, 16,
24, 32, 48, 64px).

Apply --color-paper as the body background and --color-ink as the default text
color globally. No box-shadows, no border-radius above 4px anywhere in the base
styles, this is a flat, hairline-bordered aesthetic, not a card-based one.
```

---

## D2. Page Shell & Header

```
Rebuild the dashboard's base template header to match this layout: a single-row
header with "Close Assistant" as the page title using --font-display at
--text-2xl, --color-ink, with normal (not bold) weight, letter-spacing slightly
tightened. To the right of the title, a month selector dropdown using
--font-body, styled as plain text with a small down-caret, no default browser
select styling, no border unless focused. The header has a single
1px --color-hairline border at its bottom, no shadow.

Below the header, add a status ledger strip: a thin horizontal row showing
counts like "● 4 open   ● 2 approved   ● 1 rejected" where each dot is a small
8px circle colored with --color-flag, --color-confirmed, and --color-rejected
respectively, and the text uses --font-body at --text-sm in --color-slate.
This strip has its own bottom hairline border and generous vertical padding
(--space-4 top and bottom).
```

---

## D3. Flagged Items Table Redesign

```
Restyle the flagged items table to look like a ledger, not a generic data
table or card list. Requirements:
- No table borders on the outer edge, no zebra striping, no box-shadow
- Each row separated by a single 1px --color-hairline divider, full width
- Each row shows: vendor/description (--font-body, --color-ink, --text-base),
  the flag reason as a smaller secondary line beneath it in --color-slate
  --text-sm, the amount right-aligned in --font-body with tabular-nums enabled,
  and a small status indicator (colored dot + label, same color system as the
  ledger strip) instead of a badge or pill
- Approve and Reject buttons: plain text-style buttons (not filled/rounded
  buttons), --color-confirmed for Approve text and --color-rejected for Reject
  text, with an underline appearing only on hover, right-aligned next to the
  amount
- On approve/reject via htmx, swap in the updated row with the status dot and
  label changed accordingly, and fade the action buttons out since the
  decision is now made, replacing them with just the resolved status

Keep all of this in --font-body. Do not introduce drop shadows, rounded pill
badges, or card containers anywhere in this table.
```

---

## D4. Draft Summary Section

```
Restyle the close summary section below the flagged items table. Give it a
small eyebrow label "DRAFT SUMMARY" in --font-body, --text-xs, uppercase,
letter-spacing widened, --color-slate, sitting above the month label. Render
the summary text itself in --font-body --text-base, --color-ink, with
generous line-height (1.6) and a max content width (around 65-75 characters
per line) so it reads like a document, not a UI panel, no surrounding box,
border, or background fill, just generous whitespace around the text block.

Below the text, add a hairline divider and the "Mark Reviewed" action styled
the same plain-text-button way as Approve/Reject (--color-confirmed text,
underline on hover), next to a small textarea for reviewer notes that's
visually understated (hairline border only, no shadow, --font-body) until
focused.
```

---

## D5. Empty & Loading States

```
Add an empty state for when a selected month has no flagged items: instead of
an empty table, show a simple message in --font-body --color-slate, --text-base,
something like "No items flagged for [Month]. Everything reconciled cleanly."
Add a lightweight loading state for the htmx month-switch and approve/reject
actions: a subtle opacity transition (reduce the affected element's opacity to
0.5 during the htmx request, restore on completion) rather than a spinner, to
keep the calm, low-motion feel of the rest of the design.
```

---

## D6. Responsive & Accessibility Pass

```
Review the dashboard for mobile responsiveness: the flagged items table should
collapse to a stacked layout below 640px (vendor/description on top, amount
and actions below, status dot inline with the vendor name) rather than
horizontally scrolling. Ensure all interactive elements (month selector,
approve/reject buttons, mark reviewed) have a visible keyboard focus state
using a 2px outline in --color-ink offset slightly from the element. Confirm
color contrast between text colors and --color-paper meets WCAG AA at minimum,
adjust --color-slate or --color-flag slightly darker if needed to pass.
```

---

## D7. Self-Critique Pass

```
Take a screenshot of the current dashboard (or describe it in detail if
screenshots aren't available) and review it against this checklist: no drop
shadows anywhere, no rounded pill-shaped badges, no card-grid layout, serif
font used only for the page title and month label and nowhere else, amber
color appears only on open/unreviewed flags and nowhere else, green appears
only on approved/confirmed states and nowhere else. Fix any violations found.
```
