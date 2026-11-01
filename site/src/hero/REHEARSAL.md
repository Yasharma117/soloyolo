# Rehearsal: soloyolo hero

Gold: `hero-demo` for the corner-bleed frame and pacing; `static-card` for a satellite straddling the sidebar.
Kept: the 720 × 340 stage, 32px gutter, window running off the right and bottom, named targets, poster on the payoff.
Changed: soloyolo's own tokens (warm greys, near-black ink, orange accent), a sidebar app window, and the
evidence card in Messages' own blue, because it is a real iMessage.

Beats: 1 click the overdue promise → its source message comes forward · 2 Draft intro → the draft streams in ·
3 Send → the button confirms on itself, the check fills, "9d overdue" rolls to "Done" · payoff holds 2.2s ·
reset: the kept promise leaves "You owe" and the next one drops in. Loop ≈ 10s.

Captured: widths 1280 (wide) and 390 (compact 358 × 356), light theme, poster (reduced motion), the send beat and the reset at 60–70ms.

Film:
- `film.mjs --gate` on the playground capture route: **rehearsal passed** at 1280 and 390.
- Same on this site's dev server: **rehearsal passed** at both widths.
- Production build (`vite preview`): 6 `kit override` lines name `.ss-phone__*` rules. This demo has no phone CSS;
  they are the kit's own `phone.css` rules after Vite merged its 42 `@layer stageshow` blocks into one file. Stands as a
  detector artifact; dev, where files are separate, is clean.
- Fixed along the way: promise card cut by the crop (400 → 344px), "Done" in the wrong color, uneven satellite padding,
  compact window narrower than tall, an empty pane during the compact reset, two "lands on a transform" hops (`will-change`).
- Stands: a `jump` warning at the reset is the kit's `Collapse reveal="drop"` closing; frame by frame it reads as the card leaving.

Assumptions: the page is light; the demo sits beside copy, so corner bleed.
Unresolved: the compact source bubble wraps to two lines with air on its left (Messages' right-aligned sent bubble).
Not checked: dark theme (the site is light-only), `--states`, and the skill's fresh-eye review by a separate reviewer,
which was not run in this session.
