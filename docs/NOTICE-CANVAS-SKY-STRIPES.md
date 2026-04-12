# NOTICE — Canvas Sky RGB 스트라이프 (2026-04-12)

**Reporter:** Designer
**Owner:** FE (render), AI Engineer (atlas 생성)
**Status:** FE 측 1차 수정 완료 — 실측 확인 대기

## 증상

대시보드 `GameCanvas` 상단 하늘 영역에 수직 RGB 스트라이프(얇은 색수차 선)가 **주기적으로** 나타남.

## 근본 원인 분석 (FE 렌더 측)

하늘은 `sky_blue.png` (16×16) 타일을 `COURT_WIDTH/16 = 27`개 × 12행 그리드로 배치함 (`GameCanvas.tsx:261-274`).

1. **PixiJS v8 기본 `scaleMode = 'linear'`** — 바이리니어 샘플링은 포토 텍스처에는 적절하지만 픽셀아트는 텍셀 경계를 흐린다.
2. **devicePixelRatio ≠ 1 + `resolution: dpr` + `autoDensity: true`** — 내부 백버퍼가 비정수 배율(예: 432×1.25=540)로 렌더되면서 GPU가 sub-texel 좌표를 샘플링.
3. **Atlas padding 2px → 0 alpha 영역** — sky_blue 프레임은 `(x=156, y=2, w=16, h=16)`로 우측 2px 공간은 투명. 바이리니어가 이 투명 영역을 타일 우측 edge 로 섞어 반투명 1px 심(seam)을 만듦.
4. **27개 타일 × 16px 간격** = 27개의 수직 심이 정확히 주기적으로 보임. LCD 서브픽셀 렌더링이 이 1px 심을 R/G/B 줄로 증폭.

RL 물리에서 오는 선수/공 좌표(예: `x=123.7`)도 `roundPixels` 미설정 시 같은 sub-pixel 샘플링 유발.

## FE 수정 (커밋 예정)

`frontend/src/components/game/GameCanvas.tsx`

| 항목 | Before | After | 이유 |
|---|---|---|---|
| `antialias` | `true` | `false` | 픽셀아트에 canvas edge 안티얼라이싱 불필요 + 1px fringing 유발 |
| `roundPixels` | (미설정) | `true` | 분수 좌표 스프라이트를 정수 픽셀에 스냅 |
| 텍스처 `scaleMode` | 기본 `linear` | `nearest` (Assets.load 직후 shared source 에 지정) | 픽셀아트 무보간 샘플링 강제 |

구현:
```ts
// app.init({ antialias: false, roundPixels: true, ... })
const sharedSource = Object.values(textures)[0]?.source
if (sharedSource) sharedSource.scaleMode = 'nearest'
```

스프라이트시트는 단일 `TextureSource` 를 공유하므로 한 줄이 28 pikachu + 6 ball + 10 number + 기타 objects 전부 커버.

## AI Engineer 협업 필요 여부

**현재 atlas 는 frame 간 2px padding 이 이미 들어가 있음** (`sprite_sheet.json` 확인: sky_blue x=156..172, 우측 다음 엔트리 x=174+). NEAREST 강제로 충분할 것으로 예상 — atlas regeneration **불필요**.

단, FE 수정 후 실측에서 다음 중 하나가 남아 있다면 atlas 쪽 이슈로 넘김:

1. 특정 스프라이트 edge 에서 여전히 1px 인접 프레임 색이 섞임 → padding 부족 또는 bleed 마진(extrude) 필요
2. AnimatedSprite 프레임 전환 순간에 플릭커 → TexturePacker `extrude=2` 재생성 요청

## 검증 방법

1. FE 수정 배포 후 designer 가 대시보드 캔버스 시각 확인 (여러 DPR: 1.0, 1.25, 1.5, 2.0)
2. 스트라이프 완전 소거면 완료. 잔여 아티팩트 있으면 AI Engineer 에게 atlas 재생성 요청.

## 테스트

- PixiJS 내부 렌더링은 단위 테스트로 검증 곤란 (jsdom WebGL 미지원). 시각 회귀는 designer 실측으로 커버.
- `tsc --noEmit` / ESLint / Vitest 195개 전부 green 상태로 수정.
