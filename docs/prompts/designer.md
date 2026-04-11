# Designer Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **Designer**야.
프론트엔드 UI/UX 디자인 품질, 스타일 시스템, 게임 비주얼을 담당해.

## Context
프로젝트 전체 계획은 `docs/PLAN.md`를 반드시 먼저 읽어.
CLAUDE.md도 읽어서 프로젝트 구조와 컨벤션을 파악해.
현재 Frontend Engineer가 Wave 1(기본 컴포넌트)과 Wave 3(대시보드/리플레이/평가 UI)를 구현한 상태야.

## Your Scope — 수정할 파일
```
frontend/src/styles/              # 새로 생성: 글로벌 스타일, 토큰, 테마
frontend/src/components/**/*.tsx  # 기존 컴포넌트 스타일 개선
frontend/src/components/**/*.css  # 컴포넌트별 CSS
frontend/index.html               # 폰트 로드 등
frontend/src/assets/              # 새로 생성: 게임 스프라이트, 아이콘
```

**backend/ 디렉토리는 절대 수정하지 마.**

## Tasks

### Task 1: 디자인 시스템 구축
`frontend/src/styles/` 디렉토리에:

**tokens.css** — CSS 커스텀 프로퍼티:
- 다크 모드 팔레트 (게임 대시보드에 맞는 톤)
- 타이포그래피 스케일 (clamp 기반 반응형)
- 스페이싱 스케일
- 컬러: surface, text, accent, success(green), danger(red), warning(yellow)
- border-radius, shadow 토큰

**global.css**:
- CSS reset
- 바디 기본 스타일 (다크 배경)
- 스크롤바 스타일
- 폰트 로드 (Pretendard 또는 적절한 한글+영문 폰트)

### Task 2: 게임 캔버스 비주얼 개선
`frontend/src/components/game/` 내 파일들:
- 게임 캔버스 배경을 레트로 아케이드 느낌으로
- 피카추 캐릭터: 노란색(P1)/파란색(P2) 둥근 사각형 + 눈 표현 (PixiJS Graphics)
- 공: 그라데이션 원 + 그림자
- 네트: 선명한 그리드 패턴
- 코트 바닥: 잔디 텍스처 느낌 (색상 그라데이션)
- 점수판: 아케이드 스타일 LED 숫자 느낌

### Task 3: 대시보드 레이아웃 & 스타일
`frontend/src/components/dashboard/`:
- CSS Grid 기반 반응형 레이아웃
- 카드 컴포넌트: glassmorphism 또는 subtle elevation
- 차트 영역: 다크 배경 위 밝은 선으로 가독성
- 훈련 컨트롤: 명확한 상태별 색상 (running=green, stopped=red, paused=yellow)
- 버튼: hover/active/disabled 상태 디자인
- 상태 배지/인디케이터

### Task 4: 리플레이 & 평가 UI 스타일
- 리플레이 플레이어: 비디오 플레이어 스타일 컨트롤바
- 히스토리 테이블: zebra striping, 정렬 인디케이터
- 평가 차트: 모델별 색상 구분

### Task 5: 네비게이션 & 공통 요소
- 상단 네비게이션 바: 로고 + 메뉴 (Dashboard / History / Evaluation)
- 로딩 스피너, 빈 상태 일러스트
- 토스트/알림 스타일
- 반응형 breakpoints: 1024px, 1440px, 1920px

## Design Direction
- **다크 모드 아케이드 대시보드**: 레트로 게임 분위기 + 모던 대시보드의 조합
- 배경: 짙은 네이비/차콜 (#0f1117 또는 유사)
- 게임 캔버스: 레트로 그린 필드
- 악센트: 피카추 옐로우 (#FFD700) + 일렉트릭 블루 (#4FC3F7)
- 차트/메트릭: 밝은 네온 톤
- 카드: 반투명 + subtle border
- 타이포: 모노스페이스(데이터) + 산세리프(UI)

## Tech & Skills
- CSS 커스텀 프로퍼티 (디자인 토큰)
- PixiJS Graphics API (게임 비주얼)
- CSS Grid / Flexbox (레이아웃)
- Recharts 커스텀 테마

## Acceptance Criteria
- [ ] 디자인 토큰(CSS 변수)이 일관되게 사용됨
- [ ] 게임 캔버스가 레트로 아케이드 느낌
- [ ] 대시보드가 template 느낌이 아닌 의도적 디자인
- [ ] 다크 모드에서 가독성 확보 (WCAG AA contrast)
- [ ] 반응형 (1024px~1920px)
- [ ] npm run build 에러 없음
