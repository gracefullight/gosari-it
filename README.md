# 고사리잇 (gosari-it)

제주 고사리 채취 동행 AI 에이전트 — 제주 AI·빅데이터 활용 AI Agent 개발 챌린지 출품작.

봄 고사리철의 **날씨 비교 · 경험 기록 · 가족·지인 나눔 · 가격 정보 확인**을 하나의 대화로 연결합니다.
자연어 이해·계획·설명은 LLM(GPT-6 Luna)이, 자료 검사·집계·비교·개인 변경은 결정론적 코드와 확인 폼이 담당합니다.

## 빠른 시작 (mise + Docker Compose)

사전 조건: [mise](https://mise.jdx.dev), 로컬 Docker 엔진(OrbStack/Docker Desktop), 프로젝트 검토.

```sh
mise trust
mise install --locked
bun install
uv sync --all-packages
mise run up
```

정상이면 호스트에서 **http://127.0.0.1:8765** 로 접속합니다. loopback만 publish됩니다.

- 키 미설정·외부 통신 비활성은 **제한 모드**로 동작합니다(고정 검증 표본 재생 + 로컬 수첩/나눔).
  유료 API 호출이 readiness의 선행조건이 아닙니다.
- 최초 `mise run up`은 이미지를 빌드합니다. 이후 시작은 빠르게 재사용됩니다.

### 운영 명령

| 명령 | 동작 |
|---|---|
| `mise run doctor` | Docker·lock·포트·정책 검사 |
| `mise run init` | 로컬 설정/비밀 생성 (덮어쓰기 없음) |
| `mise run up` | 빌드 → DB → 초기화(migration) → 앱 → readiness 확인 |
| `mise run status` | 컨테이너·기능 가용성 |
| `mise run logs` | 최근 로그 (비식별) |
| `mise run down` | 컨테이너 정리, DB 볼륨과 개인 기록 유지 |
| `mise run reset -- --confirm=gosariit-local` | 공개 자료와 개인 기록이 담긴 DB 볼륨 삭제 (명시 확인 필수) |

### 개발 모드 (네이티브)

```sh
mise run infra:up     # 개발용 PostgreSQL 18/pgvector
mise run db:migrate
mise run dev          # API(8000) + Vite(5173, /api 프록시)
```

네이티브 API는 `.local/settings.env`·`.local/secrets/sources.env`·`.local/dev.env`를 읽고 기존 환경변수를 우선한다. DB·OpenAI 키 파일은 `.local/secrets/`에서 읽는다. 기기별 DB 주소는 `.local/dev.env`에서 설정한다. 키 값은 소스에 넣지 않는다.

## 다섯 기능

1. **나들이** — 제주 날씨 지도, 후보 날짜·지역·시각과 우선순위 비교, 준비 목록 편집
2. **지역 탐색** — 주소 검색, 관심 장소 핀, 방문일·메모·주변 날씨
3. **내 수첩** — 기록 생성·수정·삭제·검색·달력, 위치와 공개 날씨 연결, PostgreSQL 보관
4. **나눔** — 지인 관계와 나눔 이력, 수정·삭제·전달 완료 변경, 수첩 기록 연결
5. **가격 조사** — 날짜·시장·생건·등급·포장별 실제 aT 정산 조회, 상품 가격/1kg 환산 전환, 조건별 캐시

AI 대화는 공개 조건을 확인한 뒤 공용 응답 캐시를 먼저 조회한다. 캐시가 없으면 GPT-6 Luna가 허용된 도구를 선택하고, 실제 조회 결과를 받아 다음 도구 실행이나 답변을 이어 간다. 답변은 SSE로 전달하며 도구별 실행 내역은 접힌 목록에서 확인한다. 연결이 끊기면 같은 작업을 이어받고, 실행 중인 답변은 중지할 수 있다.

공개 도구의 정규화 결과는 PostgreSQL 공용 캐시에 보관한다. 동일 질문 또는 같은 확정 조건에서 코사인 유사도가 0.95를 초과하는 질문은 품질·최신성·무결성 검사를 거쳐 응답을 재사용한다. 개인 기록 검색은 로컬 E5 의미검색과 키워드를 결합한다.

산림조합 조사가와 소매 상품은 확인 날짜가 있는 표본·원문 링크를 제공한다. 기관 응답이 차단되면 실패 범위를 유지하며, 다른 출처로 조회한 값은 출처를 구분한다.

## 안전 경계

- 개인 기록·별칭·정확 좌표는 **외부 LLM·공용 캐시·운영 로그로 전송되지 않습니다.**
- 모든 개인 변경은 `preview → 사용자 확인 → consent → commit` 승인 프로토콜을 거치며 멱등입니다.
- 공개 분석은 허용 필드 allowlist DTO로만 전송하고, 결정론 계산을 사실 원장으로 삼습니다.
- 숫자 0(valid_zero)·결측(missing)·의미 미확정 공란(unresolved_blank)을 구분합니다.

## 검증

```sh
mise run test        # API 회귀(고정 표본 기대값) + 웹 테스트
mise run lint
mise run typecheck
```

고정 회귀 기대값(SRS §10.6): 선흘 2023 강수 21/51일·2024 24/61일,
공통 월일 04-11~05-31 51일에서 21/20, 제주184 강수 양수 24·숫자 0 8·공란 29,
상품 200g 32,500원 → 162,500원/kg 환산.

## 프로파일별 기능 행렬

| 기능 | center(기본) | replay | live(외부 요청 승인) |
|---|---|---|---|
| 공개 분석(고정 표본) | ✓ 재생 표시 | ✓ | ✓ |
| 원천 실조회 | ✗ | ✗ | ✓ (키·게이트 필요) |
| LLM 설명 | 키 있으면 | ✗ | ✓ |
| 수첩·나눔·지역·지인(DB 구성 시 영속 보관) | ✓ | ✓ | ✓ |
| 파일 내보내기/불러오기 | ✗ (정책 미확인) | ✗ | 정책 승인 후 |
| 지도 타일 | 설정 시 | 설정 시 | ✓ |

## 문서

- [설치·운영 매뉴얼](docs/install-manual.md)
- [원천 어댑터 매뉴얼](docs/adapter-manual.md)
- [데이터 활용 명세](docs/data-usage.md)
- [전체 기획 인수 점검](docs/acceptance/2026-11-07/report.md)
- [에이전트 실행·비용 절감](docs/agent-runtime.md)
- 기준 명세: 고사리잇 SRS v1.2 (별도 제공 기획 자료)

## 라이선스

MIT — [LICENSE](LICENSE). KRDS-TW(@gracefullight/krds-tw) MIT 사용.
지도 데이터 © OpenStreetMap contributors (ODbL). 캐릭터는 전용 제작 이미지이며 제주 공식 마스코트가 아닙니다.
