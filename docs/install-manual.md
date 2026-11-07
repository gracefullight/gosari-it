# 설치·운영 매뉴얼

## 1. 구성

- **앱 이미지**: Node 26에서 Vite 정적 UI 빌드 → Python 3.14 slim 런타임.
  Litestar/Uvicorn이 정적 UI(`/`)와 API(`/api/v1`)를 같은 포트(8765)에서 서빙한다.
- **DB**: PostgreSQL 18 + pgvector. 공개 자료·응답 캐시와 사용자별 수첩·지역·지인·나눔을 구분해 저장한다.
  개인 변경과 승인 결과는 같은 트랜잭션으로 보관하며 재시작 후 복원한다.
- **역할 분리**: `db-init`가 관리자 권한으로 vector 확장·앱 역할·migration을 수행하고,
  앱 역할(`gosari_app`)에는 DDL/role 관리 권한을 주지 않는다.

## 2. 시작 순서

```sh
mise trust
mise install --locked   # mise.lock 플랫폼 고정
bun install
uv sync --all-packages
mise run up             # init → doctor → build → db → db-init → app → readiness
```

`mise run up` 내부 순서:

1. init: `apps/api/.env`와 `apps/web/.env`가 없을 때 각 앱의 `.env.example`에서 권한0600으로 생성한다.
   새 API 설정의 DB 비밀번호는 임의 생성하며 기존 파일·키·볼륨은 덮어쓰거나 삭제하지 않는다.
2. doctor: 앱별 설정·DB 비밀번호·Linux daemon·로컬 context·lock·포트를 검사한다. 원격/공유 daemon은 차단한다.
3. build: frozen 의존성으로 이미지 빌드. `.local/build-manifest.json`에
   image ID·소스 commit·lock 해시를 기록.
4. db `up --wait` → db-init 실제 실행 완료 확인 → app `--no-deps --wait`.
5. 앱 healthy + 호스트 HTTP ready 확인 후 URL 출력.

## 3. 비밀·설정

- API 설정과 비밀은 `apps/api/.env`에 둔다. 예시는 `apps/api/.env.example`을 사용한다.
  `DB_ADMIN_PASSWORD`, `DB_PASSWORD`, 모델·기관 API 키와 `VWORLD_DOMAIN`을 이 파일에서 관리한다.
- 웹 설정은 `apps/web/.env`에 둔다. `VITE_` 변수는 브라우저에 포함되므로 서버 비밀을 넣지 않는다.
- Compose도 같은 `apps/api/.env`를 사용한다. DB 비밀번호는 이 환경변수에서 Docker 런타임 secret으로 전달하고,
  앱에는 관리자 비밀번호를 전달하지 않는다. 이미지 참조(`GOSARI_APP_IMAGE`, `GOSARI_DB_IMAGE`)와 `APP_PORT`도 API 설정에 둔다.
- 기존 DB를 연결할 때는 현재 DB 비밀번호를 그대로 유지한다. `.env`를 새로 만들어도 기존 DB 역할의 비밀번호가 바뀌지는 않는다.
- `.local/`은 로그·PID·lock·빌드 매니페스트 등 실행 산출물에만 사용한다. 기존 DB 볼륨은 유지한다.
- 실제 `.env`는 Git·이미지 빌드 컨텍스트·로그에서 제외한다.
- 환경변수 계약은 SRS §16.2와 `apps/api/src/gosari/config.py`가 일치한다.
- 원천 키를 UI·LLM·매니페스트 URL에 노출하지 않는다. 매니페스트 URL은 인증정보 제거.

## 4. 외부 요청 게이트

`EXTERNAL_REQUESTS_ENABLED=false`(기본)이면 서버측 게이트가 기관 분석과 모델 전송을 차단한다.
이 값은 방화벽 설정이 아니다. 제주 지도용 Open-Meteo 조회, 지도 타일·주소 검색은 각 화면에서 별도로 요청한다.

기관별 활용신청·쿼터·키 유효성을 확인한다. 현재 개발 환경의 제주데이터허브는 한국 네트워크에서 실조회가 확인됐다.

## 5. 세션·개인정보

- 개인 기록과 연결한 공개 근거, 미리보기·동의·실행 결과는 PostgreSQL에 저장한다.
- DB 저장 실패는 성공으로 반환하지 않고 메모리 변경을 되돌린다. 같은 승인 재시도는 중복 기록을 만들지 않는다.
- 개인 기록 초기화는 DB 삭제에 성공한 뒤 현재 세션과 브라우저 식별자를 지운다.
- 실행 중 작업과 세션 메모리 캐시 때문에 worker·replica는 각각1개를 유지한다. 네이티브 개발은 reload를 사용한다.
- 세션 접속 유효기간은 `SESSION_IDLE_TTL`·`SESSION_ABSOLUTE_TTL`로 설정한다. 현재 기본값은365일이다.

## 6. 백업·갱신

- DB 볼륨(`public_pgdata`)에는 공개 자료와 개인 기록이 함께 있으며 `down`으로 유지된다. 백업은 센터의 개인 기록 보관 정책을 확인한 뒤 수행한다.
- 갱신: 소스 갱신 → `mise run up` (재빌드·migration). migration 실패 후 볼륨 자동 삭제 금지.
- `reset`은 `--confirm=gosariit-local` 명시 확인 시 DB 볼륨을 삭제한다. 공개 자료와 모든 개인 기록이 삭제되며 앱별 `.env`는 유지된다.
- 화면의 개인 기록 초기화는 현재 세션의 DB 행과 메모리를 삭제한다. 기존 백업·내려받은 파일·OS 임시 파일·스왑은 별도 보관·삭제 대상이며, 초기화가 저장 장치의 포렌식 삭제를 수행하는 것은 아니다. 센터 운영자는 이 항목의 보관·정리 절차를 따로 확인한다.

## 7. Windows 센터

- Compose Linux 컨테이너 경로는 Linux 이벤트 루프 + psycopg3 동기 풀.
- Windows native 경로(별도 검증): Proactor + psycopg3 동기 풀/제한 스레드풀.
- Docker Desktop 라이선스·WSL2 승인·보안 정책을 먼저 확인한다. Docker 금지 시
  무단 설치/DLP 우회 없이 native/replay 대안을 사용한다.

## 8. 문제 해결

| 증상                     | 확인                                                                              |
| ------------------------ | --------------------------------------------------------------------------------- |
| doctor: daemon 연결 실패 | OrbStack/Docker Desktop 시작                                                      |
| 앱 limited               | DB 연결·키·게이트 설정. `/api/v1/health/ready` 참조                               |
| 예보 조회 불가           | Open-Meteo 연결·조회 날짜 확인. 기관 자료는 해당 서비스 활용신청과 인증 결과 확인 |
| 지도 회색                | `TILE_PROVIDER_CONFIG` 미설정 → 목록 표시가 정상                                  |
| 포트 충돌                | `apps/api/.env`의 APP_PORT 변경                                                   |
