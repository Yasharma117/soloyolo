# Component plan

What exists, and what to build next, in the order screens will need it.

## Built (v0.1)

| Layer | Parts |
|---|---|
| Tokens | palette, semantic colors (light, dark), orbs, type scale (11 steps), space, radius, shadow, motion, icon sizes |
| Theme | `ThemeProvider` (device or pinned), `useTheme()` |
| Components | Text · Stack/Row · Surface (card, outline, raised, dashed) · Divider · Icon (allow-list) + NetworkIcon · Button (primary, secondary, ghost, danger; sm, md; icon; loading) · IconButton · Chip · ReasonChips · Badge · Avatar (xs–xl) · Facepile · SearchField · Tabs · SectionLabel · ListRow · EmptyState · Skeleton · DotGrid · Toast + useToast · SwipeRow |
| Blocks | TodayHeader · PromiseCard · PromiseRow · PromiseSentence · PersonRow · QuietPile · PageTitle · PersonHeader · TimelineEvent · SourceRow · FloatingTabBar |
| Gates | lint rules for screens (`mobile/eslint.config.js`), color check for the package (`scripts/check.mjs`), both in CI |

## Next

### Tier 1: needed by the next features
| Part | Why |
|---|---|
| **Sheet** (bottom sheet) | Snooze picker, "why is this here", Telegram pairing |
| **Menu / action sheet** | Long-press on a card: Done, Not needed, Later, Open chat |
| **Toggle** | Settings: morning time, which sources count |
| **TextField** | Notes on a person, renaming |
| **SegmentedControl** | Today / This week |
| **Banner** | "Sync stopped 12h ago" at the top of Today |

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
