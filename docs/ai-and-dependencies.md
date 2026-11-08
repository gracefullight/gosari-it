# AI·외부 서비스·오픈소스 사용 목록

기준: 2026-11-08 제출 준비 소스. 아래 버전은 문서 작성 시 로컬 설치 메타데이터에서 확인한 값이다. 제출 이미지의 최종 해석 버전은 함께 제공하는 `bun.lock`·`uv.lock`과 이미지 검증 기록을 따른다. 각 배포물의 LICENSE·NOTICE를 함께 확인한다.

## 1. AI 사용

| 구분 | 구성 | 사용하는 일 |
| --- | --- | --- |
| 런타임 생성 모델 | OpenAI `gpt-6-luna` | 공개 질문과 대화 문맥 이해, 도구·인자 선택, 부족한 조건 질문, 결과 설명과 등록된 UI·후속 동작 선택 |
| 로컬 임베딩 | `intfloat/multilingual-e5-small`, 384차원 | 로컬 모델이 준비된 환경의 공개 응답·개인 기록 의미 검색. 모델 카드의 MIT 라이선스 사용 |
| 개발 보조 | Codex·oh-my-agent·Agent Valley | 구현·회귀 작성·검토·작업 조정. 제품의 사용자 대화 런타임과 구분 |
| 화면 캐릭터 | 전용 제작 이미지 | 고사리잇 캐릭터 표시. 제주 공식 마스코트가 아님 |

기본 이미지의 E5 모델 revision은 `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 경로는 `/app/models/multilingual-e5-small`이다. 실제 이미지의 로컬 모델 로딩·검색 모드는 검증 영수증과 구분해 확인한다.

생성 모델에는 공개 질문과 허용된 대화 문맥, 서버가 정리한 공개 도구 결과를 전달한다. 개인 기록 조회는 서버 안에서 수행하고 모델에는 종류·건수만 전달한다. 저장된 개인 기록의 원문·지인 이름·개인 장소 좌표는 검색 결과로 모델에 전달하지 않는다. 질문과 대화 문맥은 별도의 개인 자료 경계 검사를 거친다. 공식 공개 관측 지점의 이름·좌표는 공개 조회 데이터로 구분한다.

모델은 원시 HTML·가격표 값을 생성해 렌더링하지 않는다. 등록된 컴포넌트와 결과 참조를 선택하고, 서버가 실제 데이터와 연결한다. 기록 변경은 기존 미리보기·동의·실행 절차를 사용한다.

사용량은 모델 호출 수, 입력·출력·추론·제공사 캐시 토큰으로 기록한다. 사용량이 누락되면 미확인 상태를 유지한다. 서비스 전체 비용 절감률과 달러 비용은 산정하지 않았다.

## 2. 외부 API와 브라우저 서비스

| 서비스 | 용도 | 전달·수신하는 자료 |
| --- | --- | --- |
| OpenAI Chat Completions | 스트리밍 도구 선택·답변 | 허용된 질문·문맥·공개 도구 결과 / 도구 호출·응답·사용량 |
| 제주데이터허브 578·579 | 공개 관측 지점과 일별 기상 | 관측소·날짜·페이지 조건 / 기관 관측 자료 |
| 기상청 공공데이터포털 | ASOS 일자료·초단기실황·단기예보 | 공개 지점·격자·시각 / 관측·예보 |
| aT 공공데이터포털 | 표준코드·도매 정산 | 날짜·시장·품목·규격 / 코드·정산 거래 |
| Open-Meteo | 지도·나들이 예보와 과거 재분석 | 공개 좌표·날짜·기상 요소 / 기온·강수확률·풍속·과거 날씨 |
| 브이월드 | 포함 필지와 토지 소유 구분 | 공개 지점 좌표·필지번호 / 소유 구분·기준월·갱신일 |
| 산림조합·탐나오·오아시스 | 가격 표본의 공식 원문 연결 | 사용자가 링크를 열 때 해당 서비스로 이동 |
| Google Maps URLs | 공개 지점 거리뷰 링크 | 링크에 공개 지점 좌표 포함. 사용자가 클릭해 이동 |
| OpenStreetMap 타일 | 지도 배경 | 브라우저의 지도 타일 요청 |
| Daum/Kakao 우편번호 | 사용자가 시작한 주소 검색 | 브라우저에서 검색한 주소 / 선택 주소 |
| OpenStreetMap Nominatim | 선택 주소의 좌표 변환 | 선택한 주소 / 좌표 |
| 브라우저 SpeechRecognition | 한국어 받아쓰기 | 사용자가 시작한 마이크 입력. 브라우저 제공사 인식 서비스가 원격 처리를 할 수 있음 |
| Web Audio Analyser | 실제 입력 음량 파형 | 브라우저 안에서 마이크 신호 분석 |
| Google Analytics 4 | 메뉴·채팅 이용 집계 | 정해진 페이지 이름과 시작·완료·중지 종류. 대화문·기록·지인·좌표·검색 조건을 보내지 않음 |

기관 키는 API 서버에서 읽는다. 지도·주소·음성·분석 스크립트는 브라우저의 별도 요청 경로를 사용한다. 음성은 앱 백엔드에 업로드하지 않는다. 브라우저의 주소 검색과 좌표 변환에는 사용자가 선택한 주소가 해당 서비스로 전송된다.

데이터별 실조회·표본 구분과 이용 조건은 [데이터 활용 명세](data-usage.md)에 있다.

## 3. 웹 주요 의존성

| 패키지 | 확인 버전 | 라이선스 | 용도 |
| --- | --- | --- | --- |
| React·React DOM | 19.3.1 | MIT | 화면·상태 렌더링 |
| Vite | 8.3.6 | MIT | 개발 서버·정적 UI 빌드 도구 |
| TypeScript | 5.9.3 | Apache-2.0 | 타입 검사 |
| Tailwind CSS | 4.3.5 | MIT | 화면 스타일 |
| @gracefullight/krds-tw | 0.6.1 | MIT | 공통 디자인 기반 |
| @base-ui/react | 1.9.0 | MIT | 대화상자·메뉴·접기·선택기 |
| @json-render/core·react | 0.22.0 | Apache-2.0 | 모델이 선택한 결과 UI 렌더링 |
| @tanstack/react-query | 5.106.1 | MIT | 서버 조회와 캐시 |
| @tanstack/react-hotkeys | 0.22.0 | MIT | 단축키 |
| Jotai | 2.20.3 | MIT | 대화·초안·화면 상태 |
| MapLibre GL JS | 5.24.0 | BSD-3-Clause | 제주 지도 |
| FullCalendar core·daygrid·interaction·react | 6.1.22 | MIT | 수첩·날짜 달력 |
| @gracefullight/markdown | 0.1.8 | MIT | 한국어 Markdown 처리 |
| react-markdown·remark-gfm | 10.1.0·4.0.1 | MIT | 답변·표·목록 표시 |
| Zod | 4.6.7 | MIT | UI·응답 구조 검사 |
| @phosphor-icons/react | 2.1.10 | MIT | 화면 아이콘 |
| date-fns·react-day-picker | 4.4.0·10.0.2 | MIT | 날짜 처리·선택 |
| nextstepjs·nuqs | 2.3.0·2.10.2 | MIT | 사용 안내·URL 상태 |

`class-variance-authority`, `clsx`, `cn`, `tailwind-merge`도 공통 클래스 구성에 사용한다. 전체 직접 의존성은 [웹 manifest](../apps/web/package.json), 해석된 전이 의존성은 [bun.lock](../bun.lock)에 있다.

## 4. API 주요 의존성

| 패키지 | 확인 버전 | 라이선스 | 용도 |
| --- | --- | --- | --- |
| Litestar | 2.25.0 | MIT | API·OpenAPI |
| Uvicorn | 0.54.0 | BSD-3-Clause | ASGI 실행 |
| Pydantic·pydantic-settings | 2.14.3·2.16.2 | MIT | 입력·설정 검사 |
| psycopg·psycopg-pool | 3.3.8·3.3.3 | LGPL-3.0-only | PostgreSQL 연결·풀 |
| pgvector Python | 0.5.1 | MIT | 벡터 저장·검색 연결 |
| Alembic | 1.20.1 | MIT | DB migration |
| HTTPX | 0.28.1 | BSD-3-Clause | 기관·모델 HTTP 요청 |
| pandas | 3.1.1 | BSD-3-Clause | 자료 처리 |
| structlog | 26.1.0 | MIT OR Apache-2.0 | 구조화 로그 |
| sentence-transformers | 6.2.0 | Apache-2.0 | 로컬 임베딩 |
| PyTorch | 2.15.0 | 배포물의 복수 라이선스 | 로컬 임베딩 실행. CPU Linux 휠과 macOS 배포물을 구분 |
| Tenacity | 9.2.1 | Apache-2.0 | 재시도 지원 |

PyTorch 로컬 배포물의 라이선스 표현은 `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND ISC AND MIT AND Zlib`다.

전체 API 의존성은 [API manifest](../apps/api/pyproject.toml)와 [uv.lock](../uv.lock)에 있다. Python 런타임은 3.14, DB는 PostgreSQL 18과 pgvector 확장이다. 검증 도구로 pytest·Vitest·Testing Library·Ruff·Pyrefly·Biome을 사용한다.

프로젝트 소스의 MIT 라이선스는 [LICENSE](../LICENSE)에 있다. 지도 데이터의 ODbL, 기관 자료 이용 조건, 외부 서비스 약관, 라이브러리 라이선스는 서로 구분한다.
