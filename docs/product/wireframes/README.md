# Wireframes and tokens sheet

`tokens-sheet.png` is a rendered preview only. `design/tokens.json` is the source of truth for every token value;
if the two differ, the JSON wins and the PNG is stale.

Re-render it (lossless, truecolour, no palette quantisation; the file must stay at or below 1 MB, `scripts/guards.sh` check 5):

1. Serve the repository root: `python3 -m http.server 8765`. The page loads Roboto and Material Symbols from Google Fonts, so the browser needs network access to fonts.googleapis.com and fonts.gstatic.com; without it the render will not match.
2. Open `http://localhost:8765/docs/product/wireframes/wireframes.html?screen=tokens` in Chromium with a viewport
   1180 CSS px wide, device scale factor 1, and take a full-page screenshot as PNG (Playwright:
   `chromium.launch()`, `newPage({ viewport: { width: 1180, height: 800 }, deviceScaleFactor: 1 })`,
   `screenshot({ path: 'docs/product/wireframes/tokens-sheet.png', fullPage: true })`).
3. Optional: lossless recompression only (maximum zlib level); never reduce colours.

The per-screen PNGs (`01-...` to `33-...`) come from the same page with `?screen=05&theme=dark` and similar.
