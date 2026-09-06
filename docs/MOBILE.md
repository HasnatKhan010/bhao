# Bhao mobile — the Play Store runbook

The mobile app is a **Capacitor shell around the same Next.js app** — one codebase,
the full bilingual RTL UI, the API called over the public internet. No second
framework, no duplicated logic.

## Architecture

```
web/ (Next.js)  ──STATIC_EXPORT=1──▶  web/out/  ──cap sync──▶  android/app  ──gradle──▶  AAB
                                                                      │
                                                      app loads the UI from the bundle,
                                                      prices/forecasts from the public API
```

The deployed web stays dynamic (`standalone`); only the mobile bundle is exported
statically. The app inside Android loads `out/` from the device and calls the API
directly, so a broken web deployment never breaks installed apps.

## One-time setup (done)

- `capacitor.config.ts` — appId `pk.bhao.app`, appName `Bhao`, webDir `out`
- `npm run build:static` — `STATIC_EXPORT=1 next build` (exports every route incl.
  `/en`/`/ur`, all 17 city pages, all 57 item-code pages)
- `npx cap add android` — the `android/` project is committed (Capacitor convention)

## Every release

```bash
cd web
NEXT_PUBLIC_BHAO_API_URL=https://<deployed-api-host> npm run build:static
npx cap sync android
cd android && ./gradlew bundleRelease        # → app/build/outputs/bundle/release/app-release.aab
```

**`NEXT_PUBLIC_BHAO_API_URL` is baked in at build time** — set it to the deployed
API host (e.g. `https://bhao-api.fly.dev`). The bundled app has no localhost.

## Play Store checklist

1. **Signing**: create an upload keystore once, keep it out of git
   (`android/keystore/` is gitignored), configure `signingConfigs` in
   `android/app/build.gradle`.
2. **Privacy policy URL**: live at `/en/privacy` and `/ur/privacy` on the deployed
   site — Play requires a working URL. The page states plainly that the app
   collects nothing.
3. **Data Safety form**: "No data collected, no data shared" — accurate, because
   the app has no accounts, analytics, or tracking.
4. **Content rating**: questionnaire; expected "Everyone" (prices and charts).
5. **Target API level**: set `compileSdkVersion`/`targetSdkVersion` in
   `android/variables.gradle` to the level Play currently requires (API 34+).
6. **App name/description**: bilingual (English + Urdu) — a differentiator on the
   Store too.
7. **Internal testing track first**: upload the AAB, opt in with a tester list,
   then promote to production.
8. **New release cadence**: the panel updates weekly; a release every few weeks is
   plenty (the app renders whatever the API serves — staleness is handled by the
   API's own `panel_week` display and healthcheck).

## Screenshots for the listing

Capture from the running app: the home forecast card (English), the Urdu RTL home,
and the scorecard. Real data only — the fixture banner must never appear in store
assets.
