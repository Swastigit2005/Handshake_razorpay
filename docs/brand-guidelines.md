# Handshake Brand Guidelines v1.0

> Last updated: 2 September 2026  
> Status: Production candidate

## Quick Reference

| Element | Value |
|---|---|
| Brand concept | Controlled Momentum |
| Primary Color | #305EFF |
| Secondary Color | #080D29 |
| Accent Color | #48D08C |
| Heading and body font | Inter Tight |
| Technical font | Fragment Mono |
| Voice | Precise, candid, controlled, quietly confident |

## 1. Brand idea

Handshake is the control layer between an agent checkout failure and a merchant's
money. Its visual character should combine forward motion with visible restraint:
the system acts quickly, while the policy gate remains deterministic and legible.

**Positioning:** Handshake is the revenue-recovery layer for merchants serving AI
buyers. It detects dead checkout sessions, diagnoses the machine-readable cause,
gates one repair through deterministic policy, and proves the outcome in rupees.

**Primary message:** You can't email a bot a coupon.

**Supporting messages:**

- Recover the buyer you cannot contact.
- A model may propose a cause; only deterministic policy decides whether money moves.
- Measure against a randomised control, never against zero.
- Fix catalogue defects once instead of recovering the same failure forever.

## 2. Visual identity

### Primary Colors

| Name | Hex | RGB | Usage |
|---|---|---|---|
| Rail Blue | #305EFF | rgb(48, 94, 255) | Primary actions, active states, stage progress |
| Rail Blue Dark | #2950DA | rgb(41, 80, 218) | Hover and pressed states |
| Rail Blue Light | #75A3FF | rgb(117, 163, 255) | Dark-surface highlights and diagrams |

### Secondary Colors

| Name | Hex | RGB | Usage |
|---|---|---|---|
| Ledger Navy | #080D29 | rgb(8, 13, 41) | Hero, navigation, control-room surfaces |
| Slate | #192839 | rgb(25, 40, 57) | Primary light-mode text |
| Rail Slate | #768EA7 | rgb(118, 142, 167) | Decorative lines and dark-surface labels |

### Accent Colors

| Name | Hex | RGB | Usage |
|---|---|---|---|
| Recovered Green | #48D08C | rgb(72, 208, 140) | Recovered money and verified success only |
| Refusal Red | #F0263C | rgb(240, 38, 60) | Binding policy refusals and destructive state |
| Review Amber | #FF8C1A | rgb(255, 140, 26) | Caveats, simulation, and attention states |

### Neutral Palette

| Name | Hex | Usage |
|---|---|---|
| Paper | #FFFFFF | Primary light surface |
| Canvas | #F8FAFC | Light page background |
| Recessed | #F1F5FA | Secondary surfaces and table headers |
| Rule | #DFE3E9 | Borders and dividers |
| Accessible Muted | #596F88 | Small labels and captions on white or recessed surfaces |

### Color behavior

- Blue means navigation, progress, or an available action.
- Green means money demonstrably recovered or a chain demonstrably verified.
- Red means a policy bound stopped an action; it never means generic decoration.
- Amber means the reader must understand a caveat before trusting a number.
- Never rely on color alone: every state also has a label, value, or icon.

## 3. Typography

```css
--font-heading: 'Inter Tight', system-ui, sans-serif;
--font-body: 'Inter Tight', system-ui, sans-serif;
--font-mono: 'Fragment Mono', ui-monospace, monospace;
```

- Landing display: 40-74px, 700 weight, 1.01 line height.
- Landing section heading: 29-46px, 700 weight, 1.07 line height.
- Body: 16-18px, 400 weight, 1.55-1.65 line height, maximum 62-74ch.
- Console heading: compact 14-20px, 600-700 weight.
- Evidence, identifiers, API traces, and labels: Fragment Mono at 10-13px.
- Sentence case is the default. All caps is reserved for short machine labels.

## 4. Logo

The mark depicts two halves of a transaction meeting across a shared boundary:
Razorpay blue for detection and execution, recovered green for the successful return.

- Use the full horizontal lockup in website headers at 120px or wider.
- Use the mark alone no smaller than 24px.
- Keep one mark-width of clear space around standalone uses.
- Do not rotate, stretch, shadow, recolor, or place the mark on a noisy image.
- Razorpay's logo is not incorporated. The color relationship signals ecosystem fit
  without suggesting endorsement or ownership.

## 5. Motion and data graphics

Motion explains cause and effect. It is not confetti.

- Animate the seven-stage recovery sequence in reading order.
- Reveal measured values by counting toward the stored result; always settle on the
  exact value even if a tab is throttled.
- Use 180-300ms for controls, 500-900ms for explanatory transitions.
- Pointer light and shallow perspective may communicate depth on desktop.
- Touch feedback is immediate and small. No scroll-jacking or cursor replacement.
- Respect `prefers-reduced-motion`; all information remains present without animation.
- Charts use direct labels and Indian-number formatting. Avoid decorative 3D charts.

## 6. Imagery

The product is an invisible protocol layer, so its most authentic imagery is its own
evidence: API traces, policy decisions, audit hashes, before/after bars, and recovery
flows. Generic stock photography and AI-generated people make the product feel less
credible and are not used in the application.

If campaign art is required, use abstract transaction rails: deep navy field,
electric-blue paths, recovered-green terminal node, sparse grid, subtle volumetric
light, no coins, cards, robots, handshakes, dashboards, or human faces.

## 7. Voice and tone

### Brand Personality

| Trait | Description |
|---|---|
| **Precise** | Claims include a denominator, control, or mechanism. |
| **Candid** | Limitations appear with the results, not behind a footnote. |
| **Controlled** | Money movement is framed through permission, bounds, and reversibility. |
| **Quietly confident** | Strong findings stand on evidence rather than superlatives. |

### We say

- "Recovered ₹3,50,019 in a seeded 500-session experiment."
- "R-10 refused the action because confidence was below 0.70."
- "Same buyers, same seed, only the feed differs."

### We do not say

- "Revolutionary AI that eliminates abandonment."
- "Guaranteed revenue." 
- "Seamless, best-in-class, game-changing, or magical."
- Anything implying production readiness, real-market validation, or Razorpay endorsement.

## 8. Component language

- Primary buttons: Rail Blue, white text, 40-48px pill, explicit verb.
- Cards: 16px radius, one-pixel border, shallow shadow; elevation changes by at most 3px.
- Inputs: 8-10px radius, visible focus ring, persistent label.
- Tables: neutral surface, direct labels, right-aligned numeric columns.
- Status chips: pill-shaped, mono text, semantic color plus written state.

## 9. Accessibility and quality bar

- Text contrast meets WCAG 2.1 AA: 4.5:1 for normal text and 3:1 for large text.
- Every interactive element is keyboard reachable with a visible focus state.
- Minimum body size is 16px on marketing pages and 14px on dense console rows.
- Layouts are verified at 390px, 768px, 1440px, and keyboard-only navigation.
- The dark and light console themes preserve the same semantic hierarchy.

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-09-02 | Initial identity, messaging, motion, and component system |
