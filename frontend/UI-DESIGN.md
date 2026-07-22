# Design System Inspired by Xanh SM

## 1. Visual Theme & Atmosphere

Xanh SM's design system embodies a fresh, modern marketplace aesthetic centered on sustainability and accessibility. The visual identity combines vibrant teal accents with a calming, neutral palette that evokes trust and professionalism. The design emphasizes clarity and simplicity through generous whitespace, soft transitions, and a friendly tone. Illustrated iconography and gradient backgrounds create an inviting, approachable feeling that appeals to both merchants and customers. The color hierarchy is deliberately restrained—dominant grays and teals work in harmony to guide attention without overwhelming, making the interface feel organized and navigable. This is a design language that prioritizes user confidence and ease of discovery.

**Key Characteristics**
- Bright teal primary accent paired with sophisticated neutral grays
- Clean, geometric layout with emphasis on breathing room
- Illustrations and icons as primary visual decoration
- Gradient backgrounds on hero sections for visual interest
- Accessible contrast ratios throughout
- Friendly, approachable tone balanced with professional credibility

## 2. Color Palette & Roles

### Primary
- **Primary Action** (`#28BDBF`): Call-to-action buttons, key interactive elements, primary brand touchpoints
- **Primary Dark** (`#00A398`): Secondary button states, active/focused states, deeper emphasis

### Accent Colors
- **Warning** (`#E3BB42`): Alert states, cautionary messaging, promotional badges
- **Gold Accent** (`#E3BB42`): Special offers and highlighted content

### Interactive
- **Button Text** (`#FFFFFF`): Text on primary action buttons for maximum contrast
- **Link Text** (`#374151`): Hyperlinks and navigational text, medium gray-blue
- **Ghost Button Text** (`#888888`): Tertiary interactive elements, subtle calls-to-action

### Neutral Scale
- **Text Primary** (`#353535`): Main body copy, highest contrast readable text
- **Text Secondary** (`#666666`): Secondary information, metadata, less critical copy
- **Text Tertiary** (`#888888`): Disabled states, hints, help text
- **Text Light** (`#FFFFFF`): Light mode text on dark backgrounds
- **Text Dark** (`#111827`): Headings, emphasized text, strong hierarchy

### Surface & Borders
- **Background** (`#FFFFFF`): Primary surface, card backgrounds, container fill
- **Divider** (`#E5E7EB`): Subtle borders, rule lines between sections
- **Border** (`#D5D8DC`): Input borders, card borders, structural divisions
- **Surface Light** (`#EEEEEE`): Subtle background tints, hover states

### Semantic / Status
- **Dark Overlay** (`#000000`): Modal overlays, darkening filters

## 3. Typography Rules

### Font Family
**Primary:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`

**Secondary:** `Roboto, 'Helvetica Neue', Arial, sans-serif`

Fallback stack ensures system fonts render crisply across platforms while maintaining brand voice.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|-----------------|-------|
| **Display / Hero** | Roboto | 60px | 500 | 60px | 0px | Large primary headings, marketing hero text |
| **Heading 1 (H1)** | -apple-system | 39px | 700 | 54.6px | 0px | Page titles, major section heads |
| **Heading 2 (H2)** | -apple-system | 18px | 700 | 24.3px | 0px | Section subheadings, card titles |
| **Heading 3 (H3)** | Roboto | 18px | 700 | 22px | 0px | Minor headings, navigation items |
| **Body** | -apple-system | 16px | 500 | 26px | 0px | Primary paragraph text, descriptions |
| **Body Small** | -apple-system | 14px | 600 | 21px | 0px | Secondary body copy, supporting text |
| **Button / Label** | Roboto | 14px | 500 | normal | 0px | Button text, form labels |
| **Button Secondary** | Roboto | 14px | 700 | 40px | 0px | Bold button text, strong calls-to-action |
| **Caption** | Roboto | 14px | 300 | normal | 0px | Form inputs, hints, small metadata |
| **Overline / Eyebrow** | -apple-system | 14px | 400 | 21px | 0px | Label headers, category tags |

### Principles
- Hierarchy is built through size and weight, not color—maintaining accessibility
- Line heights are generous (`1.5–1.65x font size`) to ensure readability in body text
- Roboto is reserved for interactive elements and data-heavy contexts; `-apple-system` handles narrative content
- Weights range from 300 (light inputs) to 700 (strong headings) for clear visual differentiation
- All font sizes use pixel units for pixel-perfect precision

## 4. Component Stylings

### Buttons

#### Primary Button
- **Background:** `#28BDBF`
- **Text Color:** `#FFFFFF`
- **Padding:** `0px 20px`
- **Height:** `40px`
- **Font Size:** `13px`
- **Font Weight:** `700`
- **Font Family:** `Roboto`
- **Line Height:** `40px`
- **Border:** `0px`
- **Border Radius:** `0px`
- **Box Shadow:** `none`
- **Hover:** Background `#00A398`, cursor pointer
- **Active:** Background `#00A398`, box-shadow `inset 0px 2px 4px rgba(0, 0, 0, 0.2)`
- **Disabled:** Background `#D5D8DC`, cursor not-allowed, opacity `0.6`

#### Secondary Button (Icon)
- **Background:** `rgba(0, 0, 0, 0)`
- **Text Color:** `#888888`
- **Padding:** `0px 10px`
- **Height:** `auto`
- **Font Size:** `14px`
- **Font Weight:** `500`
- **Font Family:** `Roboto`
- **Line Height:** `normal`
- **Border:** `0px`
- **Border Radius:** `0px`
- **Box Shadow:** `none`
- **Hover:** Text Color `#28BDBF`
- **Active:** Text Color `#00A398`

#### Ghost Button
- **Background:** `rgba(0, 0, 0, 0)`
- **Text Color:** `#4F5F69`
- **Padding:** `0px`
- **Height:** `auto`
- **Font Size:** `22px`
- **Font Weight:** `400`
- **Font Family:** `-apple-system`
- **Line Height:** `22px`
- **Border:** `0px`
- **Border Radius:** `0px`
- **Box Shadow:** `none`
- **Hover:** Opacity `0.8`

#### Text Link Button
- **Background:** `rgba(0, 0, 0, 0)`
- **Text Color:** `#374151`
- **Padding:** `0px 10px`
- **Height:** `auto`
- **Font Size:** `18px`
- **Font Weight:** `700`
- **Font Family:** `Roboto`
- **Line Height:** `normal`
- **Border:** `0px`
- **Border Radius:** `0px`
- **Box Shadow:** `none`
- **Hover:** Text Color `#28BDBF`, text-decoration underline

#### Large Button Block
- **Background:** `rgba(0, 0, 0, 0)`
- **Text Color:** `#353535`
- **Padding:** `16px 0px`
- **Width:** `100%` (full container)
- **Height:** `64px`
- **Font Size:** `14px`
- **Font Weight:** `400`
- **Font Family:** `-apple-system`
- **Line Height:** `21px`
- **Border:** `1px solid #E5E7EB`
- **Border Radius:** `0px`
- **Box Shadow:** `none`
- **Hover:** Background `#EEEEEE`

### Cards & Containers

#### Default Card
- **Background:** `#FFFFFF`
- **Border:** `1px solid #E5E7EB`
- **Border Radius:** `0px`
- **Padding:** `20px`
- **Box Shadow:** `rgba(0, 0, 0, 0.1) 0px 0px 2px 0px, rgba(0, 0, 0, 0.18) 0px 20px 40px 0px`
- **Hover:** Box Shadow `rgba(0, 0, 0, 0.1) 0px 10px 15px -3px, rgba(0, 0, 0, 0.1) 0px 4px 6px -4px`

#### Hero Card
- **Background:** Linear gradient from `#C3F0F1` to `#28BDBF`
- **Border:** `0px`
- **Border Radius:** `20px`
- **Padding:** `32px`
- **Box Shadow:** `none`
- **Text Color:** `#1F2937`

### Inputs & Forms

#### Text Input Standard
- **Background:** `#FFFFFF`
- **Border:** `1px solid #E0E0E0`
- **Border Radius:** `0px`
- **Padding:** `7px 30px 7px 14px`
- **Height:** `36px`
- **Font Size:** `14px`
- **Font Weight:** `300`
- **Font Family:** `Roboto`
- **Text Color:** `#353535`
- **Box Shadow:** `rgba(0, 0, 0, 0.08) 0px 0px 15px 0px inset`
- **Focus:** Border `1px solid #28BDBF`, box-shadow `rgba(40, 189, 191, 0.2) 0px 0px 8px 0px`
- **Placeholder Color:** `#888888`

#### Text Input Large
- **Background:** `#FFFFFF`
- **Border:** `1px solid #E0E0E0`
- **Border Radius:** `0px`
- **Padding:** `9px 40px 9px 15px`
- **Height:** `42px`
- **Width:** `100%`
- **Font Size:** `18px`
- **Font Weight:** `300`
- **Font Family:** `Roboto`
- **Text Color:** `#353535`
- **Box Shadow:** `rgba(0, 0, 0, 0.08) 0px 0px 15px 0px inset`
- **Focus:** Border `1px solid #28BDBF`

#### Search Input (Rounded)
- **Background:** `#FFFFFF`
- **Border:** `1px solid #E0E0E0`
- **Border Radius:** `33px`
- **Padding:** `7px 15px`
- **Height:** `40px`
- **Width:** `280px`
- **Font Size:** `14px`
- **Font Weight:** `300`
- **Font Family:** `Roboto`
- **Text Color:** `#353535`
- **Box Shadow:** `rgba(0, 0, 0, 0.05) 0px 2px 2px 0px inset`
- **Focus:** Background `#FFFFFF`, border `1px solid #28BDBF`, outline `none`

#### Form Label
- **Font Size:** `14px`
- **Font Weight:** `600`
- **Color:** `#4B5563`
- **Margin Bottom:** `8px`
- **Font Family:** `-apple-system`

### Navigation

#### Navigation Links
- **Font Size:** `18px`
- **Font Weight:** `500`
- **Font Family:** `Roboto`
- **Color:** `#374151`
- **Line Height:** `22px`
- **Padding:** `0px 16px`
- **Hover:** Color `#28BDBF`, text-decoration underline
- **Active:** Color `#00A398`, text-decoration underline

#### Navigation Item (Large Logo)
- **Font Size:** `60px`
- **Font Weight:** `500`
- **Font Family:** `Roboto`
- **Color:** `#212121`
- **Line Height:** `60px`
- **Height:** `28.9844px`
- **Hover:** Opacity `0.9`

### Badges

#### Standard Badge
- **Background:** `#E3BB42`
- **Text Color:** `#FFFFFF`
- **Padding:** `4px 12px`
- **Font Size:** `12px`
- **Font Weight:** `600`
- **Border Radius:** `100%`
- **Display:** `inline-block`

#### Badge Neutral
- **Background:** `#EEEEEE`
- **Text Color:** `#666666`
- **Padding:** `4px 12px`
- **Font Size:** `12px`
- **Font Weight:** `600`
- **Border Radius:** `100%`

## 5. Layout Principles

### Spacing System

Base unit: `8px`

- **Micro spacing:** `8px` — Padding within buttons, margin between inline elements
- **Compact spacing:** `12px` — Padding in form controls, tight grouped spacing
- **Standard spacing:** `16px` — Default padding in cards, normal element separation
- **Comfortable spacing:** `20px` — Padding inside containers, standard section margins
- **Breathing room:** `24px` — Spacing between major sections
- **Large gaps:** `28px, 32px` — Transitions between content blocks
- **Hero spacing:** `52px, 80px, 84px, 112px, 152px` — Large section separations, full-width hero margins

**Usage Context:**
- Buttons and form elements: `12px` internal padding
- Card padding: `16px–20px`
- Section margins: `24px–32px`
- Between sections: `52px–112px`
- Top/bottom hero: `80px–152px`

### Grid & Container

- **Max Width:** `1200px` for primary container
- **Column Strategy:** 12-column responsive grid
  - Desktop: 12 columns, `20px` gutter
  - Tablet: 8 columns, `16px` gutter
  - Mobile: 4 columns, `12px` gutter
- **Section Patterns:**
  - Hero section: Full width with gradient background, `80px–112px` top/bottom padding
  - Feature grid: 4-column layout on desktop (2-column tablet, 1-column mobile)
  - Content section: 2-column split or single column with max-width `832px`

### Whitespace Philosophy

Generous whitespace is foundational to Xanh SM's visual clarity. The design prioritizes breathing room over density—sections are well-separated, cards have ample internal padding, and text rarely touches container edges. This creates a calm, uncluttered experience that reduces cognitive load and invites the user to explore. Whitespace also functions as a design element, establishing visual rhythm and guiding eye movement through emphasis and grouping.

### Border Radius Scale

- **None:** `0px` — Structural elements, buttons, inputs (default)
- **Sharp:** `4px` — Micro interactions, small UI details
- **Rounded:** `20px` — Image containers, large cards
- **Pill:** `100%` — Badges, circular icons, fully rounded elements

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| **Flat (None)** | Box Shadow `none` | Default buttons, text links, structural elements |
| **Subtle (sm)** | `rgba(0, 0, 0, 0.1) 0px 0px 2px 0px, rgba(0, 0, 0, 0.18) 0px 20px 40px 0px` | Dropdown menus, tooltips, floating panels |
| **Medium (md)** | `rgba(0, 0, 0, 0.1) 0px 10px 15px -3px, rgba(0, 0, 0, 0.1) 0px 4px 6px -4px` | Cards on hover, lifted containers, modals |
| **Hover State** | `rgba(0, 0, 0, 0.1) 0px 10px 15px -3px, rgba(0, 0, 0, 0.1) 0px 4px 6px -4px` | Interactive cards, buttons elevated on hover |

**Shadow Philosophy:**
Xanh SM uses subtle, realistic shadows that mimic natural light falling from above-front. Shadows serve a functional purpose—they distinguish interactive surfaces and create depth hierarchy without overwhelming the interface. The system avoids heavy shadows; even the "medium" elevation is gentle, maintaining the design's clean, modern aesthetic. Shadows increase on hover and active states to provide tactile feedback. Dark overlays (`#000000` at 40–60% opacity) are reserved for modal backgrounds.

## 7. Do's and Don'ts

### Do
- Use `#28BDBF` (primary teal) for all primary calls-to-action and key interactive moments
- Maintain a minimum contrast ratio of 4.5:1 for all text on colored backgrounds
- Apply generous padding (`16px–20px`) inside cards and containers for visual comfort
- Use `-apple-system` for narrative, body-oriented content; `Roboto` for interactive and technical elements
- Stack spacing in multiples of `8px` for rhythm and consistency
- Implement hover states on all interactive elements with color shift or shadow lift
- Reserve the warning color `#E3BB42` exclusively for promotions, alerts, and special messaging
- Use full-width sections (`100%`) for hero and banner content
- Include accessible focus states with clear outline or border highlight (minimum `2px` width)
- Test all button and link text for sufficient contrast against backgrounds

### Don't
- Mix `-apple-system` and `Roboto` within the same sentence or paragraph
- Create text smaller than `12px` for body content (inaccessible)
- Use shadows heavier than the "medium" level; keep the design feeling light and open
- Apply more than two weight levels per heading (avoid cascading font-weight variations)
- Place neutral gray text (`#888888`) on light backgrounds without sufficient contrast—use `#666666` or darker
- Create buttons with padding less than `12px` internal or heights less than `36px` (too small for touch targets)
- Overload cards with more than two distinct shadow treatments
- Mix border radiuses within a single component family (keep inputs, buttons, and cards consistent)
- Use `#FFFFFF` text on `#FFFFFF` backgrounds (invisible)
- Add decorative shadows; all shadows must serve a functional, depth-signaling purpose

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|------|-------|-------------|
| **Mobile** | `< 640px` | Single column, 4-column grid, `12px` gutter, `16px` padding, hero `52px` top/bottom |
| **Tablet** | `640px–1024px` | 2–3 columns, 8-column grid, `16px` gutter, `16px–20px` padding, `20px` section margins |
| **Desktop** | `≥ 1024px` | 4-column layout, 12-column grid, `20px` gutter, `20px` padding, `32px–52px` section margins |
| **Large Desktop** | `≥ 1440px` | Max container width `1200px`, centered, sidebar layouts enabled |

### Touch Targets

Minimum sizes for all interactive elements (mobile-first):
- **Button Height:** `40px` (minimum), `44px` (recommended for thumb reach)
- **Button Padding:** `12px` horizontal (minimum `20px` ideal)
- **Link / Tap Target:** `44px × 44px` (WCAG 2.1 Level AAA)
- **Input Height:** `40px–42px` minimum
- **Spacing Between Targets:** `8px` minimum to prevent accidental double-tap
- **Icon Size:** `24px` (minimum), `32px` (recommended for touch)

### Collapsing Strategy

**Mobile (< 640px):**
- Stack all layouts vertically (no side-by-side)
- Full-width buttons and inputs (`100%`)
- Hero sections reduce top/bottom padding to `52px`
- Feature grids collapse to single column
- Navigation moves to hamburger menu or collapse
- Card padding reduces to `12px–16px`
- Font sizes reduce by `2px` (e.g., body `14px` instead of `16px`)

**Tablet (640px–1024px):**
- 2-column layouts enabled where appropriate
- Feature grids shift to 2-column
- Navigation can display inline if space permits
- Buttons and inputs remain flexible width
- Section margins reduce slightly (`20px–24px`)
- Hero section padding `28px–52px`

**Desktop (≥ 1024px):**
- Full 4-column feature grids
- Multi-column content layouts
- Sidebar navigation revealed
- Maximum content width constrained to `1200px` with centered container
- Section margins increase (`32px–112px`)

## 9. Agent Prompt Guide

### Quick Color Reference

- **Primary CTA:** Teal (`#28BDBF`) — Use on primary buttons, key interactive moments
- **Secondary CTA:** Dark Teal (`#00A398`) — Use on hover states, active buttons
- **Background:** White (`#FFFFFF`) — Card and surface fill
- **Heading Text:** Dark Gray (`#111827`) — Strong, primary text
- **Body Text:** Medium Gray (`#353535`) — Main paragraph copy
- **Secondary Text:** Gray (`#666666`) — Metadata, secondary information
- **Tertiary Text:** Light Gray (`#888888`) — Disabled states, hints
- **Borders:** Light Gray (`#E5E7EB`) — Subtle dividers, structural lines
- **Warning / Accent:** Gold (`#E3BB42`) — Alerts, promotions, special messaging
- **Overlay:** Black (`#000000`) at 40–60% opacity — Modals, overlays

### Iteration Guide

1. **Always use `#28BDBF` for primary actions**—it is the system's dominant interactive color and must be reserved exclusively for key CTAs
2. **Maintain the 8px spacing grid**—all margins and padding must be multiples of 8px (8px, 16px, 24px, 32px, etc.)
3. **Font hierarchy is built on size and weight, not color**—do not rely on color alone to differentiate text levels
4. **Apply shadows only on interaction**—buttons and cards start with no shadow; add shadows on hover, focus, or modal states
5. **Borders are always `#E5E7EB` or `#D5D8DC`**—never use black or other colors for structural dividers
6. **Input heights are minimum `36px`–`42px`**—form fields must meet touch target minimums
7. **Button padding is always `0px 20px` (horizontal) and `0px` (vertical, height provided instead)**—maintain this pattern across all button sizes
8. **Navigation links are `18px`, font-weight `500`, color `#374151`**—consistency is critical for navigation UX
9. **Hero sections use gradient backgrounds from light teal `#C3F0F1` to primary `#28BDBF`**—this is the signature visual treatment
10. **Card padding defaults to `16px–20px`, border-radius `0px`**—maintain flat, modern aesthetic with minimal rounding
11. **All interactive elements must have visible focus states**—minimum 2px border or outline in primary color (`#28BDBF`)
12. **Text contrast must meet WCAG AA (4.5:1 minimum)**—verify all text color + background combinations before finalizing