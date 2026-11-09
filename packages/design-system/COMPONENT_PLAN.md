# Component plan

What exists, and what to build next, in the order screens will need it.

## Built (v0.1)

| Layer | Parts |
|---|---|
| Tokens | palette, semantic colors (light, dark), orbs, type scale (11 steps), space, radius, shadow, motion, icon sizes |
| Theme | `ThemeProvider` (device or pinned), `useTheme()` |
| Components | Text · Stack/Row · Surface (card, outline, raised, dashed) · Divider · Icon (allow-list) + NetworkIcon · Button (primary, secondary, ghost, danger; sm, md; icon; loading) · IconButton · Chip · ReasonChips · Badge · Avatar (xs–xl) · Facepile · SearchField · Tabs · SectionLabel · ListRow · EmptyState · Skeleton · DotGrid · Toast + useToast · SwipeRow |
| Blocks | TodayHeader · PromiseCard · PromiseRow · PromiseSentence · PersonRow · QuietPile · PageTitle · PersonHeader · TimelineEvent · SourceRow · FloatingTabBar |
| From Markon (v0.2) | Screen · StatusScreen · ReasonSheet (from its confirm-with-reason dialog, made optional and after the fact) · BottomSheet (88% cap, scrolling body, close button, fixed footer) · ConfirmDialog (grows from 95%) · Banner · Chip tones · SectionCard · KeyValueList · NavRow/NavList · StepHeader · FadeIn · Stagger · CountUp · Loader · format helpers · `/screens` and `?tone=` state routes · writing rules. Rebuilt from Markon's docs for React Native; no Markon or Untitled UI code copied (its PRO components are licensed to Markon's owner) |
| From Markon (v0.3, read from its source) | StatusBadge + STATUS + statusOf (status-badge's single vocabulary) · ChipGroup (chip-group) · OptionList with a suggested pick (option-radio-group) · StatTile/StatRow (stat-tile) · ReviewStrip (review-banner) · InlineError (inline-error) · NavRow lead/description/trailing and KeyValueList emphasis (list.tsx) · TimelineEvent rail and bubble (activity-feed) · FloatingTabBar rebuilt as Markon's floating dock (app-shell/bottom-nav: full-width glass dock, soft pill that slides and stretches, label folds, icon pops, reduced motion respected) · Screen chrome from app-shell/screen.tsx: Wash (warm tint fading out by a quarter screen), TopBar that is clear at rest and fills with the title once content scrolls under it, close/back pinned in it · CardSkeleton/RowSkeleton with a breathing Skeleton · `?state=empty|error|loading` previews from page-state, listed in /screens. Rebuilt for React Native on our tokens; no web code carried over |
| From the Atoms redesign (Figma, v2) | CheckInCard: the "Is Read 10 pages still working for you?" check-in as Today's Still on? deck for quiet promises, with the stacked cards behind · Button `warm` (amber gradient pill, dark text) and `soft` · tokens wash/warmFrom/warmTo/onWarm |
| Gates | lint rules for screens (`mobile/eslint.config.js`), color check for the package (`scripts/check.mjs`), both in CI |

## Next

### Tier 1: needed by the next features
| Part | Why |
|---|---|
| **Menu / action sheet** | Long-press on a card: Done, Not needed, Later, Open chat |
| **Toggle** | Settings: morning time, which sources count |
| **TextField** | Notes on a person, renaming |
| **SegmentedControl** | Today / This week |
| **Skeletons per block** | PromiseCard and PersonRow while loading |

### Tier 2: blocks for screens not built yet
| Block | Screen |
|---|---|
| **OnboardingStep** | First run: link WhatsApp, pair Telegram, import exports |
| **ImportProgress** | An export being read: counts, what was skipped |
| **MergeSuggestion** | Identity: "Are these the same person?" with Yes / No |
| **EdgeRow** | "Sonu → forwarding your profile to Saurabh at Razorpay" |
| **WeekReview** | Sunday: what got done, what went quiet |

### Tier 3: polish
Skeleton states per block · reduced-motion variants · haptics map · Dynamic Type sizing · right-to-left check

## Not doing
- A second accent color. Status colors live only on their swipe actions.
- Custom fonts. The platform faces load instantly and look native; the serif is the platform's own.
- Illustrations. Orbs and the dot grid are the only decoration.
