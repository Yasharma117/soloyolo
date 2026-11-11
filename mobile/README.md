# soloyolo app (iOS and Android)

The phone app: **Today** (the 1–3 things that matter now; swipe left when done, right if not needed),
**People**, **All open** and **Sources**. Built with Expo, so the same code runs in the iOS Simulator on
your Mac and on an Android phone.

It shows your real data when it can reach `python -m spike serve` on your Mac, and a demo with made-up
people otherwise. The label at the top of Today says which.

## Run it in the iOS Simulator (on your Mac)

You need Xcode once: install it from the App Store, open it, and let it install the iOS Simulator.

```bash
cd ~/soloyolo/mobile && npm install
```

For your real data, start the server in another terminal (skip this for the demo):

```bash
cd ~/soloyolo && .venv/bin/python -m spike --db ~/.soloyolo/soloyolo.db serve
```

Then:

```bash
cd ~/soloyolo/mobile && npx expo start --ios
```

The Simulator opens with the app. The Simulator shares your Mac's network, so it reaches the server at
`127.0.0.1:8765` directly.

## Run it on your Android phone

Install **Expo Go** from the Play Store. On the Mac, run `npx expo start` in this folder and scan the QR
code with Expo Go (phone and Mac on the same Wi-Fi). The phone can't reach your Mac's server yet (it
only listens on the Mac itself), so it shows the demo. When there's a private route to the Mac
(Tailscale), start with `EXPO_PUBLIC_SOLOYOLO_URL=https://<your-mac>.ts.net npx expo start`.

## Check it

```bash
npx tsc --noEmit
npx expo export --platform ios    # compiles the iOS bundle without Xcode
```
