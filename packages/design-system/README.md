# soloyolo design system

`@soloyolo/design-system`: the tokens, components and blocks every soloyolo screen is built from. React Native,
so one system serves iOS, Android and the web build. The app imports from here and nowhere else for its look;
lint fails the build when a screen goes around it.

Open the live catalog in the app: **Sources → Design system** (`/design`), in light or dark.

---

## What soloyolo is

A phone app that reads your chats (WhatsApp first; LinkedIn, Instagram and X from their exports) and each morning
shows the 1–3 things you said you'd do, or are waiting on, that matter today. Anything quiet for a few days is
assumed done. It is a nudge, not a backlog.

## Voice

Plain, warm, specific. The app talks like a friend who remembers, not a task manager.

- **Say the promise as a sentence.** "You said you'd send Rohan the rent agreement scan", "Waiting on Priya to
  share the hiring manager's email". Never "Task: rent agreement".
- **Second person** for you, first names for them. No "we".
- **Sentence case** everywhere; uppercase only in small spaced section labels.
- **Numbers as words** in the greeting ("three things"), as digits everywhere else.
- **Empty states say what's missing and what happens next.** "Nothing you said you'd do needs you today. Older
  things are assumed done, unless someone chases you about them."
- **Errors say what to do.** "Couldn't save that. Is soloyolo running on your Mac?"
- **No emoji** in the interface. They appear only inside quoted messages, as people wrote them.
- **Hinglish stays as written** in quotes. Don't translate people.

## Visual foundations

From the references the design was built on (Mobbin: Mesh, HEY, Atoms, Joi):

- **Paper, not white.** The page is warm paper (`background`); white is for cards on it (`surface`). Dark mode is
  warm near-black, not blue-black.
- **One accent: marigold.** It marks what's urgent (a due date, someone chasing) and underlines the owed words in a
  sentence. Never decoration. Green means Done, violet means Still on, stone means Not needed, each only on its
  swipe action.
- **Two faces.** The platform sans for everything in the interface. A serif only for promise sentences
  (`sentence`, `sentenceSmall`): it makes the promise read like something a person said.
- **Hierarchy from size and weight**, one step at a time: display (the date), title (a screen), heading (the
  greeting), body, small, caption, label.
- **Space on a 4-point grid** (`space.*`). Gaps between siblings come from the parent's `gap`, never from margins.
- **Radius grows with the object:** 6 small chips, 10–14 fields and groups, 18 piles, 22 cards, pill for buttons and
  the tab bar.
- **Shadows are soft and warm** and only on things that float: cards (`shadow.card`) and the tab bar
  (`shadow.floating`). Lists sit flat on the paper with hairline dividers.
- **People are gradient orbs** with initials, two hues picked from the name, so a person always looks the same.
- **Texture once:** the dot grid behind Today's header, fading out. Nowhere else.
- **Motion is quick and calm:** 160ms toasts, 220ms leaving cards, 400ms sheets. No bounce. Swipes follow the
  finger 1:1 and confirm with a light haptic.

## Layers

```
src/
  tokens/      palette (raw) → semantic colors per theme, type scale, space, radius, shadow, motion, icon sizes
  theme/       ThemeProvider + useTheme(): follows the device, or pinned (the catalog pins it)
  components/  the parts: Text, Stack/Row, Surface, Divider, Icon, Button/IconButton, Chip/ReasonChips, Badge,
               Avatar/Facepile, SearchField, Tabs, SectionLabel, ListRow, EmptyState, Skeleton, DotGrid,
               Toast (provider + useToast), SwipeRow
  blocks/      whole patterns, imported as they are: TodayHeader, PromiseCard, PromiseRow, PromiseSentence,
               PersonRow, QuietPile, PageTitle, PersonHeader, TimelineEvent, SourceRow, FloatingTabBar
  index.ts     the only import path: import { PromiseCard, useTheme } from '@soloyolo/design-system'
```

**Use a block if one fits, compose components if not, add a component if neither.** A screen that hand-builds a
card, a row or a tab bar is a bug.

## Rules the build enforces

`npx expo lint` in `mobile/` (CI runs it) fails when a screen in `src/app/`:

- imports `Text`, `TextInput`, `Pressable`, `Touchable*`, `Button` or `Switch` from `react-native`
- imports icons, gradients or the swipeable directly
- imports from inside the package (`@soloyolo/design-system/src/...`)
- writes a hex or rgba color, or sets `fontFamily`

`npm run check -w @soloyolo/design-system` fails when any color is written outside `src/tokens`.

## Adding to it

1. Need a color, size or font? Add a **token** (semantic name for what it's for), in both themes.
2. Need a new part? Add a folder under `components/` with `Name.tsx` and `index.ts`, export it from `src/index.ts`,
   and add it to the catalog (`mobile/src/app/design.tsx`).
3. Need a new screen pattern twice? Make it a **block**.
4. Check light and dark in the catalog, then `npx tsc --noEmit` and `npx expo lint` in `mobile/`.

See `COMPONENT_PLAN.md` for what exists and what comes next.
