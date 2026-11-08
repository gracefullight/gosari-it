# 설치·운영 매뉴얼

## 1. 구성과 실행 주소

| 구성          | 역할                                                           |
| ------------- | -------------------------------------------------------------- |
| 앱            | Litestar/Uvicorn API와 Vite 정적 UI를 같은 포트에서 제공       |
| DB            | PostgreSQL 18·pgvector. 공개 캐시·근거와 세션별 개인 자료 저장 |
| 초기화        | `db-init`가 vector 확장·앱 역할·migration 수행                 |
| 네이티브 개발 | API 8000·Vite 5173·로컬 DB 15432                               |
| Compose       | 기본 UI/API `http://127.0.0.1:8765`, DB 내부 주소 `db:5432`    |

이미지의 Node·Python·uv·Dockerfile frontend 기반은 제출 빌드에 사용한 실제 digest로 고정하고, Bun·Python 의존성은 잠금 파일을 사용한다. 최종 이미지·플랫폼 식별자는 검증 영수증을 따른다.

앱 DB 역할은 `gosari_app`이다. 관리자 비밀번호는 DB 초기화에만 사용하고 앱 컨테이너에서는 비워 둔다. 앱은 읽기 전용 루트 파일시스템·UID10001로 실행한다.

## 2. 앱별 설정

API는 `apps/api/.env`, 웹은 `apps/web/.env`를 사용한다. 예제는 각 앱의 `.env.example`에 있다. 없는 파일은 `mise run init`으로 만들며 기존 값과 DB 볼륨을 유지한다.

| API 설정                                        | 용도                                                       |
| ----------------------------------------------- | ---------------------------------------------------------- |
| `DB_HOST`·`DB_PORT`·`DB_NAME`·`DB_USER`         | DB 연결                                                    |
| `DB_PASSWORD`·`DB_ADMIN_PASSWORD`               | 앱 역할·초기화 관리자 비밀번호                             |
| `EXTERNAL_REQUESTS_ENABLED`                     | 기관 분석·모델 외부 요청 게이트                            |
| `OPENAI_API_KEY`·`LLM_MODEL`                    | 모델 인증·모델명, 기본 `gpt-6-luna`                        |
| `JEJU_PROJECT_KEY`                              | 제주데이터허브                                             |
| `KMA_SERVICE_KEY`                               | 공공데이터포털 기상청                                      |
| `KMA_HUB_KEY`                                   | 선택적 별도 API허브 AWS 경로                               |
| `AT_SERVICE_KEY`                                | 공공데이터포털 aT                                          |
| `VWORLD_API_KEY`·`VWORLD_DOMAIN`                | 브이월드 전용 키·등록 도메인                               |
| `RESPONSE_CACHE_ENABLED`                        | DB 공용 캐시 사용                                          |
| `DOMAIN_THRESHOLD_CONFIG`                       | 의미 캐시 임계값, 기본 0.95·실제 유사도는 이를 초과해야 함 |
| `EMBEDDING_MODEL_PATH`·`EMBEDDING_REVISION`     | 로컬 임베딩 모델·리비전                                    |
| `APP_PORT`·`GOSARI_APP_IMAGE`·`GOSARI_DB_IMAGE` | Compose 포트·이미지 참조                                   |

예시의 키는 가짜 값이다. 실제 값은 API 설정에만 입력한다.

```dotenv
OPENAI_API_KEY=example-openai-key
JEJU_PROJECT_KEY=example-jeju-key
KMA_SERVICE_KEY=example-kma-key
AT_SERVICE_KEY=example-at-key
VWORLD_API_KEY=example-vworld-key
VWORLD_DOMAIN=http://localhost
LLM_MODEL=gpt-6-luna
EXTERNAL_REQUESTS_ENABLED=true
```

OpenAI는 명시된 `OPENAI_API_KEY`를 우선하고 비어 있을 때 선택적 파일 설정을 사용한다. 명시적 `*_FILE` 운영 호환도 유지하지만 일반 설정은 API `.env`의 직접 값을 사용한다. 웹 `VITE_*` 값은 브라우저에 포함되므로 API 인증 키를 넣지 않는다.

Compose는 같은 API `.env`를 읽는다. PostgreSQL 관리자 비밀번호만 writable DB 서비스의 런타임 secret으로 연결하고, 읽기 전용 앱·db-init에는 필요한 직접 환경변수를 전달한다. `db-init`에는 전체 API 설정을 전달하지 않는다. 기존 DB를 사용할 때는 그 DB의 실제 비밀번호를 유지한다.

컨테이너 이미지에는 multilingual-e5-small의 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`을 `/app/models/multilingual-e5-small`에 포함한다. 런타임은 로컬 파일만 읽고 `HF_HUB_OFFLINE=1`을 사용한다. 네이티브 실행은 준비된 로컬 모델 경로를 지정한다. Compose 앱은 이 컨테이너용 경로와 고정 revision을 명시해 네이티브 모델 경로 설정과 분리한다.

설정은 프로세스 시작 때 읽고 캐시한다. 변경 뒤 해당 API 실행 경로를 재시작한다. `.local/`은 PID·로그·lock·빌드 매니페스트 등 실행 산출물에 사용한다.

## 3. Compose 시작

로컬 Docker 엔진과 mise를 준비한 뒤 실행한다.

```sh
mise trust
mise install --locked
bun install
uv sync --all-packages
mise run init
# API 설정을 입력한 뒤 실행
mise run up
```

실행 순서는 설정 확인 → frozen 의존성 이미지 빌드 → DB 준비 → db-init/migration → 앱 → readiness다. `.local/build-manifest.json`에 이미지·소스 기준·잠금 파일 해시를 기록한다.

키와 외부 요청 설정을 제공하면 실조회 경로를 사용한다. `APP_PROFILE=replay`는 검증 표본 재생 모드다. 모델 연결이 없는 자유 채팅은 모델 오류 상태를 반환하며, 표본·개인 메뉴의 가용성과 구분한다.

```sh
mise run status
mise run logs
mise run down
```

`down`은 컨테이너를 정리하고 DB 볼륨을 유지한다. 이미지 갱신과 migration도 `mise run up`을 사용한다. DB 전체 초기화는 별도 명시 명령이다.

```sh
mise run reset -- --confirm=gosariit-local
```

이 명령은 공개 자료와 개인 기록이 담긴 DB 볼륨을 삭제한다. 유지할 DB의 갱신에는 사용하지 않는다.

## 4. 네이티브 개발과 같은 DB 사용

```sh
mise run init
mise run infra:up
mise run db:migrate
mise run dev
```

API의 DB 설정은 `127.0.0.1:15432`다. `infra:up`은 같은 `gosariit-local` 프로젝트에 `compose.yaml`과 `compose.native.yaml`을 적용해 기존 DB 이미지·볼륨만 시작한다. `--no-build --pull never`를 사용하고 앱·migration을 함께 실행하지 않는다.

컨테이너 앱은 계속 내부 `db:5432`를 사용한다. 일반 Compose DB는 내부망에 두고 native override에서만 bridge와 loopback 포트 `127.0.0.1:15432`를 추가한다.

```sh
mise run infra:down
```

`infra:down`은 같은 DB에 `stop`만 실행해 컨테이너·볼륨·기록을 유지한다.

## 5. 연결과 기능 확인

| 주소                    | 확인 내용               |
| ----------------------- | ----------------------- |
| `/api/v1/health/live`   | API 프로세스 응답       |
| `/api/v1/health/ready`  | DB를 포함한 준비 상태   |
| `/api/v1/capabilities/` | 실제 설정의 기능 가용성 |
| `/schema/openapi.json`  | 등록된 API 명세 JSON    |
| `/`                     | 웹 UI                   |

기관 분석과 모델 전송 게이트가 꺼져 있어도 지도용 Open-Meteo·지도 타일·주소 검색·브라우저 음성은 별도 경로를 사용한다. 완전한 오프라인 실행과 구분한다. 브이월드는 공공데이터포털 공통키가 아닌 전용 키와 등록 도메인을 사용한다.

마이크 기능은 지원 브라우저에서 사용자가 눌러 시작한다. 한국어 인식과 파형을 사용하며 발화 종료 후 입력란에 자동 반영한다. 언어팩 설치·수동 받아쓰기 확인 단계는 없다. 브라우저 권한·인식 서비스 연결·실제 전사 품질은 해당 환경에서 확인한다.

## 6. 보관·운영

공개 근거와 개인 기록·미리보기·동의·실행 결과는 PostgreSQL에 저장한다. DB 저장 실패는 성공으로 반환하지 않으며 같은 승인 재시도는 중복 기록을 만들지 않는다. `public_pgdata` 백업에는 개인 자료도 포함된다.

현재 작업·대화 메모리를 사용하는 API worker·replica는 각각 1개로 운영한다. 세션 유효기간은 `SESSION_IDLE_TTL`·`SESSION_ABSOLUTE_TTL` 설정을 사용한다. 설정의 기본값은 365일이다.

화면의 개인 기록 초기화는 현재 세션의 DB 자료를 삭제한다. 운영 백업과 외부로 내려받은 파일의 보관은 별도다. 실제 `.env`, 키, 개인 DB는 Git·이미지 빌드 컨텍스트·제출 소스에서 제외한다.

## 7. 환경별 검증 범위

Linux 컨테이너는 Uvicorn의 asyncio 실행과 psycopg 동기 풀을 사용한다. 최신 이미지·빈 DB 실행 여부는 [구현 결과](submission-results.md)에 이미지 식별자와 함께 기록한다. 기존 이미지에 최신 소스만 연결한 실행과 새 제출 이미지를 구분한다.

Windows 센터 PC·WSL2·Docker Desktop과 실제 휴대폰의 전체 설치·사용은 해당 장비에서 확인해야 한다. 코드 경로 지원, macOS 개발 실행, 브라우저 화면 크기 변경을 그 장비의 검증으로 표현하지 않는다.

## 8. 제출 실행본과 소스 ZIP

센터용 Linux AMD64 이미지는 별도 태그로 빌드한다.

```sh
mise run submission:build:amd64
SUBMISSION_IMAGE=gosariit-app:submission-amd64 SUBMISSION_PORT=8766 SUBMISSION_RUNTIME_DIR=.local/submission-runtime-check mise run submission:verify
```

검증 도구는 기존 개발 DB와 다른 프로젝트·새 빈 볼륨을 만들고 bootstrap·migration·readiness를 확인한다. 원본 설정은 API `.env`를 읽으며 격리 실행용 임시 설정과 소유 원장은 지정한 `.local/` 디렉터리에 권한을 제한해 저장한다. 같은 디렉터리의 이전 원장이 있으면 덮어쓰지 않으므로 검증마다 새 디렉터리를 사용한다.

검증을 마칠 때는 같은 디렉터리로 해당 도구가 만든 컨테이너만 중지한다. 볼륨·로그·이미지는 보존한다.

```sh
SUBMISSION_RUNTIME_DIR=.local/submission-runtime-check mise run submission:stop
```

검토한 계획서 PDF와 안전한 검증 JSON을 지정해 소스 ZIP을 만든다. 다음 PDF 경로는 예시이며 실제 검토 파일로 바꾼다.

```sh
mise run submission:package -- --proposal path/to/reviewed.pdf --receipt docs/verification/submission-20261108.json
```

포장 도구는 허용한 소스·문서·표본·잠금 파일만 포함하고 실제 `.env`·개인 DB·실행 비밀·에이전트 작업 폴더를 제외한다. ZIP의 파일별 해시·매니페스트·SHA256과 추출 검증 결과를 생성한다. 선택적 시연 영상은 `--video path/to/demo.mp4`로 지정한다. 포장 명령 자체는 앱 실행이나 모델 호출을 하지 않는다.

## 9. 문제 해결

| 증상                           | 확인                                                  |
| ------------------------------ | ----------------------------------------------------- |
| Docker 연결 실패               | 로컬 Docker 엔진·context·포트                         |
| API 응답만 되고 준비 상태 실패 | DB 호스트·포트·기존 비밀번호와 `/health/ready`        |
| 자유 대화 실패                 | OpenAI 키·모델 접근·외부 요청 설정·작업 오류          |
| 기관 조회 실패                 | 기관별 활용신청·키·쿼터·실패 범위                     |
| 브이월드 인증 실패             | 전용 키와 등록 도메인                                 |
| 지도가 열리지 않음             | 타일 네트워크·브라우저 WebGL. 지역 목록으로 날씨 확인 |
| 음성 입력 실패                 | 지원 브라우저·마이크 권한·장치·인식 서비스 연결       |
| 포트 충돌                      | API `.env`의 `APP_PORT`와 기존 실행 프로세스          |
