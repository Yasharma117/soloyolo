# refs/

Reference material the research docs cite. Two kinds:

**Open-source repos (git submodules).** Beeper and mautrix code, fetched with:

```bash
git submodule update --init --depth 1
```

**Mesh (me.sh) material: local only, never committed.** `REPORT.md` cites paths under
`refs/mesh-desktop/`, `refs/mesh-wasm/`, `refs/mesh-web/` and `rea-out/`. Those are
Mesh's closed-source app bundle, native addons, WASM engine and web bundle. They are
copyrighted, so they are git-ignored. To reproduce the teardown on your own machine:

| Path | How to get it |
|---|---|
| `refs/mesh-desktop/` | Download `me.sh/api/download/mac`, mount the DMG read-only, copy `Mesh.app/Contents/Resources/app.asar` and `app.asar.unpacked/`, then `npx @electron/asar extract app.asar x` |
| `refs/mesh-wasm/` | The engine WASM the web app loads from `assets.me.sh/clients/sync-engine/<hash>/mesh-sync-browser.wasm` |
| `refs/mesh-web/` | Save `app.me.sh` and its `index-*.js` bundle from the browser |
| `rea-out/` | Output of `rea analyze-javascript-application` over the above |

Only findings (prose, file:line citations, short quotes) belong in the repo.
