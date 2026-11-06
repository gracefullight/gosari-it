# 설치·운영 매뉴얼

## 1. 구성

- **앱 이미지**: Node 26에서 Vite 정적 UI 빌드 → Python 3.14 slim 런타임.
  Litestar/Uvicorn이 정적 UI(`/`)와 API(`/api/v1`)를 같은 포트(8765)에서 서빙한다.
- **DB**: PostgreSQL 18 + pgvector. 공개 자료·응답 캐시만 저장한다.
  개인 수첩·나눔·지역은 앱 프로세스 RAM(세션) 한정이며 DB·WAL·백업에 들어가지 않는다.
- **역할 분리**: `db-init`가 관리자 권한으로 vector 확장·앱 역할·migration을 수행하고,
  앱 역할(`gosari_app`)에는 DDL/role 관리 권한을 주지 않는다.

## 2. 시작 순서

```sh
mise trust
mise install --locked   # mise.lock 플랫폼 고정
bun install
uv sync --all-packages
mise run up             # doctor → init → build → db → db-init → app → readiness
```

`mise run up` 내부 순서:

1. doctor: Linux daemon·로컬 context·lock·포트 검사. 원격/공유 daemon 차단.
2. init: `.local/settings.env`, `.local/images.env`, DB 비밀을 **원자적 exclusive create**로 생성.
   기존 파일·키·볼륨은 덮어쓰거나 삭제하지 않는다. OpenAI 키는 기본 빈 파일.
3. build: frozen 의존성으로 이미지 빌드. `.local/build-manifest.json`에
   image ID·소스 commit·lock 해시를 기록.
4. db `up --wait` → db-init 실제 실행 완료 확인 → app `--no-deps --wait`.
5. 앱 healthy + 호스트 HTTP ready 확인 후 URL 출력.

## 3. 비밀·설정

- `.local/secrets/` — `db_admin_password`, `db_app_password`, `openai_api_key`,
  `sources.env`(원천 키). **Git·빌드 컨텍스트·로그 제외.**
- `.local/settings.env` — 비밀 없는 실행 설정. `deploy/settings.env.example` 참고.
- 환경변수 계약은 SRS §16.2와 `apps/api/src/gosari/config.py`가 일치한다.
- 원천 키를 UI·LLM·매니페스트 URL에 노출하지 않는다. 매니페스트 URL은 인증정보 제거.

## 4. 외부 요청 게이트

`EXTERNAL_REQUESTS_ENABLED=false`(기본)이면 서버측 게이트가 모든 원천·모델 전송을 차단한다.
이 값은 앱 검사이지 방화벽이 아니다. 지도 타일· geocoding 등 브라우저 요청도
`TILE_PROVIDER_CONFIG` 미설정 시 발생하지 않는다(관측소 목록으로 대체).

라이브 전환 전 확인: 기관별 이용조건·활용신청·쿼터, 센터 네트워크 허용, 키 유효성.

## 5. 세션·개인정보

- 개인 기록은 세션 종료·만료·프로세스 재시작 시 소실되며 복구하지 않는다.
- worker 1·replica 1·reload 없음으로 고정한다(세션 RAM 공유 불가).
- 이미지/설정 변경·rebuild·down은 세션을 소실시킬 수 있다.

## 6. 백업·갱신

- 공개 DB 볼륨(`public_pgdata`)은 `down`으로 유지된다. 백업은 센터 정책 범위에서 볼륨 덤프.
- 갱신: 소스 갱신 → `mise run up` (재빌드·migration). migration 실패 후 볼륨 자동 삭제 금지.
- `reset`은 `--confirm=gosariit-local` 명시 확인 시에만 공개 볼륨을 삭제한다.

## 7. Windows 센터

- Compose Linux 컨테이너 경로는 Linux 이벤트 루프 + psycopg3 동기 풀.
- Windows native 경로(별도 검증): Proactor + psycopg3 동기 풀/제한 스레드풀.
- Docker Desktop 라이선스·WSL2 승인·보안 정책을 먼저 확인한다. Docker 금지 시
  무단 설치/DLP 우회 없이 native/replay 대안을 사용한다.

## 8. 문제 해결

| 증상 | 확인 |
|---|---|
| doctor: daemon 연결 실패 | OrbStack/Docker Desktop 시작 |
| 앱 limited | DB 연결·키·게이트 설정. `/api/v1/health/ready` 참조 |
| 예보 조회 불가 | 라이브 모드 + KMA 키 필요. 재생 표본 없음 |
| 지도 회색 | `TILE_PROVIDER_CONFIG` 미설정 → 목록 표시가 정상 |
| 포트 충돌 | `.local/settings.env`의 APP_PORT 변경 |