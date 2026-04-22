# 제안서 — MineRL Diamond 차기 프로젝트

**작성일**: 2026-04-23 · **작성자**: PM · **상태**: Proposal · **기간**: 12주 (2026-04-27 ~ 2026-07-19)

## 1. 프로젝트 개요

차기 프로젝트로 **MineRL Diamond** (NeurIPS MineRL Competition 파생) 을 선정한다. Pika v2.0.0 이 (a) 2D 저차원 observation + (b) discrete-action + (c) 단일 엔진 재현 문제로 닫혔다면, MineRL 은 (a) **64×64 RGB 3D observation** + (b) **long-horizon sparse reward (diamond 도달까지 ~6000+ step)** + (c) **material curriculum** 세 축을 동시에 요구해 v2 의 Dreamer V3 세팅을 실전 테스트하기에 적합하다. **기대 결과**: Pika 에서 검증한 알고리즘 매트릭스(PPO/SAC/Dreamer)를 3D sparse-reward 환경에 투입해 diamond 도달률 ≥30% 달성 + 한국어 콘텐츠 시리즈 자산화.

## 2. 시장/타겟 분석

- **한국 Minecraft 유저풀**: 2025 공식 Java/Bedrock 합산 MAU 약 180 만명 추정, 초·중 연령대 60% 이상. 교육용 Minecraft Education 도입 학교 1,200 개 (교육부 2024 집계) — **"AI 가 마크 플레이" 서사의 타겟 친화도 매우 높음**.
- **글로벌 RL 연구 커뮤니티**: NeurIPS MineRL Diamond Competition (2019~2021) 이후 Dreamer V3 논문이 baseline 을 ~2~3배로 끌어올린 사례 공개. 최신 leaderboard 상위권은 대부분 institutional lab. **개인 솔로 + Dreamer V3 재현으로 "SOTA 재현 가능성" 자체가 컨텐츠 포인트**.
- **영상 콘텐츠 생태계 (한국 마크 유튜버 벤치)**: 도티(약 280 만), 잠뜰TV(약 220 만), 양띵(약 160 만) 등 상위 채널 평균 회당 10~40만 조회. **"AI 가 대신 마크 플레이" 영상은 국내에서 아직 희소** — 참고: 양띠로그 "봇이 마크" 영상 3편 평균 12 만뷰, 외국어 채널 "Neural MMO" 류 영상 평균 조회수 50k 이상.

## 3. 목표 정의 (SMART)

- **기술 목표**: Dreamer V3 + CNN encoder 로 `MineRLObtainDiamondShovel-v0` 환경에서 **10M step 학습 후 100 에피소드 평가 diamond 도달률 ≥30%** (공식 baseline PPO+ImageNet pretrain 5~8% 대비 4~6배). Iron pickaxe 도달률 ≥80% 는 반드시 달성.
- **콘텐츠 목표**: **유튜브 시리즈 5편** (15~20분 / 편) + **블로그 시리즈 8편** (DevOps 주제 3편 + 학습 주제 5편). 목표 누적 조회수 50k+ / 블로그 월 방문 3k+.
- **학습 목표**: 3D RGB observation 처리 (CNN + ResNet-18 feature extractor), world-model 기반 long-horizon planning 튜닝, 대규모 replay buffer 관리 (100k~500k transition) 운영 경험 축적.

## 4. Phase plan (12주)

| Phase | 기간 | 산출물 |
|-------|------|--------|
| **P1 환경 구축 + 베이스라인** | W1~W2 (2주) | MineRL 0.4.x docker 이미지, Gymnasium wrapper, PPO+CNN 1M step 베이스라인, wood 도달률 ≥90% |
| **P2 Dreamer V3 + CNN 통합** | W3~W6 (4주) | v2.0 `backend/rl/dreamer.py` 를 3D RGB 로 확장, ResNet-18 encoder, world-model 10M step 학습, iron 도달률 ≥60% |
| **P3 curriculum + reward shaping** | W7~W9 (3주) | wood → stone → iron → diamond curriculum, intrinsic reward (RND or ICM), stuck detection + replay shaping, diamond 도달률 ≥30% |
| **P4 최종 실험 + 분석** | W10~W11 (2주) | seed 5개 × 10M step 반복, ablation (CNN depth / world-model size / reward shape), 결과 paper-quality 플롯 |
| **P5 콘텐츠 제작 + 공개** | W12 (1주) | 유튜브 5편 컷 편집, 블로그 초안 8편, GitHub 공개, HackerNews / r/MachineLearning / r/Korea_MachineLearning 배포 |

## 5. 성공 지표

- **기술**: diamond 도달률 ≥30%, iron 도달률 ≥80%, wall-clock 10M step ≤7일 on 4070 Ti, sample efficiency curve 가 baseline PPO 대비 2배 이상 완만하게 상승
- **콘텐츠**: 유튜브 누적 조회수 ≥50k, 블로그 Top-3 글 월 방문 ≥1k, reddit 게시물 upvote ≥100, 국내 AI 커뮤니티 (카카오 AI 오픈채팅방, 페북 텐서플로우 코리아) 피드백 수신 수 ≥20
- **부가**: 한국 마크 커뮤니티 관련 서브레딧/디시인사이드/네이버 카페에서 채널/블로그 언급 ≥5회, Minecraft 교육 커뮤니티에서 활용 문의 ≥1건

## 6. 리소스 추정

- **GPU**: NVIDIA 4070 Ti 16GB × 1 (보유). Dreamer V3 WM batch 16 / seq 64 기준 ~10GB VRAM, 여유 ~6GB
- **LLM**: Claude Max 20x (보유) — 코드 생성 + 블로그 초안 + 영상 대본 공동 작성
- **시간**: 주 10~20시간 × 12주 = **120~240 시간**. 주중 저녁 2시간 × 5 + 주말 5~10시간 기준
- **외부 비용 (추정)**:
  - 전기세: 학습 기간 약 200 kWh × 150원 = **3만원**
  - 도메인 + 블로그 호스팅: **월 1만원 × 3개월 = 3만원** (이미 개인 도메인 사용 시 0원)
  - 영상 편집: DaVinci Resolve Free + Audacity **0원**, 음원 라이선스 Epidemic Sound 월 $12 × 2개월 = **3만 2천원**
  - Cloud burst 예비비 (Lambda Labs A100 × 20h 대비): **15만원**
  - **합계 ≈ 24만원** (cloud burst 미사용 시 9만원)

## 7. 콘텐츠 전략

- **학습 영상 3단계 구성**:
  - (1) **블루퍼 편 2~3편** — "AI가 마크 배우는 실패 모음" (wood 못 찾아 죽음, 용암 다이빙, 무한 점프). 짧고 가볍게, 댓글 유인용
  - (2) **진전 편 1~2편** — iron 도달 영상 + "3주 걸린 이유" 기술 해설. Dreamer V3 설명 + 한국어 자막
  - (3) **성공 편 1편** — diamond 도달 하이라이트 + 전체 여정 요약 + 다음 계획 예고. 썸네일: "AI가 마크 다이아 캔 기록"
- **한국 마크 유튜버 콜라보 가능성**: 상위권 채널은 접근 어려움. **중소 채널 (구독 5~20만) 2~3 곳** 에 "AI vs 인간" 챌린지 제안. 양측 동일 시드에서 플레이 비교. 콜라보 성사 시 양쪽 시청자풀 교차 노출
- **개발 과정 블로그 시리즈** (DevOps + 팀 orchestration 관점 3편):
  - "claude-squad 로 RL 프로젝트 병렬 작업" (Pika v2 5-sprint 경험 바탕)
  - "GPU 1장으로 Dreamer V3 재현하기"
  - "12주 솔로 RL 프로젝트 운영: PM 관점 회고"
- **GitHub open-source 공개**: 프로젝트 완료 시점에 MIT 로 공개. Pika v2.0.0 과 연결 링크. README 에 학습 가중치 HuggingFace 공개 (Diamond 도달 seed 선별 3개)

## 8. 리스크 + 대응

- **기술 리스크**: Dreamer + CNN 튜닝 실패 (diamond 도달률 <10%) → **대응**: iron pickaxe 도달까지만 달성해도 "한국어로 Dreamer V3 재현기" 라는 기술 콘텐츠 가치 보존. wood→iron 구간도 MineRL 에서 쉬운 과제 아님
- **시간 리스크**: 12주 초과 → **대응**: phased deliverable. P1+P2 종료 시점 (W6) 에 중간 블로그 1편 선공개, P3 실패 시 P4 를 "분석 중심" 으로 전환해 기존 결과만으로 마무리
- **하드웨어 리스크**: 4070 Ti VRAM/속도 부족 → **대응**: Lambda Labs A100 80GB 시간당 $1.29 × 20h = $26 × 환율 1,400원 ≈ **5만원** 으로 final training run 만 cloud 실행. 예비비 15만원 내 해결
- **콘텐츠 실패 리스크**: 유튜브 조회수 목표 미달 → **대응**: 영상 조회수와 무관하게 (a) GitHub star + HuggingFace 가중치가 포트폴리오 자산, (b) 블로그 기술 시리즈는 장기 유입 채널, (c) 12주 프로젝트 자체가 "개인 + AI 협업 RL 프로젝트" 레퍼런스. 실패해도 sunk cost 는 시간만, 현금 지출 9~24만원 한정

## 참고

- [NeurIPS MineRL Diamond Competition 2021 결과](https://minerl.io/diamond/)
- [Dreamer V3 원논문](https://arxiv.org/abs/2301.04104)
- Pika v2.0.0 algorithm matrix — `docs/adr/0018-dreamer-v3-world-model.md`
- 5-sprint 협업 회고 — `docs/retrospective/v2.x-retrospective.md`
