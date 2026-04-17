# Port(assets) Post-Merge Checklist

Run after AI Engineer's `port(assets)` commit lands.

## 1. File presence

- [ ] `sprite_sheet.png` + `.json` hashes unchanged; 7× `WAVE14[0-6]_1.wav` + `bgm.mp3` hashes match
- [ ] Favicons / PWA icons added if in scope

## 2. Atlas parsing (PixiJS)

- [ ] `Assets.load('sprite_sheet.json')` resolves without error
- [ ] Spot-check keys: `ball/ball_0..4`, `ball/ball_hyper|trail|punch`, `pikachu/pikachu_0_0..6_4` (28), `objects/cloud|wave|mountain|net_pillar|shadow`, `number/number_0..9`, `messages/common/ready|game_end`
- [ ] No "missing frame" console warnings on first render

## 3. Sprite alignment

- [ ] Pikachu anchor (0.5,0.5); shadow at y=273
- [ ] Ball anchor (0.5,0.5); 5-frame rotation cycles
- [ ] Net pillar stack x=213, y=176→272 contiguous
- [ ] Ground tiles tile cleanly on 16px grid at y=248/264/280/296
- [ ] Player 2 `scale.x=-1` mirror correct on dive

## 4. Sound playback

- [ ] BGM loops seamlessly, volume ≈0.2; POWERHIT + BALLTOUCHESGROUND trigger on correct events, no clipping
- [ ] Vocals not stacking chaotically; mute toggle fully silences

## 5. Regression

- [ ] D11–D15 canvas FX composite over ported sprites; `SPRITE_GUIDE.md` mapping still accurate
