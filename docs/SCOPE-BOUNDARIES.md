# Designer ↔ Frontend Engineer Scope Boundaries

## Problem
Designer와 Frontend Engineer가 같은 `.tsx` 파일을 수정하면 merge conflict 발생.

## Rule: 파일 소유권 분리

### Designer 소유 파일 (CSS/스타일만)
```
frontend/src/styles/**          # 디자인 토큰, 글로벌 스타일
frontend/src/components/**/*.css # 모든 컴포넌트 CSS 파일
frontend/src/assets/**           # 아이콘, 이미지
frontend/index.html              # 폰트 링크, 메타태그만
```

### Frontend Engineer 소유 파일 (로직/마크업)
```
frontend/src/components/**/*.tsx # 모든 컴포넌트 로직
frontend/src/hooks/**            # React hooks
frontend/src/lib/**              # 유틸리티, API 클라이언트
frontend/src/App.tsx             # 라우터, 레이아웃
frontend/src/main.tsx            # 엔트리포인트
frontend/vite.config.ts          # 빌드 설정
frontend/package.json            # 의존성
```

## 협업 프로토콜

### Designer가 컴포넌트 스타일을 변경할 때
1. **CSS 파일만 수정** — `.css` 파일에서 클래스, 변수, 레이아웃 변경
2. **TSX에 className 추가 필요 시** → Frontend Engineer에게 요청하거나 PM이 조율
3. **절대로 `.tsx` 파일 직접 수정하지 말 것**

### Frontend Engineer가 새 컴포넌트를 만들 때
1. `.tsx` 파일 생성 + `import './ComponentName.css'` 포함
2. 기본 className 부여 (예: `className="dashboard"`, `className="metrics-chart"`)
3. Designer가 해당 `.css` 파일에서 스타일 작업

### 공유 파일 수정 필요 시
- `index.html`: Designer는 `<link>` 태그만, Frontend는 `<script>` 태그만
- 둘 다 수정 필요 → PM에게 알려서 순차 작업 조율
