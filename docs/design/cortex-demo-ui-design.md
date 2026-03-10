# Cortex Demo UI — Design Specification

**Author:** Saheb | **Date:** March 10, 2026 | **Status:** Ready for Development
**Audience:** Ayush (developer) + Kalyan demo (Thursday)
**Purpose:** React web application demonstrating the Cortex AI pipeline with dual view modes — Analyst View for end users, Engineering View for pipeline explainability.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Information Architecture](#2-information-architecture)
3. [Design Tokens](#3-design-tokens)
4. [Global Layout](#4-global-layout)
5. [Component: Top Navigation Bar](#5-component-top-navigation-bar)
6. [Component: Sidebar — Chat History](#6-component-sidebar--chat-history)
7. [Component: Main Chat Panel — Analyst View](#7-component-main-chat-panel--analyst-view)
8. [Component: Pipeline Explainability Panel — Engineering View](#8-component-pipeline-explainability-panel--engineering-view)
9. [Pipeline Step Specifications](#9-pipeline-step-specifications)
10. [Results Presentation](#10-results-presentation)
11. [Starter Query Cards](#11-starter-query-cards)
12. [Interaction Design & Animations](#12-interaction-design--animations)
13. [Error States & Edge Cases](#13-error-states--edge-cases)
14. [Dark Mode](#14-dark-mode)
15. [Responsive Behavior](#15-responsive-behavior)
16. [Full User Journey](#16-full-user-journey)
17. [Accessibility](#17-accessibility)
18. [Developer Implementation Notes](#18-developer-implementation-notes)
19. [Metric Playground](#19-metric-playground)

---

## 1. Design Principles

These principles govern every decision in this document. When in doubt, the principle wins.

**Trust first.** Every visual element earns trust or wastes space. Show the SQL. Show the data source. Show the confidence score. Analysts who can verify the answer will use the tool daily. Analysts who cannot verify it will stop trusting it.

**Answer, then explain.** The result appears first. The pipeline steps, SQL, and metadata appear below or in a secondary panel. Executives should be able to read the answer without ever seeing a pipeline step. Engineers should be able to expand the full trace.

**The pipeline visualization is for the demo, not the analyst.** The Engineering View is a transparency and credibility tool. In production, most Finance analysts will live in Analyst View. Design both, but the Analyst View is the real product.

**Motion is data.** The sequential step animation communicates that the system is doing careful work, not just hallucinating. Each step completing before the next starts is meaningful — it maps to the actual pipeline sequence. Do not animate for decoration.

**Enterprise restraint.** Glass morphism is acceptable as a subtle surface treatment on cards and panels, not as the primary design language. No gradients on text. No parallax. No hero animations. This is American Express, not a startup.

---

## 2. Information Architecture

### Page Structure

The application is a single-page application (SPA) with three visual regions that are always present:

```
┌────────────────────────────────────────────────────────────────────┐
│  TOP NAV BAR (64px fixed)                                          │
│  Logo | "Cortex" wordmark | View Toggle | User badge | Settings    │
├──────────────┬─────────────────────────────────────────────────────┤
│              │                                                      │
│   SIDEBAR    │   MAIN CONTENT AREA                                 │
│   (280px     │                                                      │
│   collapsible│   [Analyst View]  OR  [Split: Analyst + Engineering] │
│   )          │                                                      │
│              │                                                      │
│   Chat       │                                                      │
│   History    │                                                      │
│              │                                                      │
│   Session    │                                                      │
│   List       │                                                      │
│              │                                                      │
└──────────────┴─────────────────────────────────────────────────────┘
```

### View Modes

**Analyst View (default)**
- Full width main content
- Clean chat interface
- Results in-line
- Pipeline steps hidden
- No SQL visible unless user expands

**Engineering View**
- Main content splits into two panels
- Left panel (55% width): Analyst chat interface (same as Analyst View)
- Right panel (45% width): Pipeline explainability panel, fixed position, scrollable
- The two panels are visually separated by a 1px divider with a drag handle to resize

### Component Hierarchy

```
App
├── TopNavBar
│   ├── LogoMark
│   ├── ProductWordmark
│   ├── ViewModeToggle
│   ├── UserBadge
│   └── SettingsButton
├── Sidebar
│   ├── NewChatButton
│   ├── SessionList
│   │   └── SessionItem (repeating)
│   └── SidebarCollapseButton
├── MainContentArea
│   ├── ChatPanel (always present)
│   │   ├── WelcomeState (when no messages)
│   │   │   ├── GreetingText
│   │   │   └── StarterQueryCards (5 cards)
│   │   ├── MessageThread (when messages exist)
│   │   │   ├── UserMessage (repeating)
│   │   │   └── AssistantResponse (repeating)
│   │   │       ├── SummaryAnswer
│   │   │       ├── ResultTable (or ResultChart)
│   │   │       ├── MetadataFooter (expandable)
│   │   │       └── FollowUpSuggestions
│   │   ├── TypingIndicator (during processing)
│   │   └── ChatInputArea
│   │       ├── TextInput
│   │       └── SendButton
│   └── EngineeringPanel (only in Engineering View)
│       ├── PanelHeader
│       ├── PipelineStepList
│       │   └── PipelineStep (7 steps, sequential)
│       │       ├── StepHeader
│       │       ├── StepContent (expandable)
│       │       └── StepTimingBadge
│       └── PanelFooter (confidence score, total latency)
└── DisambiguationModal (overlay, shown when needed)
```

---

## 3. Design Tokens

All values referenced throughout this document. Ayush should create a `tokens.ts` or CSS custom properties file from this table.

### Colors

```
// Brand
--color-amex-blue:           #006FCF
--color-amex-dark-blue:      #00175A
--color-amex-white:          #FFFFFF

// Surface
--color-surface-primary:     #FFFFFF
--color-surface-secondary:   #F7F8F9
--color-surface-tertiary:    #F0F2F5
--color-surface-inverse:     #00175A

// Text
--color-text-primary:        #0D1117     // Near-black, not pure black
--color-text-secondary:      #6B7280     // Muted gray
--color-text-tertiary:       #9CA3AF     // Placeholder, disabled
--color-text-inverse:        #FFFFFF
--color-text-link:           #006FCF

// Semantic
--color-success:             #008767
--color-success-light:       #E6F4F1
--color-warning:             #B37700
--color-warning-light:       #FFF8E6
--color-error:               #C40000
--color-error-light:         #FDE8E8
--color-info:                #006FCF
--color-info-light:          #E6F0FA

// Pipeline steps (Engineering View)
--color-step-pending:        #9CA3AF     // Gray, not yet started
--color-step-active:         #006FCF     // Blue, in progress
--color-step-complete:       #008767     // Green, done
--color-step-warning:        #B37700     // Amber, near-miss / low confidence
--color-step-error:          #C40000     // Red, failed

// Borders
--color-border-default:      #E5E7EB
--color-border-strong:       #D1D5DB
--color-border-focus:        #006FCF

// Dark mode
--color-dark-surface:        #00175A
--color-dark-surface-raised: #0A2472     // Slightly lighter than surface
--color-dark-border:         #1E3A7A
--color-dark-text-primary:   #F9FAFB
--color-dark-text-secondary: #9CA3AF
```

### Typography

```
// Font stack
--font-primary: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif
--font-mono:    'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace

// Scale
--text-xs:   11px / line-height 16px
--text-sm:   13px / line-height 20px
--text-base: 15px / line-height 24px
--text-md:   16px / line-height 26px
--text-lg:   18px / line-height 28px
--text-xl:   22px / line-height 32px
--text-2xl:  28px / line-height 36px
--text-3xl:  36px / line-height 44px

// Weights
--font-regular:   400
--font-medium:    500
--font-semibold:  600
--font-bold:      700
```

### Spacing

```
// Base unit: 4px
--space-1:  4px
--space-2:  8px
--space-3:  12px
--space-4:  16px
--space-5:  20px
--space-6:  24px
--space-8:  32px
--space-10: 40px
--space-12: 48px
--space-16: 64px
```

### Border Radius

```
--radius-sm:   4px    // Tags, badges, small elements
--radius-md:   8px    // Cards, inputs, buttons
--radius-lg:   12px   // Panels, modals, large cards
--radius-xl:   16px   // Message bubbles
--radius-full: 9999px // Pills, toggle switches
```

### Elevation (Box Shadows)

```
--shadow-sm:  0 1px 2px 0 rgba(0,0,0,0.05)
--shadow-md:  0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05)
--shadow-lg:  0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.05)
--shadow-xl:  0 20px 25px -5px rgba(0,0,0,0.10), 0 8px 10px -6px rgba(0,0,0,0.05)

// Glass morphism surface (used sparingly)
--shadow-glass: 0 4px 24px rgba(0,23,90,0.08), inset 0 1px 0 rgba(255,255,255,0.6)
```

### Transitions

```
--transition-fast:    100ms ease-out
--transition-default: 200ms ease-out
--transition-slow:    350ms ease-out
--transition-spring:  400ms cubic-bezier(0.34, 1.56, 0.64, 1)  // Springy, for icons
```

---

## 4. Global Layout

### Root Layout

The application root renders at 100vw / 100vh with no scrolling at the page level. All scrolling happens inside individual panels.

```
Position: fixed, full viewport
Display: flex, column
Background: --color-surface-secondary (#F7F8F9)
```

**TopNavBar:** 64px height, fixed at top.

**Body row:** flex row, fills remaining height (calc(100vh - 64px)).

Within the body row:

- **Sidebar:** 280px width, collapsible to 0px (with transition). Fixed height, internal scroll.
- **MainContentArea:** flex: 1, fills remaining width. Contains ChatPanel and optionally EngineeringPanel in a flex row.

### Main Content Area — Analyst View

```
Width: 100% of remaining space (after sidebar)
Display: flex, column
Align items: center
Background: --color-surface-secondary
```

The ChatPanel inside this area centers at a maximum width of 800px, with 24px horizontal padding on each side.

### Main Content Area — Engineering View

```
Width: 100% of remaining space
Display: flex, row
No centering constraint
```

- Left: ChatPanel container — 55% width, min-width 480px, padded, internally scrolling.
- Divider: 1px vertical line in --color-border-default, with a 4px wide drag-handle zone.
- Right: EngineeringPanel — remaining width (roughly 45%), fixed, independently scrolling.

The chat content inside the left panel still centers at max-width 680px within its column. The Engineering View constrains available space, so this max-width is narrower than Analyst View.

---

## 5. Component: Top Navigation Bar

### Layout

```
Height:     64px
Width:      100%
Position:   fixed, z-index 100
Background: #00175A (Amex Dark Blue) — always, both light and dark mode
Border:     none (shadow instead)
Shadow:     0 1px 0 rgba(255,255,255,0.06), 0 2px 8px rgba(0,0,0,0.20)
Padding:    0 24px
Display:    flex, row, align-items center, justify-content space-between
```

### Left Section

**Logo area:** 40px x 40px square. Render the Amex blue card logo mark — a simplified rectangular card icon with rounded corners in white (#FFFFFF). If unavailable, render initials "AX" in bold white text, 16px, on a #006FCF background rectangle with 4px radius. Do not use a raster image — use SVG or CSS.

**Separator:** 1px vertical line, 24px tall, rgba(255,255,255,0.20), 16px margin on each side.

**Product wordmark:** Text "Cortex" in --text-lg (18px), --font-semibold, color #FFFFFF. Below it, in a second line: "Finance Intelligence" in --text-xs (11px), --font-regular, color rgba(255,255,255,0.55). These two lines are stacked vertically in a flex column.

### Center Section

**View Mode Toggle** — this is the primary control for switching between Analyst and Engineering views.

Visual treatment: A segmented control (not a dropdown). Two segments side by side with a shared pill background.

```
Container:
  Background:   rgba(255,255,255,0.10)
  Border:       1px solid rgba(255,255,255,0.15)
  Border radius: --radius-full (9999px)
  Height:       36px
  Padding:      3px
  Display:      flex, row

Segment (inactive):
  Height:       30px
  Padding:      0 16px
  Border radius: --radius-full
  Font:         --text-sm (13px), --font-medium
  Color:        rgba(255,255,255,0.60)
  Background:   transparent
  Cursor:       pointer
  Transition:   --transition-default

Segment (active):
  Background:   #FFFFFF
  Color:        #00175A
  Font:         --text-sm (13px), --font-semibold
  Shadow:       0 1px 3px rgba(0,0,0,0.20)
```

Left segment label: "Analyst View". Right segment label: "Engineering View". Switching animates the white background pill sliding from one segment to the other using transform, not opacity.

**Icon treatment:** Each segment has a small icon to the left of the label.
- Analyst View: a simple person silhouette icon, 14px
- Engineering View: a branching flowchart / nodes icon, 14px

### Right Section

**User badge:**
```
Display:      flex, row, align-items center, gap 10px
```

A colored circle avatar (32px diameter), background color derived from user name hash — but for the demo, hard-code to #006FCF. Inside the circle: first initial of the user in white, --text-sm, --font-bold.

To the right of the avatar:
- Top line: User name — "Finance Analyst" in --text-sm (13px), --font-medium, color #FFFFFF.
- Bottom line: BU badge — a small pill with background rgba(0,111,207,0.60), text "Finance BU" in --text-xs (11px), --font-medium, color #FFFFFF.

**Settings button:** A gear icon (16px) in rgba(255,255,255,0.55), right of the user section, with 12px left margin. No label. On hover: rgba(255,255,255,0.90), transition --transition-fast.

---

## 6. Component: Sidebar — Chat History

### Container

```
Width:          280px
Height:         100% (fills body row)
Background:     #FFFFFF
Border-right:   1px solid --color-border-default
Display:        flex, column
Overflow:       hidden
Transition:     width 250ms ease-out (for collapse)
Flex-shrink:    0
```

When collapsed: width transitions to 0, overflow hidden, content is invisible but not destroyed.

### New Chat Button

```
Margin:         16px
Height:         44px
Background:     #006FCF
Color:          #FFFFFF
Font:           --text-sm (13px), --font-semibold
Border-radius:  --radius-md (8px)
Display:        flex, align-items center, justify-content center, gap 8px
Cursor:         pointer
Shadow:         --shadow-sm

Hover state:
  Background:   #0057A3 (darkened Amex blue)
  Shadow:       --shadow-md
  Transition:   --transition-fast

Icon:           Plus sign (+), 16px, white
Label:          "New Conversation"
```

### Session List

```
Padding:        0 8px
Overflow-y:     auto
Flex:           1 (fills remaining sidebar height)

Scrollbar:
  Width:        4px
  Track:        transparent
  Thumb:        #D1D5DB, radius 4px
  Thumb hover:  #9CA3AF
```

**Section Header** (appears above grouped sessions):
```
Padding:   8px 8px 4px 8px
Font:      --text-xs (11px), --font-semibold
Color:     --color-text-tertiary (#9CA3AF)
Uppercase: yes, letter-spacing 0.6px
```
Label examples: "TODAY", "YESTERDAY", "LAST 7 DAYS"

**Session Item:**
```
Height:         min 44px, auto with overflow
Padding:        10px 12px
Border-radius:  --radius-md (8px)
Display:        flex, column, gap 2px
Cursor:         pointer
Margin-bottom:  2px

Default state:
  Background:   transparent

Hover state:
  Background:   --color-surface-secondary (#F7F8F9)
  Transition:   --transition-fast

Active state (current session):
  Background:   --color-info-light (#E6F0FA)
  Border-left:  2px solid #006FCF
  Padding-left: 10px (adjusted for border)
```

Inside each session item:
- Session title (truncated with ellipsis at 1 line): --text-sm (13px), --font-medium, --color-text-primary. Title is the first user message, truncated to ~35 characters.
- Timestamp: --text-xs (11px), --color-text-tertiary, right-aligned on same line.
- Preview (optional, 1 line): --text-xs (11px), --color-text-secondary, truncated.

### Sidebar Collapse Button

```
Position:       absolute, right: -12px, top: 50% (vertically centered)
Width:          24px
Height:         24px
Background:     #FFFFFF
Border:         1px solid --color-border-default
Border-radius:  --radius-full
Display:        flex, align-items center, justify-content center
Shadow:         --shadow-sm
Cursor:         pointer
Z-index:        10
```

Icon: A chevron pointing left (when expanded) or right (when collapsed). 12px, --color-text-secondary.

Hover: Background --color-surface-secondary, chevron color --color-text-primary.

---

## 7. Component: Main Chat Panel — Analyst View

### Container

```
Width:          100%
Max-width:      800px (Analyst View) / 680px (Engineering View)
Margin:         0 auto
Height:         100%
Display:        flex, column
Padding:        0 24px
```

### Welcome State (no messages)

Shown when a session has no messages yet. Replaced by MessageThread once the user sends their first query.

**Greeting section:**
```
Margin-top:   64px (from top of content area)
Text align:   center
```

Main greeting: "Good morning, what would you like to know?" (time of day changes dynamically). Font: --text-2xl (28px), --font-semibold, --color-text-primary. Line-height: 36px.

Sub-line below it (8px margin): "Ask anything about your Finance data. I'll find the answer." Font: --text-md (16px), --font-regular, --color-text-secondary.

**Starter Query Cards** — see Section 11 for full specification. They appear in a 2-column grid (5 cards: 2 + 2 + 1 centered) below the greeting, with 32px margin-top.

### Message Thread

The scrollable region containing all messages for the current session.

```
Overflow-y:   auto
Flex:         1
Padding:      24px 0
Display:      flex, column, gap 24px

Scrollbar:
  Width:      4px
  Track:      transparent
  Thumb:      #D1D5DB, radius 4px
```

Messages are rendered newest at the bottom. The thread auto-scrolls to the bottom when a new message arrives. The scroll is smooth, not instant.

#### User Message Bubble

```
Alignment:    flex-end (right side)
Max-width:    70% of chat panel width
```

The bubble:
```
Background:   #006FCF
Color:        #FFFFFF
Padding:      12px 16px
Border-radius: 16px 16px 4px 16px (top-left, top-right, bottom-right, bottom-left)
Font:         --text-base (15px), --font-regular
Line-height:  24px
Shadow:       0 1px 2px rgba(0,111,207,0.30)
```

Below the bubble (right-aligned): timestamp in --text-xs (11px), rgba(0,0,0,0.40). Example: "2:34 PM".

#### Assistant Response Container

Not a bubble — it uses the full available width, left-aligned with an icon.

**Left icon:** The Cortex "C" icon — a stylized C mark in white on a 32px circular background of #006FCF, or an abstract nodes/graph icon. This icon sits at the top-left of the response, vertically aligned with the first line of text. It is always 32px x 32px.

**Response body:** starts 12px to the right of the icon. Width: remaining space in chat panel.

**Response anatomy (top to bottom):**

1. **Summary answer** — The direct, plain-English answer to the question. This is the first thing the eye lands on.
   ```
   Font:       --text-md (16px), --font-medium, --color-text-primary
   Margin-bottom: 16px
   ```
   Example: "There are 2.4 million active cardmembers as of the last 90 days."

2. **Result table or chart** — see Section 10 for full specification.

3. **Metadata footer** — expandable, collapsed by default.
   ```
   Margin-top:   12px
   Border-top:   1px solid --color-border-default
   Padding-top:  10px
   ```
   Collapsed state shows: a row of small metadata tags and an expand button.

   Metadata tags (inline, horizontal, gap 8px):
   - Explore badge: small pill, background --color-surface-tertiary (#F0F2F5), border 1px solid --color-border-default, font --text-xs (11px), --font-medium, --color-text-secondary. Shows: "explore: finance_cardmember_360"
   - Confidence badge: same pill style, with a colored dot (green/amber/red) before the text. Shows: "94% confidence"
   - Freshness badge: shows "Updated: 6 hours ago"

   Expand button: text button, --text-xs (11px), --color-text-link, label "View SQL & details". On click, expands to show the full SQL block and additional metadata.

   Expanded state (additional content):
   - SQL block: code block with syntax highlighting, background #F7F8F9, border 1px solid --color-border-default, border-radius --radius-md, padding 16px, font --font-mono, --text-sm (13px), --color-text-primary. Line numbers on the left in --color-text-tertiary.
   - "Copy SQL" button: ghost button, top-right corner of the code block, 28px height, --text-xs (11px).
   - Additional metadata row: model name, partition filter applied (shown as a badge), bytes estimated, query execution time.

4. **Follow-up suggestions** — 2 to 3 short question chips that the user can click to continue.
   ```
   Margin-top:   16px
   Display:      flex, row, flex-wrap wrap, gap 8px
   ```
   Each chip:
   ```
   Height:         32px
   Padding:        0 12px
   Background:     --color-surface-primary (#FFFFFF)
   Border:         1px solid --color-border-default
   Border-radius:  --radius-full
   Font:           --text-sm (13px), --font-regular, --color-text-primary
   Cursor:         pointer
   Transition:     --transition-fast

   Hover:
     Border-color:   #006FCF
     Color:          #006FCF
     Background:     #E6F0FA
   ```
   Example chips: "Break down by card product" / "Compare to last quarter" / "Show top 5 only"

### Typing Indicator

Shown while the pipeline is processing. Replaces the response area until the answer is ready. In Analyst View, this is a simple animated indicator. In Engineering View, the pipeline steps panel lights up instead — but the chat still shows the indicator.

```
Display:    flex, row, align-items center, gap 10px
Margin-top: 8px
```

Left: The Cortex icon (32px, same as response icon).

Right: Text "Cortex is thinking..." in --text-sm (13px), --color-text-secondary, followed by three animated dots. The dots pulse with a stagger animation: each dot fades in/out on a 400ms loop, staggered by 150ms. Dots are 4px diameter circles, color #006FCF.

### Chat Input Area

```
Position:     sticky, bottom 0
Background:   linear-gradient(to top, --color-surface-secondary 85%, transparent)
Padding:      16px 0 24px
```

The input field:

```
Width:        100%
Min-height:   52px
Max-height:   200px (auto-expands as user types multi-line)
Background:   #FFFFFF
Border:       1.5px solid --color-border-strong
Border-radius: --radius-lg (12px)
Padding:      14px 52px 14px 16px   (right padding leaves room for send button)
Font:         --text-base (15px), --font-regular, --color-text-primary
Placeholder:  "Ask anything about your Finance data..." in --color-text-tertiary
Shadow:       --shadow-md
Resize:       none
Overflow-y:   auto
Transition:   border-color --transition-fast

Focus state:
  Border-color:  #006FCF
  Shadow:        0 0 0 3px rgba(0,111,207,0.12), --shadow-md
  Outline:       none
```

Send button (positioned inside the input field, bottom-right corner):

```
Position:     absolute, right 12px, bottom 12px
Width:        32px
Height:       32px
Background:   #006FCF (enabled) / #D1D5DB (disabled)
Border-radius: --radius-md (8px)
Display:      flex, align-items center, justify-content center
Cursor:       pointer (enabled) / not-allowed (disabled)
Transition:   background --transition-fast, transform --transition-spring

Icon:         Arrow-up icon, 14px, white
Active state: transform scale(0.92)
```

The send button is disabled when the input is empty or while a query is processing.

Below the input field (center-aligned, 8px margin-top):
```
Font:   --text-xs (11px)
Color:  --color-text-tertiary
Text:   "Cortex may make mistakes. Always verify critical decisions."
```

---

## 8. Component: Pipeline Explainability Panel — Engineering View

This panel is only visible in Engineering View. It sits to the right of the chat panel and shows the real-time pipeline execution trace.

### Container

```
Width:          45% of main content (flexible with drag handle)
Min-width:      400px
Height:         100%
Background:     #FFFFFF
Border-left:    1px solid --color-border-default
Display:        flex, column
Overflow:       hidden
```

### Panel Header

```
Height:         52px
Border-bottom:  1px solid --color-border-default
Padding:        0 20px
Display:        flex, row, align-items center, justify-content space-between
Background:     --color-surface-secondary (#F7F8F9)
Flex-shrink:    0
```

Left side:

- Icon: a small branching-nodes icon (16px, --color-text-secondary) to the left
- Label: "Pipeline Trace" in --text-sm (13px), --font-semibold, --color-text-primary
- Session indicator: a small pill showing current query state. States:
  - "Idle" — gray pill, text --color-text-tertiary
  - "Processing" — blue pill with animated pulse dot, text #006FCF
  - "Complete" — green pill, text #008767
  - "Error" — red pill, text #C40000

Right side:

- Total latency (shown when complete): --text-xs (11px), --color-text-secondary, "Total: 2.4s"
- Clear button: text button, "Clear", --text-xs (11px), --color-text-link

### Pipeline Step List

```
Overflow-y:   auto
Flex:         1
Padding:      16px
Display:      flex, column, gap 0
```

Each step connects to the next via a vertical connector line (see Section 9 for step specifications).

### Panel Footer

```
Height:       56px
Border-top:   1px solid --color-border-default
Padding:      0 20px
Display:      flex, row, align-items center, justify-content space-between
Background:   --color-surface-secondary
Flex-shrink:  0
```

Left: Overall confidence score display.
```
Label:    "Overall Confidence" in --text-xs (11px), --color-text-tertiary, uppercase, letter-spacing 0.5px
Value:    Large percentage like "94%" in --text-xl (22px), --font-bold
Color of value: #008767 (green, >=80%), #B37700 (amber, 60-79%), #C40000 (red, <60%)
```

Right: A small breakdown of the confidence components:
```
Font:       --text-xs (11px), --color-text-secondary
Lines:
  Vector:   "sem: 0.91"
  Graph:    "graph: 0.97"
  Few-shot: "fewshot: 0.89"
```

---

## 9. Pipeline Step Specifications

Each of the 7 pipeline steps follows this structure, with step-specific content inside.

### Step Container Structure

```
Position:   relative
Display:    flex, row
Gap:        12px
Padding-bottom: 0 (connector adds visual spacing)
```

**Left column (20px wide):** Contains the step indicator circle and the vertical connector line below it.

**Step indicator circle:**
```
Width:          20px
Height:         20px
Border-radius:  --radius-full
Flex-shrink:    0
Margin-top:     2px   (aligns with first line of text)
```

State-based colors:
- Pending: background --color-surface-tertiary, border 1.5px solid --color-border-strong, no icon
- Active: background #006FCF, border none, animated spinner (see animation spec)
- Complete: background #008767, border none, white checkmark icon (10px)
- Warning: background #B37700, border none, white exclamation icon (10px)
- Error: background #C40000, border none, white X icon (10px)

**Vertical connector line** (between this step and the next):
```
Width:          1.5px
Flex-shrink:    0
Position:       absolute, left 9px (center of 20px column), top 22px, bottom 0
Background:     --color-border-default (pending)
               #008767 (if the step below is complete)
               dashed #006FCF (if the step below is active)
Transition:     background 300ms ease
```

The last step (Step 7) has no connector line below it.

**Right column (flex: 1):** Contains the step header and expandable content.

**Step header:**
```
Display:        flex, row, align-items flex-start, justify-content space-between
Padding-bottom: 12px
Cursor:         pointer (for steps that are complete or warning)
```

Left of header:
- Step label: --text-sm (13px), --font-semibold, --color-text-primary (complete/active) / --color-text-tertiary (pending)
- Step sub-label (below, 4px gap): --text-xs (11px), --color-text-secondary. Short description of what this step does.

Right of header:
- Timing badge (shown when step is complete or active):
  ```
  Height:         18px
  Padding:        0 6px
  Border-radius:  --radius-sm
  Font:           --text-xs (11px), --font-medium
  Background:     --color-success-light / --color-warning-light (if slow)
  Color:          #008767 / #B37700
  ```
  Shows: "42ms" or "1.2s"
- Expand icon: chevron-down (when collapsed, complete) / chevron-up (when expanded). 12px, --color-text-tertiary. Only shown for complete/warning steps.

**Step expanded content:**
```
Padding:        0 0 16px 0
Overflow:       hidden
Transition:     height --transition-slow (CSS height transition or Framer Motion AnimatePresence)
```

The default state for all steps is collapsed. Steps auto-expand when they become active, then can be manually collapsed/expanded after completion.

---

### Step 1: User Identity Resolution

**Label:** "User Identity Resolution"
**Sub-label:** "Scoping query to your business unit"
**Duration target:** <50ms (mocked)

**Collapsed (complete) state shows:**
A single row: colored identity badge showing "Finance BU" in #006FCF with a person-circle icon.

**Expanded content:**
```
Background:     --color-surface-secondary
Border-radius:  --radius-md
Padding:        12px
Margin-bottom:  4px
```

Content inside the expanded card:

Row 1: "User resolved to Finance Business Unit"
- Sub-text: "All retrieval scoped to model: `finance_model`"

Two data rows with labels and values:
```
User:       Finance Analyst
BU Model:   finance_model
Explores:   5 available
```

Render each row as:
- Left: label in --text-xs (11px), --color-text-tertiary, uppercase
- Right: value in --text-xs (11px), --font-medium, --color-text-primary

A light blue info banner at the bottom of the card:
```
Background:   #E6F0FA
Border-left:  3px solid #006FCF
Border-radius: --radius-sm
Padding:      8px 10px
Font:         --text-xs (11px), --color-text-primary
Text:         "Query scope: locked to Finance model. Cross-BU queries are not supported."
```

---

### Step 2: Intent Classification

**Label:** "Intent Classification"
**Sub-label:** "Parsing query type and extracting entities"
**Duration target:** 200-500ms (Gemini Flash)

**Collapsed (complete) state shows:**
A row of colored entity chips extracted from the query. Example for "Total billed business by generation":
- "data_query" intent badge in --color-info-light
- Metric chip: "total billed business" — background #E6F4F1, border none, color #008767
- Dimension chip: "generation" — background --color-info-light, color #006FCF
- Filter chip: "last 90 days" — background --color-warning-light, color #B37700

**Expanded content:**

Section 1 — Intent classification result:
```
Rows:
  Intent type:   data_query
  Complexity:    moderate
  Answerable:    Yes
```

Section 2 — Extracted entities (rendered as a structured list):
```
Metrics:       total billed business
Dimensions:    generation
Time range:    last 90 days
Filters:       (none)
```

Section 3 — Resolved terms (when synonyms are resolved):
```
"total billed business" → custins.total_billed_business
```
Rendered as: original term in --color-text-secondary with an arrow → resolved canonical name in --font-mono, --color-text-primary.

**Disambiguation sub-state:** If the intent step identifies ambiguity, a yellow warning treatment is applied:
- Step indicator turns amber (--color-warning)
- Expanded content shows the ambiguous term highlighted in amber
- A note: "2 possible interpretations found — see disambiguation below"
- The DisambiguationModal (see Section 13) is triggered

---

### Step 3: Vector Search

**Label:** "Vector Search"
**Sub-label:** "Semantic field matching via pgvector"
**Duration target:** 30-100ms

**Collapsed (complete) state shows:**
"Top match: custins.total_billed_business (0.96)" — rendered as a single-line summary.

**Expanded content:**

Header row: "Searching 17 fields in Finance model for [query entity]" — the entity is in quotes, slightly highlighted.

A table of results. Max 8 rows shown, with "Show all X results" link if more:

```
Table structure:
  Column 1: Field name in --font-mono, --text-xs (11px)
  Column 2: View (explore) in --text-xs, --color-text-secondary
  Column 3: Similarity score — numeric badge
  Column 4: Status indicator

Table styling:
  No outer border
  Row separator: 1px solid --color-border-default
  Row height: 32px
  Header: --text-xs (11px), --font-semibold, --color-text-tertiary, uppercase
  Alternate row: background --color-surface-secondary (very subtle)
```

Similarity score badge:
- Score >= 0.90: background #E6F4F1, color #008767
- Score 0.85-0.89: background --color-warning-light, color #B37700 — this is the "near-miss" state. An amber dot precedes the score.
- Score < 0.85: background --color-surface-tertiary, color --color-text-tertiary

The "near-miss" amber treatment on rows with δ < 0.05 from the top score: the entire row gets a left border of 2px solid #B37700 and slightly warmer background.

At the bottom of the expanded card:
- "Selected for fusion: 3 fields" in --text-xs, --color-text-secondary
- A list of the selected field names in --font-mono chips

---

### Step 4: Graph Validation

**Label:** "Graph Validation"
**Sub-label:** "Structural compatibility check via Apache AGE"
**Duration target:** 10-50ms

This is the most visually rich step. It visualizes the knowledge graph validation.

**Collapsed (complete) state shows:**
"Winning explore: finance_cardmember_360 — all 3 fields compatible" with a green check badge.

**Expanded content:**

Section 1 — Explore scoring table:

```
Shows all explores checked:
  Column 1: Explore name
  Column 2: Fields found (e.g., "3/3")
  Column 3: Score (numeric)
  Column 4: Status (winning / valid / excluded)

Winning row:  Highlighted with left border 2px solid #008767, background #E6F4F1
Valid rows:   Normal treatment
Excluded:     Strikethrough on field count, muted text
```

Section 2 — Graph mini-visualization:

A simplified node-edge diagram rendered inline. Not a full D3 force graph — keep it static and illustrative.

```
Canvas:   Background #F7F8F9, border-radius --radius-md, height 120px, padding 12px
```

Nodes:
- Blue filled circles (16px diameter, #006FCF) for field nodes that are selected
- Gray outlined circles (16px, border 1.5px #D1D5DB) for field nodes that were rejected
- Larger rounded-rectangle (24px height, auto-width) for the winning explore in #008767

Edges:
- Lines connecting field nodes to the explore node
- Color: #008767 for connected (selected), #D1D5DB for rejected
- Line width: 1.5px

Labels below each node in --text-xs (11px). Example layout (left-to-right):
```
[total_billed_business] ─── [finance_cardmember_360]
[generation]            ───/
```

Section 3 — Required filters identified:
```
Background:   --color-warning-light
Border-left:  3px solid #B37700
Border-radius: --radius-sm
Padding:      8px 10px
Font:         --text-xs (11px)
Text:         "Required filter identified: partition_date (mandatory for all Finance explores)"
```

Section 4 — Base view priority scoring (collapsed sub-row, expandable):
"Show join path analysis" — expands to show the join chain as text:
`finance_cardmember_360 → custins_customer_insights_cardmember (base) → cmdl_card_main (joined via cust_ref)`

---

### Step 5: Few-Shot Matching

**Label:** "Few-Shot Matching"
**Sub-label:** "Pattern lookup via FAISS golden query index"
**Duration target:** 5-20ms

**Collapsed (complete) state shows — two sub-cases:**

If a match is found:
"Match found: GQ-fin-006 (similarity: 0.92)" in green.

If no match found:
"No close match — proceeding on retrieval only" in --color-text-secondary.

**Expanded content:**

Case: Match found

```
Match card:
  Background:   --color-surface-secondary
  Border:       1px solid --color-border-default
  Border-radius: --radius-md
  Padding:      12px
```

Inside the match card:
- Match ID: "GQ-fin-006" in --font-mono, --text-xs
- Similarity bar: a small horizontal progress bar showing 0.92 similarity. Bar fill is #008767, track is --color-border-default. Height: 4px, width: 100%, border-radius full.
- Original query (from golden set): italic --text-xs (11px), --color-text-secondary. "How many active customers by generation?"
- What it confirmed: --text-xs (11px), --color-text-primary. "Confirmed: explore selection (finance_cardmember_360), partition filter required."

Case: No match found

```
No-match card:
  Background:   --color-surface-secondary
  Border:       1px dashed --color-border-strong
  Border-radius: --radius-md
  Padding:      12px
  Text:         "No golden query match above similarity threshold (0.85). Relying on vector + graph retrieval."
  Font:         --text-xs (11px), --color-text-secondary
```

At the bottom: "Golden index size: 47 verified queries" in --text-xs, --color-text-tertiary.

---

### Step 6: Fusion and Payload Construction

**Label:** "Fusion & Payload"
**Sub-label:** "RRF weighted merge → Looker MCP payload"
**Duration target:** 1-5ms (near-instant)

**Collapsed (complete) state shows:**
"Confidence: 94% — payload ready for Looker MCP"

**Expanded content:**

Section 1 — RRF fusion weights display:

A horizontal bar chart showing the three channel weights and their contribution.

```
Container:   height 72px
Three rows:
  Row 1: Graph     [████████████] 1.5x weight  "18 points"
  Row 2: Few-shot  [█████████  ] 1.2x weight  "14 points"
  Row 3: Vector    [████████   ] 1.0x weight  "11 points"

Bar styling:
  Graph bar:    fill #008767
  Few-shot bar: fill #006FCF
  Vector bar:   fill #9CA3AF
  Track:        --color-surface-tertiary
  Height:       6px, border-radius full

Labels:
  Left:   Channel name, --text-xs (11px), --color-text-secondary
  Right:  Weight and points, --text-xs (11px), --color-text-secondary
```

Section 2 — Final payload (the RetrievalResult):

A code-style block showing the JSON-like payload. Use the exact field names from `src/retrieval/models.py`:

```
Styling:
  Background:   #00175A (dark, like a terminal)
  Border-radius: --radius-md
  Padding:      12px
  Font:         --font-mono, --text-xs (11px)
  Color:        #F9FAFB (base text)

Syntax coloring:
  Keys:         #9CA3AF
  String values: #6EE7B7 (green-ish)
  Numbers:      #FCD34D (amber)
  Booleans:     #60A5FA (blue)
```

Content (formatted):
```json
{
  "action":     "proceed",
  "model":      "finance",
  "explore":    "finance_cardmember_360",
  "dimensions": ["cmdl.generation"],
  "measures":   ["custins.total_billed_business"],
  "filters":    {"partition_date": "last 90 days"},
  "confidence": 0.94
}
```

Section 3 — Filter value resolution (shown when a business term was resolved to a filter value):
```
"Millennials" → "Millennial"   (normalized to LookML enum value)
```
Rendered as: original term in amber, arrow, resolved value in green.

---

### Step 7: SQL Generation and Execution

**Label:** "SQL Generation & Execution"
**Sub-label:** "Looker MCP → BigQuery"
**Duration target:** 500ms SQL gen + 1-5s BQ execution**

This step has a distinctive interactive sub-state — it pauses for user confirmation before executing.

**Step 7 has three internal phases:**

**Phase A — SQL Generated (pause for confirmation)**

The step indicator shows blue (active, paused). The connector below does not complete. The step auto-expands.

Expanded content Phase A:

Header: "SQL generated — ready to execute" in --text-sm, --font-semibold.

The SQL block:
```
Background:   #1E1E2E  (dark, VS Code-like)
Border-radius: --radius-md
Padding:      16px
Font:         --font-mono, --text-sm (13px)
Color:        #CDD6F4  (base text)
Max-height:   200px
Overflow-y:   auto

Syntax highlighting:
  Keywords (SELECT, FROM, WHERE, JOIN, GROUP BY): #CBA6F7 (purple)
  Table/field names: #89DCEB (cyan)
  String literals: #A6E3A1 (green)
  Numbers: #FAB387 (orange)
  Comments: #585B70 (muted)
```

Below the SQL block, a cost estimate banner:
```
Background:     #FFF8E6
Border:         1px solid #B37700
Border-radius:  --radius-md
Padding:        10px 14px
Display:        flex, row, align-items center, gap 8px

Icon:           Warning triangle, 14px, #B37700
Text:           "Estimated scan: 2.3 GB — estimated cost: $0.011" in --text-xs (13px), #B37700
```

If the dry-run estimate is above threshold (e.g., >10 GB), change to --color-error-light with red border and a blocking message.

Confirmation buttons:
```
Display:    flex, row, gap 12px, margin-top 12px

"Run Query" button:
  Height:       40px
  Padding:      0 20px
  Background:   #008767
  Color:        #FFFFFF
  Font:         --text-sm (13px), --font-semibold
  Border-radius: --radius-md
  Icon:         Play arrow, 14px
  Hover:        background darken 8%

"Cancel" button:
  Height:       40px
  Padding:      0 16px
  Background:   transparent
  Color:        --color-text-secondary
  Border:       1px solid --color-border-strong
  Font:         --text-sm (13px), --font-regular
  Border-radius: --radius-md
  Hover:        background --color-surface-secondary
```

**Phase B — Executing**

On "Run Query" click:
- Step indicator shows animated spinner
- Buttons disappear
- A progress row appears below the SQL block:
  ```
  Icon:   Animated spinner (16px, --color-amex-blue, spinning at 1s)
  Text:   "Executing against BigQuery..." in --text-xs (13px), --color-text-secondary
  ```
- A real-time elapsed timer appears to the right: "1.2s..." counting up in --font-mono, --text-xs

**Phase C — Complete**

Step indicator turns green. The SQL block remains. A "Execution complete" row appears:
```
"Returned 8 rows in 1.8s — 2.3 GB scanned" in --text-xs (11px), --color-text-secondary
```

The result is rendered in the chat panel (see Section 10) simultaneously.

---

## 10. Results Presentation

Results appear in the chat panel as part of the AssistantResponse, below the summary answer.

### Result Table

Used for tabular data (most query results).

```
Width:          100%
Border-radius:  --radius-md
Border:         1px solid --color-border-default
Overflow:       hidden
Shadow:         --shadow-sm
```

**Table header row:**
```
Background:   --color-surface-secondary
Height:       36px
Padding:      0 12px
Font:         --text-xs (11px), --font-semibold, --color-text-secondary, uppercase
Letter-spacing: 0.5px
Border-bottom: 1px solid --color-border-default
```

**Table body rows:**
```
Height:       min 40px
Padding:      10px 12px
Font:         --text-sm (13px), --font-regular, --color-text-primary
Border-bottom: 1px solid --color-border-default (except last row)

Alternate rows:
  Even: background #FFFFFF
  Odd:  background --color-surface-secondary (#F7F8F9)

Hover:
  Background: #EEF4FC (very light blue tint)
  Transition: --transition-fast
```

**Numeric values** in table cells: right-aligned, --font-mono, --text-sm.

**Large numbers** (e.g., 2,400,000): formatted with commas. Values > 1 million may be formatted as "2.4M" with a tooltip showing the full number on hover.

**Row limit:** Show maximum 20 rows by default. If more rows exist, show a "Show all X rows" link below the table. Clicking expands the table or opens a scrollable container with max-height 400px.

**Table footer:**
```
Padding:      8px 12px
Font:         --text-xs (11px), --color-text-tertiary
Display:      flex, row, justify-content space-between

Left:   "X rows"
Right:  "Download CSV" link (--text-xs, --color-text-link)
```

### Result Chart (optional)

For data that naturally visualizes (e.g., "by generation" = bar chart), show a chart instead of or alongside the table. The chart appears above the table.

```
Height:       200px
Border-radius: --radius-md
Background:   #FFFFFF
Border:       1px solid --color-border-default
Padding:      16px
Margin-bottom: 12px
```

Chart style:
- Bar chart for categorical breakdowns
- Use Amex brand colors: primary bars in #006FCF, secondary in #9DC3E6 (light blue)
- No grid lines — horizontal guide lines only in rgba(0,0,0,0.05)
- Axis labels in --text-xs (11px), --color-text-secondary
- No chart title (the summary answer text serves this function)
- Tooltips on hover: white background, 1px border, --shadow-md, --text-xs, --font-medium

For the demo, charts are illustrative — use a simple recharts or chart.js bar chart. Exact library choice is Ayush's to make based on what's available.

---

## 11. Starter Query Cards

Shown in the WelcomeState on a new conversation. Five clickable cards that send the pre-set query.

### Grid Layout

```
Display:      grid
Grid-template-columns: repeat(2, 1fr)
Gap:          12px
Max-width:    680px
Margin:       0 auto
```

The 5th card (if odd count) is centered alone in the last row using `grid-column: 1 / -1` and `max-width: 50%` on the 5th item, centered.

### Card Design

```
Background:   #FFFFFF
Border:       1px solid --color-border-default
Border-radius: --radius-lg (12px)
Padding:      16px
Cursor:       pointer
Display:      flex, column, gap 8px
Shadow:       --shadow-sm
Transition:   transform --transition-default, shadow --transition-default, border-color --transition-default

Hover state:
  Border-color:   #006FCF
  Shadow:         --shadow-md
  Transform:      translateY(-2px)

Active/click:
  Transform:      translateY(0)
  Shadow:         --shadow-sm
```

### Card Anatomy

**Icon row** (top of card): A small icon (20px x 20px) inside a 32px x 32px rounded square. The icon and background color are category-specific:

| Query | Icon | Background |
|-------|------|------------|
| How many active customers do we have? | People/users icon | #E6F0FA |
| Total billed business by generation | Bar chart icon | #E6F4F1 |
| Average ROC by merchant category | Percentage / ROI icon | #FFF8E6 |
| Gross TLS sales by travel vertical | Airplane icon | #EEF4FC |
| Revolve index for Millennials | Circular arrows icon | #F3E8FF |

**Query text** (below icon): The full query text. --text-sm (13px), --font-medium, --color-text-primary. Max 2 lines, ellipsis if longer.

**Tag** (bottom of card): A small pill showing the category:
- "Customer" / "Spending" / "Profitability" / "Travel" / "Behavioral"
- Height: 20px, padding 0 8px, background --color-surface-tertiary, border-radius --radius-full, font --text-xs (11px), --font-medium, --color-text-secondary

### On-click Behavior

Clicking a card:
1. The card briefly scales down (transform: scale(0.97), 80ms) and back to scale(1) — tactile feedback.
2. The card query text appears in the chat input field as if the user typed it (no animation needed here).
3. After 100ms, the message is auto-sent (simulating the user pressing Enter).
4. The WelcomeState transitions to MessageThread — the query card grid fades out (opacity 0, transform translateY(-8px), 200ms), then the message thread fades in.

---

## 12. Interaction Design and Animations

### Pipeline Step Sequential Animation

When a query is submitted, the pipeline steps animate in sequence. This is the signature interaction of the Engineering View.

**Timing:**

Each step's visual state change is tied to the actual async backend call. In the demo, use mocked timing to simulate realistic latency:

| Step | Simulated delay |
|------|----------------|
| Step 1: Identity Resolution | 200ms after query submit |
| Step 2: Intent Classification | 800ms (simulate LLM call) |
| Step 3: Vector Search | +150ms |
| Step 4: Graph Validation | +80ms |
| Step 5: Few-Shot Matching | +60ms |
| Step 6: Fusion | +30ms |
| Step 7: SQL Gen | +600ms |
| Step 7: BQ Execution | +2000ms |

**Step activation animation:**

When a step transitions from Pending to Active:
1. The step indicator circle transitions: gray → blue with a 200ms ease-out
2. The step label transitions: --color-text-tertiary → --color-text-primary with 150ms ease
3. The step auto-expands its content (height animates from 0 to auto, 300ms ease-out with slight overshoot using cubic-bezier(0.34, 1.2, 0.64, 1))
4. A subtle pulse animation on the blue step indicator: the circle emits one ring that expands and fades (like a sonar ping). Duration: 600ms, opacity 0.4 → 0. The ring is the same color as the circle, 1.5px border, expanding from 20px to 36px diameter.
5. The vertical connector line below begins animating from gray to a dashed blue pattern.

**Step completion animation:**

When a step transitions from Active to Complete:
1. The step indicator transitions: blue with spinner → green with checkmark (200ms)
2. The checkmark icon scales in from scale(0) to scale(1) using the spring transition.
3. The timing badge fades in to the right of the step label (opacity 0 → 1, translateX(-4px) → translateX(0), 200ms).
4. The vertical connector below transitions from dashed blue → solid green (300ms).
5. The step content collapses back to a one-line summary (300ms) — but only if it was auto-expanded and the user has not manually interacted with it. If the user has expanded it manually, leave it open.

**The net effect:** A smooth visual "running waterfall" down the 7 steps, each one lighting up blue as it starts and turning green as it finishes, with a green line of completed progress growing downward.

### View Mode Toggle Animation

Switching from Analyst View to Engineering View:

1. The toggle pill slides right (transform: translateX, 200ms ease-out).
2. The main content area width animates: the chat panel smoothly shrinks to 55% (width transition, 300ms ease-out).
3. The Engineering Panel slides in from the right: transform translateX(100%) → translateX(0), 350ms ease-out with slight overshoot (cubic-bezier(0.34, 1.1, 0.64, 1)).
4. If there is an active query result, the pipeline trace populates immediately in the panel showing the last completed run.

Switching back to Analyst View:
1. Reverse: panel slides out right, chat panel expands to full width.

### Message Send Animation

1. User presses Enter or clicks Send.
2. The message bubble appears immediately at the bottom of the thread with a subtle scale-in (scale(0.95) → scale(1), 150ms, ease-out).
3. The input field clears.
4. The typing indicator appears 200ms after the message bubble (avoid jarring instant state change).
5. If in Engineering View: Step 1 activates simultaneously with the typing indicator.

### Disambiguation Animation

When the system detects ambiguity and the disambiguation modal appears:
1. The typing indicator is replaced by the assistant response showing the disambiguation question.
2. The intent step in the Engineering View turns amber.
3. The modal overlay fades in (opacity 0 → 1, 200ms).
4. The modal itself scales in: scale(0.96) → scale(1), 250ms, ease-out.

### Hover and Focus States

All interactive elements follow a consistent hover pattern:
- Button hover: 100ms transition, slight darken or background tint
- Card hover: 200ms transition, elevation increase + translateY(-2px)
- Link hover: underline appears, color darkens
- Input focus: border color → #006FCF, focus ring appears (see input spec)

All transitions use the defined transition tokens — no ad-hoc values.

---

## 13. Error States and Edge Cases

### Disambiguation Flow

Triggered when: Step 4 (Graph Validation) finds multiple valid explores with equal score, OR Step 2 (Intent Classification) finds multiple possible interpretations of a term.

**Chat panel treatment:**

The assistant response does not show a result. Instead:

```
SummaryAnswer text:  "I found 2 possible interpretations of your query.
                      Which one did you mean?"
```

Below the text, option cards are shown (not chips — cards are easier to read):

```
Option card:
  Width:          100%
  Padding:        12px 16px
  Border:         1.5px solid --color-border-default
  Border-radius:  --radius-md
  Cursor:         pointer
  Margin-bottom:  8px
  Display:        flex, row, align-items center, justify-content space-between

  Hover:
    Border-color: #006FCF
    Background:   #E6F0FA

  Left:
    Option label in --text-sm (13px), --font-medium, --color-text-primary
    Option description in --text-xs (11px), --color-text-secondary, margin-top 2px

  Right:
    Chevron-right icon, 14px, --color-text-tertiary
```

Example disambiguation scenario for "active customers":
- Option A: "Active Customers (Standard)" — field: `custins.active_customers_standard`, sub-text: "Standard cardmembers with activity in last 90 days"
- Option B: "Active Customers (Premium)" — field: `custins.active_customers_premium`, sub-text: "Premium cardmembers with activity in last 90 days"

Below the options: "--text-xs (11px), --color-text-tertiary, italic: 'Selecting an option will run the query. You can also type more details.'"

On selection: the selected card gets a green border (200ms), then the pipeline continues (Steps 5-7 activate) and the result is returned.

**Engineering View treatment:**

Step 2 or Step 4 turns amber. The expanded content shows the disambiguation options with the same amber left-border treatment. A note: "Pipeline paused — awaiting user disambiguation."

### Low Confidence State

Triggered when: fusion confidence score is below 0.75 (configurable threshold).

The result is still returned, but with a prominent confidence warning.

**Chat panel:**

The summary answer is shown normally, but preceded by:

```
Warning banner:
  Background:   #FFF8E6
  Border:       1px solid #B37700
  Border-radius: --radius-md
  Padding:      10px 14px
  Margin-bottom: 12px
  Display:      flex, row, gap 10px

  Icon:         Warning triangle, 16px, #B37700

  Text:         "Low confidence (61%). I may have misunderstood part of your
                question. Please verify the results."

  Font:         --text-sm (13px), --color-text-primary
```

The confidence badge in the metadata footer shows amber.

In Engineering View: Steps 3-5 show amber indicators. The footer confidence score is displayed in amber.

### Out-of-Scope Query

Triggered when: Intent classification returns `out_of_scope`, or the query is about data that doesn't exist in the Finance model.

**Chat panel:**

```
SummaryAnswer:  "This question is outside what I can answer with Finance
                data. I can only query data from the Finance Business Unit."

Below the text, a "What I can help with" section:
  - List of 3 relevant example queries (pulled from starter query list)
  - Each shown as a clickable chip

Footer text: "Need data from another business unit? Contact the data team."
```

No pipeline steps complete in Engineering View. Step 2 shows a red indicator. Steps 3-7 remain gray/pending.

### SQL Execution Error

Triggered when: BigQuery returns an error after query execution.

**Chat panel:**

The SQL block remains visible (expandable). Below it:

```
Error banner:
  Background:   #FDE8E8
  Border:       1px solid #C40000
  Border-radius: --radius-md
  Padding:      10px 14px
  Icon:         Alert circle, 16px, #C40000
  Text:         "Query execution failed: [error message, truncated to 120 chars]"
  Font:         --text-sm (13px), --color-text-primary
```

Recovery suggestion below the banner:
"Try rephrasing your question, or ask me to simplify the query."

Two action chips: "Try simplified query" / "Show full error"

In Engineering View: Step 7 shows a red indicator. The expanded content shows the BigQuery error in a red-bordered code block.

### Timeout State

Triggered when: BigQuery execution exceeds 8 seconds (configurable).

A "Query timed out" error is shown with:
- Estimated scan size that caused the timeout
- Suggestion: "Try narrowing your time range or adding a filter"
- A "Retry with suggested filter" action chip

### Partial Results

Triggered when: Some entities were matched but others were not (e.g., user asks for a field that doesn't exist in the model).

The result returns what was found, with a callout:

```
Info banner:
  Background:   #E6F0FA
  Border:       1px solid #006FCF
  Text:         "Note: I couldn't find data for [unmatched term].
                Showing results for [matched terms] only."
```

---

## 14. Dark Mode

The application supports dark mode toggled from the settings button in the top nav (or automatically respecting `prefers-color-scheme: dark`).

Dark mode is not an inversion — it is a deliberate redesign using the Amex dark palette.

### Color Overrides

```
--color-surface-primary:     #0A2472    (dark raised surface)
--color-surface-secondary:   #00175A    (base dark background)
--color-surface-tertiary:    #051542    (deepest dark, under components)
--color-text-primary:        #F9FAFB
--color-text-secondary:      #9CA3AF
--color-text-tertiary:       #6B7280
--color-border-default:      #1E3A7A
--color-border-strong:       #2D4F99
```

### Component Adjustments in Dark Mode

**Top nav:** Unchanged (already dark blue). The border below it changes to 1px solid rgba(255,255,255,0.08).

**Sidebar:**
- Background: #0A2472
- Border-right: 1px solid #1E3A7A
- Session item hover: background #1E3A7A
- Session item active: background rgba(0,111,207,0.25), border-left #006FCF

**Chat area background:** #00175A

**User message bubble:**
- Background: #006FCF (unchanged — it reads well on dark)

**Assistant response:**
- Background: #0A2472 (for the expanded content cards)

**Result table:**
- Background: #0A2472
- Header: #051542
- Alternate rows: #051542 / #0A2472
- Border: #1E3A7A

**Starter query cards:**
- Background: #0A2472
- Border: #1E3A7A
- Hover border: #006FCF

**Input field:**
- Background: #0A2472
- Border: #2D4F99
- Focus border: #006FCF
- Placeholder: #6B7280

**Engineering panel:**
- Background: #0A2472
- Header/footer: #051542
- The dark payload block (Step 6): unchanged — already dark terminal style

**Code/SQL blocks in dark mode:**
- Background: #010C1F (near-black)
- Border: #1E3A7A

**Warning/error banners:** Slightly increased opacity on the background color (from 0.08 to 0.15) to maintain visibility on dark backgrounds.

---

## 15. Responsive Behavior

The UI is primarily designed for desktop (1440px+). The Kalyan demo will be on a large monitor. These are the breakpoints to handle.

**1440px+ (primary target):** Full layout as described. Sidebar visible. Analyst View chat max-width 800px.

**1280px:** Sidebar collapses to 56px (icon-only mode — show session icons without labels). Chat max-width 720px.

**1024px:** Engineering View is disabled — the toggle shows a tooltip "Engineering View requires a wider screen" and remains on Analyst View. Sidebar remains icon-only.

**Below 1024px:** Application shows a banner: "Cortex works best on a desktop browser. Some features are limited on smaller screens." The chat still functions fully. Engineering View unavailable.

Do not optimize for mobile at this stage — it is not a priority and would distract from the demo build.

---

## 16. Full User Journey

This describes the complete interaction flow for the Thursday demo scenario: Kalyan opens the app and watches Saheb demonstrate it in Engineering View.

### Journey Step 1: Landing

**State:** Application loads, Engineering View already active (pre-set for demo), sidebar visible, welcome state shown in chat panel, pipeline panel is empty/idle.

**What Kalyan sees:** A premium dark-blue nav bar. On the left, the Cortex wordmark. In the center, the view toggle clearly shows "Engineering View" as active. On the right, "Finance Analyst / Finance BU" badge. The main area is split — left shows a clean welcome message and 5 starter query cards, right shows an empty pipeline trace panel with "Waiting for query..." in muted text.

### Journey Step 2: Query Selection

Saheb clicks the starter query card "Total billed business by generation."

**What happens:**
1. Card clicks with tactile scale animation.
2. The query text appears in the input.
3. 100ms later, it auto-sends.
4. The query bubble appears in the chat (blue bubble, right-aligned).
5. The typing indicator appears on the left.
6. Simultaneously in the Engineering Panel: Step 1 lights up blue.

### Journey Step 3: Pipeline Execution (the show)

Over the next ~4 seconds, the 7 steps animate through:

1. Step 1 (Identity Resolution): Appears instantly, auto-expands, shows "Finance BU" badge, turns green. (0.2s)
2. Step 2 (Intent Classification): Lights up blue, pulses. 0.8s later, turns green. Entities appear: metric chip "total billed business" (green), dimension chip "generation" (blue). Synonym resolution: "total billed business" → `custins.total_billed_business`. (total: ~1.0s from submit)
3. Step 3 (Vector Search): Immediately activates. 150ms later turns green. The table of field candidates appears with similarity scores. Top match highlighted in green: `custins.total_billed_business (0.96)`. Near-miss `custins.avg_billed_business (0.91)` shown in amber. (total: ~1.15s)
4. Step 4 (Graph Validation): Activates. Shows the mini node-edge graph. `finance_cardmember_360` highlighted as winning explore with green border. Required filter notice appears: partition_date. Turns green at 80ms. (total: ~1.23s)
5. Step 5 (Few-Shot): Activates. 60ms later: match found — "GQ-fin-006 (similarity: 0.92)". Turns green. (total: ~1.29s)
6. Step 6 (Fusion): Activates. Nearly instant (30ms). The dark terminal card appears showing the JSON payload with confidence 0.94. Turns green. Panel footer: "94%" in green, channel breakdown visible. (total: ~1.32s)
7. Step 7 (SQL Generation): Activates. After 600ms, the SQL block appears — a SELECT statement with GROUP BY generation, partition filter in WHERE clause. The cost estimate shows "2.1 GB — $0.010". The "Run Query" and "Cancel" buttons appear. Pipeline pauses here.

Saheb narrates: "The system generated the SQL from Looker's semantic layer — no LLM wrote this SQL. It's deterministic, validated, cost-estimated. Now I can review it and decide to run."

### Journey Step 4: Query Execution

Saheb clicks "Run Query."

**What happens:**
1. Buttons disappear. Spinner appears. Timer counts up.
2. In chat: typing indicator continues.
3. 1.8 seconds later: Step 7 turns green. "Returned 8 rows — 1.8s"
4. In chat: typing indicator disappears. The assistant response fades in:
   - Summary: "Total billed business by generation shows Millennials as the largest segment at $4.2B, followed by Gen X at $3.8B."
   - A bar chart appears above the table.
   - A clean table with 8 rows (one per generation) appears.
   - Metadata footer shows: "explore: finance_cardmember_360 | 94% confidence | Updated: 6 hours ago"
   - Follow-up chips: "Break down by card product" / "Compare to last quarter" / "Which generation has highest average spend?"

### Journey Step 5: Follow-Up

Saheb clicks "Compare to last quarter."

The query is sent. The Engineering Panel resets (all 7 steps go back to pending state) and the sequence begins again — this time faster because the few-shot match is higher confidence (the previous query was just run and added to context).

This demonstrates the conversational follow-up capability.

### Journey Step 6: Toggle to Analyst View

Saheb clicks the toggle to switch to Analyst View.

**What Kalyan sees:** The engineering panel slides out smoothly to the right. The chat panel expands to full width. The result table and chart are still visible — nothing is lost. The interface looks exactly like a premium internal tool — clean, simple, no visible complexity.

Saheb: "This is what a Finance analyst would see every day. No SQL, no pipeline steps, no noise. Just the answer."

---

## 17. Accessibility

The demo must be accessible at a minimum level. These are non-negotiable:

**Keyboard navigation:** All interactive elements (buttons, cards, input, toggle) must be reachable via Tab. Active element must have a visible focus ring (2px solid #006FCF, offset 2px).

**Focus ring:**
```
outline: 2px solid #006FCF
outline-offset: 2px
border-radius: match element border-radius
```
Remove focus ring on mouse click only (`:focus:not(:focus-visible)` pattern).

**Color contrast:** All text must pass WCAG AA contrast (4.5:1 for normal text, 3:1 for large text). The Amex blue (#006FCF) on white passes. White on dark blue (#00175A) passes. Check all secondary text colors — #6B7280 on white fails; use #595959 minimum if compliance is needed. For the demo, target AA compliance on primary content, best-effort on tertiary labels.

**ARIA labels:** All icon-only buttons must have `aria-label`. The view toggle must use `role="radiogroup"` with `role="radio"` on each segment and `aria-checked`. The pipeline steps should use `aria-live="polite"` on the step list container so screen readers announce completions.

**Animation:** Respect `prefers-reduced-motion`. When this media query is set, all transitions use 0ms duration (no animation). The pipeline steps still change state but without animation. Use the pattern:
```css
@media (prefers-reduced-motion: reduce) {
  * { transition-duration: 0ms !important; animation-duration: 0ms !important; }
}
```

**Semantic HTML:** Use proper heading hierarchy (h1 for product name, h2 for section headers, h3 for step labels). Tables must have `<thead>` with `<th scope="col">`. Buttons must be `<button>`, not `<div>`.

---

## 18. Developer Implementation Notes

These notes are specifically for Ayush to prevent common pitfalls.

### Technology Assumptions

These are recommendations, not constraints. Ayush should use what is already in the project stack or what he is most productive with:
- React 18+ with functional components and hooks
- TypeScript strongly preferred (the pipeline state maps directly to the `CortexState` and `RetrievalResult` types in `src/`)
- CSS-in-JS or CSS Modules — avoid global CSS overrides
- For chart: Recharts or Chart.js (both are small, well-maintained)
- For animations: Framer Motion is the cleanest option for the step animations; CSS transitions are acceptable for simpler effects
- For the code block syntax highlighting: Prism.js or highlight.js (Prism is lighter)
- No component library — build from tokens to maintain full control over the design

### Data Mocking for Demo

All pipeline data is mocked. Create a `mockPipeline.ts` that simulates the 7-step response with realistic timing. The mock data should be structured to match the actual `CortexState` and `RetrievalResult` data models from `src/retrieval/models.py` and `src/pipeline/state.py`. This ensures the UI can be connected to the real pipeline later by swapping one file.

The mock should include one scenario per starter query. Each scenario has the full 7-step trace with realistic field names, similarity scores, and SQL. The SQL should be real BigQuery SQL based on the actual LookML field names in `cortex/lookml/views/`.

For the demo query "Total billed business by generation", the mocked SQL should be approximately:
```sql
SELECT
  cmdl_card_main.generation,
  SUM(custins_customer_insights_cardmember.total_billed_business_amt) AS total_billed_business
FROM
  `axp-lumid.dw.custins_customer_insights_cardmember` AS custins_customer_insights_cardmember
  JOIN `axp-lumid.dw.cmdl_card_main` AS cmdl_card_main
    ON custins_customer_insights_cardmember.cust_ref = cmdl_card_main.cust_ref
WHERE
  custins_customer_insights_cardmember.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC
```

### Component File Structure

Suggested file organization:
```
src/
  components/
    layout/
      TopNavBar.tsx
      Sidebar.tsx
      MainLayout.tsx
    chat/
      ChatPanel.tsx
      MessageThread.tsx
      UserMessage.tsx
      AssistantResponse.tsx
      ResultTable.tsx
      ResultChart.tsx
      TypingIndicator.tsx
      ChatInput.tsx
      StarterQueryCards.tsx
      FollowUpChips.tsx
      MetadataFooter.tsx
    pipeline/
      EngineeringPanel.tsx
      PipelineStepList.tsx
      PipelineStep.tsx
      steps/
        Step1Identity.tsx
        Step2Intent.tsx
        Step3VectorSearch.tsx
        Step4GraphValidation.tsx
        Step5FewShot.tsx
        Step6Fusion.tsx
        Step7Execution.tsx
    shared/
      Badge.tsx
      CodeBlock.tsx
      Tag.tsx
      ConfidenceBar.tsx
      DisambiguationModal.tsx
  tokens/
    colors.ts
    typography.ts
    spacing.ts
    shadows.ts
    transitions.ts
  mock/
    mockPipeline.ts
    scenarios/
      totalBilledBusinessByGeneration.ts
      activeCustomers.ts
      avgRocByMerchant.ts
      tlsSalesByTravel.ts
      revolveIndexMillennials.ts
  hooks/
    usePipelineAnimation.ts
    useViewMode.ts
    useSession.ts
```

### Animation Implementation Pattern

For the sequential step activation, use a single `usePipelineAnimation` hook that takes the current pipeline state and returns the visual state for each step. This hook drives all Engineering Panel animations. The hook should watch the `activatedAt` timestamp per step and compute the derived visual state (pending / active / complete / warning / error). Steps auto-advance when the mock (or real) pipeline emits state changes via a callback or observable.

Avoid directly animating in individual step components — the hook is the single source of truth for timing.

### The Drag Handle

The drag handle between chat panel and engineering panel is a nice-to-have — skip it if time is short. Implement as a fixed 45/55 split with no drag capability for the demo.

### SQL Syntax Highlighting

Use Prism.js with the `sql` language pack and the `vsc-dark-plus` theme (it matches the VS Code dark terminal aesthetic specified in Step 7). Apply the dark background (#1E1E2E) as a CSS override on the `pre` element. Do not use the default Prism themes — they conflict with the design.

### Performance

The Engineering Panel's 7-step animation must not cause jank. Key rules:
- All animations must use `transform` and `opacity` only — never animate `height`, `width`, `top`, or `left` directly. For height transitions, use `max-height` with `overflow: hidden` as a workaround, or use Framer Motion's `AnimatePresence` with `layout` prop.
- The typing dots animation must use CSS `@keyframes`, not JavaScript intervals.
- The pipeline step connector line color transition must use CSS transition on the `background-color` property.

### State Management

For the demo, React `useState` and `useContext` are sufficient. No Redux or Zustand needed. The pipeline state lives in a single context (`PipelineContext`) that is consumed by both the ChatPanel (for typing indicators) and the EngineeringPanel (for step visualization).

### Demo-Specific Hard-Coding

For Thursday's demo only, it is acceptable to hard-code:
- The user identity as "Finance Analyst / Finance BU"
- The session list in the sidebar (3-4 past sessions showing realistic query titles)
- The initial view mode as Engineering View (override the default)
- The current time for the greeting ("Good morning, ...")

Mark all hard-coded demo values with a comment: `// DEMO: replace with real value before production`

---

*End of Cortex Demo UI Design Specification*

*For questions about the backend data models, refer to `cortex/src/pipeline/state.py` (pipeline state), `cortex/src/retrieval/models.py` (RetrievalResult schema), and `cortex/lookml/demo_queries.md` (realistic demo query scenarios). For LookML field names used in the mocked SQL, refer to `cortex/lookml/views/`.*

---

## 19. Metric Playground

### Overview

The Metric Playground is a standalone educational section of the Cortex demo UI. It is not part of the query pipeline — it lives outside the main chat flow and is accessed via a dedicated top-nav tab labeled **"Metric Playground"** (positioned to the right of the main "Cortex" navigation item).

**Purpose:** To show any stakeholder — analyst, executive, or data steward — exactly how a metric moves from a raw BigQuery column to an enriched, AI-queryable asset. This section answers the question Kalyan or Jeff will invariably ask: "How does the AI actually know what 'total spend' means?"

**Audience for this section during the demo:** Kalyan (vision + execution proof), Sulabh (technical depth), and any data steward who will use Renuka's enrichment UI. The Playground is where those two workstreams — Cortex and Lumi — visibly intersect.

**Tone:** Premium interactive documentation. Think Stripe Docs or the Vercel guides — clean, structured, every piece of information earns its presence.

---

### 19.1 Navigation Entry Point

The top navigation bar gains one new item to the right of the active "Cortex" label:

```
[ Cortex ]   [ Metric Playground ]
```

**Styling:**
```
Tab (inactive):
  font: Inter 14px / 500
  color: #6B7280
  padding: 0 16px
  border-bottom: 2px solid transparent

Tab (active / hover):
  color: #006FCF
  border-bottom: 2px solid #006FCF
  transition: color 150ms ease, border-color 150ms ease
```

Clicking "Metric Playground" replaces the entire main content area (chat panel + engineering panel) with the Playground layout. The top nav bar and sidebar chrome remain visible but the sidebar collapses to icon-only width (48px) because the Playground does not use chat history. A back-arrow in the top-left of the content area ("Back to Cortex") returns to the main demo view, preserving the last chat session state.

---

### 19.2 Playground Layout

The Playground uses a two-column layout on desktop:

```
+-----------------------------------------------------------+
|  TOP NAV BAR (unchanged)                                  |
+-----------------------------------------------------------+
| [48px]  |  PLAYGROUND CONTENT AREA                       |
| icon    |                                                  |
| sidebar |  [ Tab Bar: 4 tabs ]                            |
|         |  +-------------------------------------------+  |
|         |  |  TAB CONTENT (scrollable)                 |  |
|         |  |                                           |  |
|         |  +-------------------------------------------+  |
+---------+---------------------------------------------------+
```

**Playground content area max-width:** 960px, centered with `margin: 0 auto`.
**Background:** `#F7F8F9` (same as global app background).
**Tab bar:** Sticky at top of content area, `background: #FFFFFF`, `border-bottom: 1px solid #E5E7EB`, `box-shadow: 0 1px 3px rgba(0,0,0,0.06)`.

---

### 19.3 Tab Bar

Four tabs, rendered as a horizontal pill-style segmented control:

```
[ What is a Metric? ]  [ Metric Hierarchy ]  [ Define a Metric ]  [ How the AI Uses It ]
```

**Tab bar container:**
```css
display: flex;
gap: 4px;
padding: 12px 24px;
background: #FFFFFF;
border-bottom: 1px solid #E5E7EB;
position: sticky;
top: 52px;  /* height of global top nav */
z-index: 10;
```

**Individual tab:**
```css
/* Inactive */
padding: 8px 20px;
border-radius: 6px;
font: Inter 14px / 500;
color: #374151;
background: transparent;
cursor: pointer;
transition: background 120ms ease, color 120ms ease;

/* Active */
background: #EBF4FF;
color: #006FCF;
font-weight: 600;

/* Hover (inactive) */
background: #F3F4F6;
```

Each tab is self-contained. Switching tabs does not reset state within tabs — if a user has expanded a code block in Tab 1, it remains expanded when they return.

---

### 19.4 Tab 1: "What is a Metric?"

**Purpose:** Teach the three-layer model using `total_billed_business` as the canonical example. Each layer builds on the one below — the animation makes this causal relationship physically visible.

#### Layout

Vertically stacked: three layer cards connected by animated arrows. Each card is full-width within the content area. A layer number badge (01 / 02 / 03) anchors the visual hierarchy.

```
+---------------------------------------------------------------+
|  LAYER 01 — Raw Column                              [?]       |
|  "billed_business: a dollar amount on each transaction row"   |
|  +-----------------------------------------------------------+ |
|  | [ Mini data table — 5 sample rows ]                      | |
|  +-----------------------------------------------------------+ |
+---------------------------------------------------------------+
        |
        v  (animated arrow — blue, #006FCF)
+---------------------------------------------------------------+
|  LAYER 02 — Metric Definition                       [?]       |
|  "SUM(billed_business): the aggregation rule"                 |
|  +-----------------------------------------------------------+ |
|  | [ LookML measure code block ]                            | |
|  +-----------------------------------------------------------+ |
+---------------------------------------------------------------+
        |
        v  (animated arrow — blue, #006FCF)
+---------------------------------------------------------------+
|  LAYER 03 — Enriched Definition                     [?]       |
|  "How Cortex understands it"                                  |
|  +-----------------------------------------------------------+ |
|  | [ TaxonomyEntry JSON block ]                             | |
|  +-----------------------------------------------------------+ |
+---------------------------------------------------------------+
```

#### Layer Card Styling

```css
/* Card */
background: #FFFFFF;
border: 1px solid #E5E7EB;
border-radius: 12px;
padding: 24px;
margin-bottom: 0;  /* gap controlled by arrow spacer */

/* Layer number badge */
display: inline-block;
padding: 2px 10px;
border-radius: 99px;
font: Inter 11px / 700;
letter-spacing: 0.08em;
text-transform: uppercase;

/* Layer 01 badge */  background: #F3F4F6;  color: #6B7280;
/* Layer 02 badge */  background: #EBF4FF;  color: #006FCF;
/* Layer 03 badge */  background: #ECFDF5;  color: #008767;

/* Card: active/clicked state */
border-color: #006FCF;
box-shadow: 0 0 0 3px rgba(0, 111, 207, 0.12);
transition: border-color 200ms ease, box-shadow 200ms ease;
```

#### Connecting Arrow

```
Arrow spacer height: 40px
Arrow: centered SVG chevron-down, 20×20px, color #006FCF
Animation: on click of a card, the arrow below it pulses (scale 1 → 1.2 → 1, 300ms)
```

#### Tooltip ([?] button)

Small circular button, 18px diameter, color #9CA3AF. On hover/click, a tooltip appears explaining why this layer matters:

- Layer 01: "Raw columns have no meaning to an AI. 'billed_business' as a string is just noise."
- Layer 02: "The aggregation rule is the metric formula. But 'total_billed_business' still means nothing to natural language."
- Layer 03: "Enriched descriptions, synonyms, and required filters are what allow Cortex to map 'total spend' to this exact field."

Tooltip styling:
```css
background: #00175A;
color: #FFFFFF;
font: Inter 13px / 400;
padding: 10px 14px;
border-radius: 8px;
max-width: 260px;
box-shadow: 0 4px 16px rgba(0, 23, 90, 0.20);
```

#### Layer 01 Content — Mini Data Table

A 5-row sample table showing what `billed_business` looks like before aggregation:

```
┌──────────────┬──────────────────┬─────────────────────┬──────────────────┐
│ cust_ref     │ partition_date   │ billed_business     │ generation       │
├──────────────┼──────────────────┼─────────────────────┼──────────────────┤
│ CUST_0041892 │ 2025-11-15       │ 247.83              │ Millennial       │
│ CUST_0087231 │ 2025-11-15       │ 1,204.50            │ Gen X            │
│ CUST_0012943 │ 2025-11-16       │ 88.20               │ Gen Z            │
│ CUST_0056712 │ 2025-11-16       │ 3,891.00            │ Boomer           │
│ CUST_0099034 │ 2025-11-17       │ 612.45              │ Millennial       │
└──────────────┴──────────────────┴─────────────────────┴──────────────────┘
```

Table styling: same as ResultTable in Section 10. `billed_business` column header is highlighted with a subtle blue underline (`border-bottom: 2px solid #006FCF`) to call it out as the target column.

Below the table, a muted label: `Showing 5 of ~2.4B rows in custins_customer_insights_cardmember`. Font: Inter 12px, color: #9CA3AF.

#### Layer 02 Content — LookML Code Block

```lookml
measure: total_billed_business {
  type: sum
  sql: ${TABLE}.billed_business ;;
  label: "Total Billed Business"
  value_format_name: usd_0
  group_label: "Spend Metrics"
}
```

Rendered as a syntax-highlighted code block. Use the same Prism.js + `vsc-dark-plus` theme from Section 18. Background: `#1E1E2E`. The `sql` line is highlighted in amber (`#B37700` background, 20% opacity) to draw the eye to the column reference. An "Expand" chevron on the right reveals the full LookML view definition in a drawer below (containing all fields, not just this measure).

#### Layer 03 Content — Enriched Definition Block

```json
{
  "canonical_name": "total_billed_business",
  "display_label": "Total Billed Business",
  "description": "Total dollar amount billed to cardmembers within the period. Represents gross spend volume before adjustments or reversals.",
  "synonyms": [
    "total spend",
    "billed business",
    "gross spend",
    "spend volume",
    "billed dollars",
    "total billed"
  ],
  "formula": "SUM(billed_business)",
  "aggregation_type": "SUM",
  "required_filters": {
    "partition_date": "BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) AND CURRENT_DATE()"
  },
  "group_label": "Spend Metrics",
  "domain": "Finance",
  "owner": "Finance Data Office",
  "looker_field": "custins_customer_insights_cardmember.total_billed_business_amt",
  "governance_tier": "canonical"
}
```

Rendered as a JSON code block (Prism.js, `json` language). The `"synonyms"` array is highlighted with a green left border (`border-left: 3px solid #008767`) and a label above it: `"These synonyms are the vocabulary Cortex searches."` The `"required_filters"` object is highlighted with an amber left border and label: `"This filter is injected automatically — the analyst never needs to specify it."`

#### Interaction — Click to Animate

When the user clicks a layer card:
1. The clicked card border animates to `#006FCF` (200ms ease).
2. The arrow below the card pulses (scale up/down, 300ms).
3. The card immediately below gains a subtle shimmer (`background` transitions from `#FFFFFF` → `#EBF4FF` → `#FFFFFF`, 600ms) to communicate "this is what the layer above unlocks."
4. If the user clicks Layer 01, only the Layer 02 shimmer fires. If they click Layer 02, only Layer 03 shimmers. Layer 03 has no arrow below — instead, a small success badge appears: `"AI-queryable"` in `#008767`.

The interaction works in both directions — clicking a lower layer scrolls the highlighted information up to the contributing layer.

---

### 19.5 Tab 2: "Metric Hierarchy"

**Purpose:** Show that metrics have governance tiers. Not every "active customers" definition is the same — and uncontrolled proliferation is what breaks data trust.

#### Layout

Left column (320px fixed): the interactive tree. Right column (fills remaining width): the detail panel for the selected node.

```
+-----------------------------+  +------------------------------+
|  METRIC TREE                |  |  DETAIL PANEL                |
|                             |  |                              |
|  [C] Active Customers       |  |  (content changes on click)  |
|   ├── [B] Active (Premium)  |  |                              |
|   ├── [B] Active (Risk-Adj) |  |                              |
|   └── [T] Millennial Act. % |  |                              |
|                             |  |                              |
|  [ + Create Metric ]        |  |                              |
+-----------------------------+  +------------------------------+
```

#### Tree Node Styling

Each node is a pill with a governance tier badge:

```
[C]  Canonical        — badge: #00175A background, white text
[B]  BU Variant       — badge: #006FCF background, white text
[T]  Team Derived     — badge: #B37700 background, white text
```

Node:
```css
display: flex;
align-items: center;
gap: 10px;
padding: 10px 14px;
border-radius: 8px;
font: Inter 14px / 500;
color: #111827;
cursor: pointer;
border: 1px solid transparent;
transition: background 120ms, border-color 120ms;

/* Hover */
background: #F3F4F6;

/* Selected */
background: #EBF4FF;
border-color: #006FCF;
```

The tree connector lines use SVG with `stroke: #E5E7EB`, `stroke-width: 1.5`. On selection, the path from root to selected node animates to `stroke: #006FCF`.

#### Tree Nodes — Mock Data

```
[C] Active Customers
    Definition: Cardmembers who billed ≥ $50 in the trailing 90 days
    Source: Finance Data Office
    Govern tier: Canonical (company-wide)

  [B] Active Customers (Premium)
      Inherits: all fields from parent
      Override: threshold = $100 (instead of $50)
      Owner: Premium BU

  [B] Active Customers (Risk-Adjusted)
      Inherits: all fields from parent
      Override: adds filter WHERE revolve_flag = TRUE
      Owner: Risk BU

  [T] Millennial Active %
      Computed: Active Customers (generation = 'Millennial') / Total Active Customers
      No governance tier — team-derived, not certified
      Owner: Finance Analytics (ad hoc)
```

#### Detail Panel — Inheritance View

When a BU Variant node is selected, the detail panel shows a two-column diff:

```
+---------------------------+  +---------------------------+
|  INHERITED FROM PARENT    |  |  THIS VARIANT OVERRIDES   |
|  (greyed out)             |  |  (highlighted)            |
|  threshold: $50           |  |  threshold: $100          |
|  period: trailing 90d     |  |  (unchanged)              |
|  formula: COUNT(DISTINCT) |  |  (unchanged)              |
|  filter: none             |  |  (unchanged)              |
+---------------------------+  +---------------------------+
```

Inherited fields render at 50% opacity with a lock icon. Overridden fields render at full opacity with an edit pencil icon and a blue left border.

When the canonical node is selected, the detail panel shows the full `TaxonomyEntry` JSON (same format as Tab 1 Layer 03).

When the team-derived node ("Millennial Active %") is selected, the detail panel shows a warning banner:

```
+-----------------------------------------------------------------+
|  [!]  Not Governed                                              |
|  This metric has no canonical owner and is not certified.       |
|  Queries that resolve to this definition may produce            |
|  inconsistent results across teams.                             |
|  [ Promote to Canonical ]  [ View Lineage ]                     |
+-----------------------------------------------------------------+
```

Banner styling:
```css
background: #FFFBEB;
border: 1px solid #B37700;
border-radius: 8px;
padding: 16px;
color: #92400E;
font: Inter 13px / 400;
```

#### "Create Metric" Button — Deduplication Warning

The "Create Metric" button at the bottom of the tree panel is mocked to demonstrate the similarity-check flow. When clicked, it opens a small inline form:

```
+-------------------------------------------+
|  Metric name:  [ Active Cardholders...  ] |
+-------------------------------------------+
```

As the user types "Active Cardholders" (after ~300ms debounce), a warning panel appears immediately below the input:

```
+-----------------------------------------------------------------+
|  [~]  Similar metric found                                      |
|  "Active Customers" — 92% match                                 |
|  Canonical  |  Finance Data Office  |  $50 threshold            |
|                                                                  |
|  [ Use Existing ]  [ Create Anyway — I know what I'm doing ]   |
+-----------------------------------------------------------------+
```

Warning styling:
```css
background: #FFFBEB;
border-left: 3px solid #B37700;
border-radius: 0 8px 8px 0;
padding: 14px 16px;
```

The similarity score (92%) should visually display as a small horizontal bar under the percentage, filled to 92% in `#B37700`. This makes the abstract score tangible.

"Use Existing" dismisses the modal and selects the "Active Customers" canonical node in the tree. "Create Anyway" advances to a simplified definition form (Tab 3 Card 2 layout, pre-populated with name).

---

### 19.6 Tab 3: "Define a Metric" (Three Paths)

**Purpose:** Show data stewards the three routes to creating an enriched metric. This tab is the functional intersection of Cortex (AI retrieval) and Lumi (semantic enrichment). A steward watching this understands their contribution feeds directly into AI accuracy.

#### Layout

Three equal-width cards side by side on desktop, stacking vertically on smaller viewports. Each card is independently interactive.

```
+----------------------+  +----------------------+  +----------------------+
|  PATH 1              |  |  PATH 2              |  |  PATH 3              |
|  From SQL            |  |  From Business       |  |  Enhance Existing    |
|                      |  |  Knowledge           |  |                      |
|  [ Paste SQL →       |  |  [ Fill Form →       |  |  [ Review LookML →   |
|    Extract Metric ]  |  |    AI Assists ]      |  |    AI Proposes ]     |
+----------------------+  +----------------------+  +----------------------+
```

Each card has a header bar with a path number badge and a short sub-label:

```
PATH 01   From SQL             — "You have existing SQL logic"
PATH 02   From Business        — "You know the definition, not the SQL"
PATH 03   Enhance Existing     — "A field exists — it just needs a description"
```

Card styling:
```css
background: #FFFFFF;
border: 1px solid #E5E7EB;
border-radius: 12px;
padding: 24px;
min-height: 480px;
display: flex;
flex-direction: column;
gap: 20px;

/* Path header bar */
background: #F7F8F9;
border-radius: 8px;
padding: 12px 16px;
margin: -24px -24px 0;  /* bleed to card edges */
border-bottom: 1px solid #E5E7EB;
```

Path badge colors:
```
PATH 01 — background: #EBF4FF;  color: #006FCF;
PATH 02 — background: #ECFDF5;  color: #008767;
PATH 03 — background: #F5F3FF;  color: #7C3AED;  (purple — distinct from Amex blues)
```

---

#### Card 1: "From SQL"

**Input area:**

```
┌─────────────────────────────────────────────────────┐
│  Paste your SQL query                               │
│  ┌─────────────────────────────────────────────┐   │
│  │  SELECT SUM(billed_business) /             │   │
│  │    COUNT(DISTINCT cust_ref)                 │   │
│  │  FROM custins                               │   │
│  │  WHERE partition_date >=                    │   │
│  │    DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)│   │
│  └─────────────────────────────────────────────┘   │
│  [ Extract Metric Definition ]                      │
└─────────────────────────────────────────────────────┘
```

The textarea uses the same code block styling (dark background `#1E1E2E`, monospace font, syntax highlighting for SQL). A placeholder text reads: `-- Paste any SQL with an aggregation...`

When "Extract Metric Definition" is clicked, a processing animation plays (the "AI Assist" spinner — described below), then the output panel appears below:

**Output area (appears after extraction):**

```
+---------------------------------------------+
|  [AI]  Proposed Metric Definition            |
+---------------------------------------------+
|  canonical_name:  spend_per_customer         |
|  display_label:   Spend Per Customer         |
|  formula:         SUM(billed_business) /     |
|                   COUNT(DISTINCT cust_ref)   |
|  aggregation:     RATIO                      |
|  required_filters:                           |
|    partition_date: trailing 90 days          |
|  suggested_synonyms:                         |
|    "avg spend per member"                    |
|    "per-customer spend"                      |
|    "average billed business"                 |
|    "spend per cardholder"                    |
+---------------------------------------------+
|  [ Accept ]  [ Edit ]  [ Discard ]           |
+---------------------------------------------+
```

The output panel uses a light green left border (`border-left: 3px solid #008767`) to signal AI output. The `suggested_synonyms` field is rendered with each synonym as a removable tag (green pill, same as the tag component in `shared/Tag.tsx`).

"Accept" triggers a brief success animation: the card border turns `#008767`, a checkmark icon fades in, and the card title updates to `"Spend Per Customer — Saved"`. "Edit" converts the output to an inline form. "Discard" resets to the empty input state.

#### AI Assist Spinner

Used in all three paths whenever LLM processing is simulated. Mock delay: 1.4 seconds.

```
Centered in output area:
  - Animated ring (SVG, rotating, stroke: #006FCF)
  - Label below ring: "Analyzing with Cortex AI..."
  - Font: Inter 13px, color: #6B7280
```

Do not use a generic spinner — the label "Analyzing with Cortex AI" is intentional for the demo.

---

#### Card 2: "From Business Knowledge"

A clean form. This is the steward's primary interface — no SQL required.

**Form fields:**

```
Name                [ Spend Per Customer                    ]
Definition          [ Total billed business in trailing 90  ]
                    [ days divided by distinct cardholder   ]
                    [ count...                              ]
Formula (optional)  [ SUM(billed_business) / COUNT(DISTINCT ]
Synonyms            [ avg spend per member  x ] [ + Add    ]
Owner               [ Finance Data Office                   ]
Domain              [v Finance         ]
```

All inputs use the same form styling as the rest of the app:
```css
border: 1px solid #E5E7EB;
border-radius: 6px;
padding: 8px 12px;
font: Inter 14px;
color: #111827;
background: #FFFFFF;

focus:
  border-color: #006FCF;
  box-shadow: 0 0 0 3px rgba(0, 111, 207, 0.12);
  outline: none;
```

The **Synonyms** field is a tag input: user types a term and presses Enter to add it as a pill. Each pill has an `×` to remove. Existing pills: `"avg spend per member"`, `"per-customer spend"`.

Below the Synonyms field, an **AI Assist badge:**

```
[✦ AI]  AI will suggest additional synonyms and related terms when you save
```

Badge styling:
```css
background: #EBF4FF;
border: 1px solid #BFDBFE;
border-radius: 6px;
padding: 8px 12px;
font: Inter 12px / 500;
color: #006FCF;
display: inline-flex;
align-items: center;
gap: 6px;
```

The `✦` icon is the "AI spark" icon from the main chat panel (see Section 8). Consistency of the AI indicator across the app is intentional — users should recognize it everywhere.

**"Save and Enrich" button:**

```css
background: #006FCF;
color: #FFFFFF;
padding: 10px 20px;
border-radius: 6px;
font: Inter 14px / 600;
```

When clicked: the mock shows the AI Assist spinner, then below the button a new panel appears:

```
+----------------------------------------------------+
|  [AI]  AI-suggested additions                      |
+----------------------------------------------------+
|  Additional synonyms:                              |
|    "average billed business"     [ Add ]           |
|    "spend per cardholder"        [ Add ]           |
|    "per-member spend"            [ Add ]           |
|  Related metrics to link:                          |
|    "total_billed_business"  (parent)  [ Link ]     |
|    "active_customers"  (denominator)  [ Link ]     |
+----------------------------------------------------+
```

Each "Add" button appends the synonym to the Synonyms tag field. Each "Link" button adds a relationship entry. This mock demonstrates the LLM-assisted enrichment workflow without requiring a real API call.

---

#### Card 3: "Enhance Existing"

**Scenario:** A LookML field exists but has no description. This is the most common real-world case at Amex — Ayush's mapped fields that are name-only.

**Before panel:**

```
+---------------------------------------------+
|  BEFORE — LookML field as imported          |
+---------------------------------------------+
  measure: total_billed_business {
    type: sum
    sql: ${TABLE}.billed_business ;;
  }
+---------------------------------------------+
```

Rendered as a code block (dark background). The absence of `label:`, `description:`, and `group_label:` is visually jarring against the enriched version — that contrast is the point.

A button below: `[ Generate Description ]`

After clicking (1.4s AI spinner), the **After panel** appears immediately below with a before/after diff view:

**After panel:**

```
+---------------------------------------------+
|  AFTER — AI-proposed enrichment             |
+---------------------------------------------+
  measure: total_billed_business {
    type: sum
    sql: ${TABLE}.billed_business ;;
+   label: "Total Billed Business"
+   description: "Total dollar amount billed to
+     cardmembers within the period. Represents
+     gross spend volume before adjustments or
+     reversals. Also known as: total spend,
+     billed business, gross spend."
+   group_label: "Spend Metrics"
+   tags: ["spend", "volume", "certified"]
  }
+---------------------------------------------+
```

The diff uses the standard code diff convention: added lines have a green left border and `background: rgba(0, 135, 103, 0.06)`. The `+` prefix on added lines renders in `#008767`.

Below the diff, a three-button row:

```
[ Approve ]  [ Edit Inline ]  [ Regenerate ]
```

"Approve" animates the card to success state (same as Card 1). "Edit Inline" converts the "After" code block to an editable textarea while preserving syntax highlighting. "Regenerate" fires another 1.4s mock and replaces the After panel with a slightly different proposed description (mock variation B — pre-written).

---

### 19.7 Tab 4: "How the AI Uses It"

**Purpose:** Close the loop. Show, step-by-step, how the enriched taxonomy entry (built in Tabs 1–3) powers a real Cortex query. This tab is the most important one for the Kalyan demo — it answers "why does any of this matter?"

#### Layout

Full-width, vertically stacked. A query input at the top (pre-filled, read-only for the demo). Below it, four numbered pipeline trace steps. Each step is a card that auto-expands in sequence (1.2s delay between expansions on page load, or user can click to jump).

At the bottom, a "What if it wasn't enriched?" callout card.

#### Query Bar (top)

```
+--------------------------------------------------------------+
|  Query:  "total spend by generation"           [Trace]       |
+--------------------------------------------------------------+
```

Styling: same as the main chat input but read-only, lighter background (`#F7F8F9`), no send icon. The `[Trace]` button is blue.

On page load (or on "Trace" click), the four steps animate open in sequence.

#### Step Cards

Each step is a collapsible card. Collapsed state: shows step number, title, and a one-line summary. Expanded state: shows the full technical detail.

**Connector between steps:** A dashed vertical line `(border-left: 2px dashed #E5E7EB)` that turns solid blue `(#006FCF)` when the step above it completes.

---

**Step 1: Vocabulary Match**

```
STEP 01   Vocabulary Match
          "total spend" → total_billed_business
```

Expanded content:

```
+------------------------------------------------------------------+
|  User said:  "total spend"                                        |
|                                                                   |
|  Vector search scanned enriched descriptions and synonyms...      |
|                                                                   |
|  TOP MATCHES                                                      |
|  ┌──────────────────────────────────────────────┬──────────┐     |
|  │ Field                                        │ Score    │     |
|  ├──────────────────────────────────────────────┼──────────┤     |
|  │ total_billed_business  (synonym: "total       │  0.96   │     |
|  │   spend" — exact match in synonyms)          │  ██████ │     |
|  │ spend_volume_mtd                             │  0.71   │     |
|  │                                              │  ████   │     |
|  │ net_revenue                                  │  0.44   │     |
|  │                                              │  ██     │     |
|  └──────────────────────────────────────────────┴──────────┘     |
|                                                                   |
|  Selected: total_billed_business  (score 0.96 > threshold 0.85)  |
+------------------------------------------------------------------+
```

The score bars are CSS `width` set to `{score * 100}%`, `background: #006FCF`, `border-radius: 3px`. The top match bar is `#006FCF` (full opacity). Lower matches use `rgba(0, 111, 207, 0.45)`.

A highlighted note below the table:

```
+------------------------------------------------------------------+
|  [!]  The synonym "total spend" exists because a data steward    |
|  added it in the enrichment workflow. Without it, vector         |
|  similarity for "total spend" vs "billed_business" would score   |
|  0.41 — below threshold. The query would fail to resolve.        |
+------------------------------------------------------------------+
```

Note styling:
```css
background: #EBF4FF;
border-left: 3px solid #006FCF;
border-radius: 0 8px 8px 0;
padding: 12px 16px;
font: Inter 13px;
color: #1E3A5F;
```

---

**Step 2: Graph Validation**

```
STEP 02   Graph Validation
          Confirmed: total_billed_business + generation in same explore
```

Expanded content:

```
+------------------------------------------------------------------+
|  AGE graph query (simplified):                                    |
|  MATCH (f1:Field {name: "total_billed_business"})-[:IN_EXPLORE]→ |
|  (e:Explore)-[:IN_EXPLORE]←(f2:Field {name: "generation"})      |
|  RETURN e.name                                                    |
|                                                                   |
|  Result:  explore = "customer_insights"  ✓                        |
|                                                                   |
|  If fields were in different explores, Cortex would ask:          |
|  "Did you mean [option A] or [option B]?"                         |
+------------------------------------------------------------------+
```

The Cypher query is rendered in a code block (same dark styling, `language-cypher`). Use generic Prism token coloring for Cypher (the `graphql` grammar is a reasonable fallback).

---

**Step 3: Filter Injection**

```
STEP 03   Required Filter Injected
          partition_date added automatically
```

Expanded content:

```
+------------------------------------------------------------------+
|  total_billed_business has a required_filter:                     |
|                                                                   |
|  "partition_date": "BETWEEN DATE_SUB(CURRENT_DATE(),             |
|                     INTERVAL 90 DAY) AND CURRENT_DATE()"         |
|                                                                   |
|  Injected into query automatically.                               |
|  The analyst did not specify a date range.                        |
|  Without this rule, the query would scan the full partition       |
|  (~2.4B rows) and potentially return wrong aggregates.            |
|                                                                   |
|  [!]  This filter rule was set by the Finance Data Office.        |
|  Governance, not guesswork.                                       |
+------------------------------------------------------------------+
```

The `required_filter` value is highlighted in the same amber left-border treatment from Tab 1 Layer 03.

---

**Step 4: SQL Generation**

```
STEP 04   SQL Generated by Looker
          Query ready to execute
```

Expanded content:

```sql
SELECT
  cmdl_card_main.generation,
  SUM(custins_customer_insights_cardmember.total_billed_business_amt)
    AS total_billed_business
FROM
  `axp-lumid.dw.custins_customer_insights_cardmember`
    AS custins_customer_insights_cardmember
  JOIN `axp-lumid.dw.cmdl_card_main` AS cmdl_card_main
    ON custins_customer_insights_cardmember.cust_ref
       = cmdl_card_main.cust_ref
WHERE
  custins_customer_insights_cardmember.partition_date
    BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND CURRENT_DATE()
GROUP BY 1
ORDER BY 2 DESC
```

Below the code block, a result table (same mock data as Section 10):

```
┌──────────────┬─────────────────────────┐
│ Generation   │ Total Billed Business   │
├──────────────┼─────────────────────────┤
│ Millennial   │ $2,847,392,140          │
│ Gen X        │ $1,923,847,203          │
│ Boomer       │ $1,654,209,887          │
│ Gen Z        │ $892,451,320            │
│ Silent       │ $124,830,092            │
└──────────────┴─────────────────────────┘
```

---

#### "What if it wasn't enriched?" Callout

This is the most important card in the entire Playground. It sits below all four steps, full width, with a distinct dark background.

```
+------------------------------------------------------------------+
|  What if total_billed_business had no enriched description?       |
|                                                                   |
|  Step 1 result without synonym "total spend":                     |
|    "total spend" vs "billed_business_amt"  →  score: 0.41        |
|    Below threshold (0.85). No match found.                        |
|                                                                   |
|  What Cortex would have returned:                                 |
|    "I couldn't find a metric matching 'total spend'.              |
|     Did you mean: net_revenue, spend_volume_mtd, or              |
|     total_transaction_amount?"                                    |
|                                                                   |
|  The synonym bridge is the fuel.                                  |
|  Without enrichment, Cortex is a very expensive keyword search.  |
+------------------------------------------------------------------+
```

Callout card styling:
```css
background: #00175A;
color: #FFFFFF;
border-radius: 12px;
padding: 28px 32px;
margin-top: 40px;

/* "What Cortex would have returned" block */
background: rgba(255, 255, 255, 0.08);
border-radius: 8px;
padding: 16px;
font-family: monospace;
color: #93C5FD;  /* soft blue for the mock AI response */

/* Final two lines */
font: Inter 15px / 700;
color: #FFFFFF;
margin-top: 20px;
```

The phrase "Without enrichment, Cortex is a very expensive keyword search." is the demo's rhetorical peak. It should render in `font-size: 16px`, `font-weight: 700`, and be the last thing visible before the section ends.

---

### 19.8 Animations and Interactivity Summary

All Playground animations must respect `prefers-reduced-motion` (same rule as Section 17 — `transition-duration: 0ms` when set).

| Element | Animation | Duration | Easing |
|---------|-----------|----------|--------|
| Tab switch | Fade in new content | 150ms | ease |
| Layer card click (Tab 1) | Border color + shimmer | 200ms / 600ms | ease |
| Connecting arrows | Pulse scale | 300ms | ease-out |
| Tree node selection (Tab 2) | Path color sweep | 400ms | ease-in-out |
| Similarity warning (Tab 2) | Slide down from input | 200ms | ease |
| Card path processing spinner (Tab 3) | Rotating ring | infinite | linear |
| Card accept success (Tab 3) | Border flash + checkmark | 300ms | ease |
| Pipeline step expand (Tab 4) | Max-height reveal | 350ms | ease-out |
| Step connector line | Color transition | 400ms | ease |
| Score bars (Tab 4) | Width from 0 | 600ms | ease-out |

The Tab 4 pipeline auto-plays on first visit (steps expand sequentially, 1.2s apart). On subsequent visits (tab revisit within same session), steps start in expanded state — do not replay the animation unless the user clicks "Replay" (a small text link in the top-right of the step container: `Replay trace`, `font: Inter 12px, color: #6B7280`).

---

### 19.9 Component Additions for the Playground

Add the following to the component file structure from Section 18:

```
src/
  components/
    playground/
      MetricPlayground.tsx           ← root component, owns tab state
      tabs/
        WhatIsAMetric.tsx            ← Tab 1
        MetricHierarchy.tsx          ← Tab 2
        DefineAMetric.tsx            ← Tab 3
        HowAIUsesIt.tsx              ← Tab 4
      shared/
        LayerCard.tsx                ← reusable layer card (Tab 1)
        ConnectingArrow.tsx          ← animated SVG arrow (Tab 1)
        LayerTooltip.tsx             ← info tooltip (Tab 1)
        MetricTreeNode.tsx           ← tree node (Tab 2)
        MetricTreeConnector.tsx      ← SVG connector lines (Tab 2)
        InheritanceDiff.tsx          ← inherited vs override panel (Tab 2)
        SimilarityWarning.tsx        ← deduplication warning (Tab 2)
        PathCard.tsx                 ← card shell for Paths 1/2/3 (Tab 3)
        AISpinner.tsx                ← "Analyzing with Cortex AI..." (Tab 3)
        SynonymTagInput.tsx          ← tag input field (Tab 3, Card 2)
        DiffCodeBlock.tsx            ← before/after LookML diff (Tab 3, Card 3)
        PipelineTraceStep.tsx        ← collapsible trace step (Tab 4)
        ScoreBar.tsx                 ← animated similarity score bar (Tab 4)
        NoEnrichmentCallout.tsx      ← dark callout card (Tab 4)
  mock/
    playground/
      metricLayerData.ts            ← Tab 1 static data
      metricHierarchyData.ts        ← Tab 2 tree data
      defineMetricMocks.ts          ← Tab 3 AI response mocks (A + B variants)
      pipelineTraceData.ts          ← Tab 4 trace steps
```

These components are self-contained — they do not depend on `PipelineContext` or `useSession`. The Playground has its own lightweight state (`MetricPlaygroundContext`) that tracks only: active tab index, active tree node, and per-card expanded/collapsed state.

---

### 19.10 Demo Script Integration

For the Kalyan demo, the Metric Playground is a **secondary stop** — use it if the audience asks "how does it know what things mean?" or if there is time after the main pipeline demo.

**Recommended Playground sequence (90 seconds):**

1. Click "Metric Playground" in the top nav — let the tab transition speak for itself.
2. Land on Tab 1 ("What is a Metric?"). Click Layer 01, then Layer 02, then Layer 03 — pause at the synonyms array. Say: "The data steward added 'total spend' as a synonym. That's the vocabulary bridge."
3. Jump to Tab 4 ("How the AI Uses It"). Click "Trace". Let steps 1–4 animate. Pause at Step 1 to show the 0.96 similarity score. Point to the synonym in the top match.
4. Scroll to the dark callout card. Read the last line: "Without enrichment, Cortex is a very expensive keyword search."
5. Back to main demo.

Tab 2 and Tab 3 are available for follow-up questions about governance and the steward workflow — do not force them into the primary flow.

---

*End of Section 19 — Metric Playground*
