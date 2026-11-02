# site

soloyolo's landing hero: an animated product demo built with the Stageshow skill (`.claude/skills/stageshow`).
The demo is faux UI: it illustrates the product, it is not the product. The real UI is `spike/viewer.html`.

```bash
cd site && npm install && npm run dev
```

```bash
npm run build
```

- `src/hero/SoloyoloHero.tsx`: the scene and its script. `REHEARSAL.md` beside it records what was filmed and checked.
- `src/kit/`: Stageshow's React kit, copied in as the skill intends (MIT, see `src/kit/LICENSE`; brand artwork
  sources are listed in `src/kit/brands/SOURCES.md`).

To iterate with the skill's playground and filming tools, copy `src/hero/` to
`.claude/skills/stageshow/examples/soloyolo-hero/` (change the kit import back to `../../kit`), run `npm run dev`
there, and film `?capture=soloyolo-hero` with `scripts/film.mjs --gate` at 1280 and 390.
