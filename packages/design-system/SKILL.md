---
name: soloyolo-design
description: Use when building or changing any soloyolo screen or UI (the Expo app in mobile/). Covers the design system's tokens, components, blocks, voice and the lint rules every screen must pass.
---

Read `packages/design-system/README.md` first. Then:

1. **Find the block.** Screens are composed from `src/blocks`: a new screen starts from `Screen`, results use
   `StatusScreen`, and the rest (TodayHeader, PromiseCard, PromiseRow, PersonRow, QuietPile, PageTitle,
   PersonHeader, TimelineEvent, SourceRow, FloatingTabBar) are used as they are when they fit. Add the route to `/screens`.
2. **Else compose components** from `src/components`. Layout with `Stack`/`Row` and `gap`; text only through
   `<Text variant tone>`; colors only through `useTheme().color`.
3. **Else add to the system**: a token, a component or a block, in the package, with a catalog entry in
   `mobile/src/app/design.tsx`. Never style around it inside a screen.
4. **Write like the voice section and its per-component table**: promises as sentences, sentence case, destructive
   buttons repeat the object, toasts are object + state, errors name the next step, no dashes or exclamation marks.
5. **Verify**: `npx tsc --noEmit` and `npx expo lint` in `mobile/`, `npm run check -w @soloyolo/design-system` at
   the root, and look at both themes in the catalog (Sources → Design system).

Quick reference: background `paper`, cards `surface`, one accent `marigold` (urgent + the owed words), Done `success`,
Still on `later`, Not needed `neutralAction`. Serif only for promise sentences. Radius 22 cards, pill buttons.
