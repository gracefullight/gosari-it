# 원천 어댑터 매뉴얼

키·세부 경로는 이 매뉴얼과 환경설정으로 고정한다. 실제 키는 납품물에 포함하지 않는다.
기관 API 호출은 `TransmissionGate`(허용 도메인·게이트·일일 예산·재시도)를 통과한다. 지도용 공개 날씨는 `WeatherService`에서 날짜별 캐시와 오류 상태를 관리한다.

## 허용 도메인

`open.jejudatahub.net`, `apis.data.go.kr`, `apihub.kma.go.kr`, `api.openai.com`

공개 날씨: `api.open-meteo.com`, `archive-api.open-meteo.com`. 타일·주소 검색은 브라우저가 OpenStreetMap·Daum과 통신한다.
타일 제공처는 접속 IP와 요청한 지도 범위를, 주소 검색 제공처는 입력한 검색어를 받는다. 센터에서 제공처별 허용 경로를 확인한다. 개인 별칭·수첩 원문은 지도 요청에 넣지 않는다.

## 1. 제주데이터허브 (필수)

| 자료 | 엔드포인트 | 조건 |
|---|---|---|
| 578 기상관측소 | `https://open.jejudatahub.net/api/proxy/t1bab75a555a15715btaa7a5abaa1aab/{JEJU_PROJECT_KEY}` | GET, 선택 `observatoryName` |
| 579 일별 기상 | `https://open.jejudatahub.net/api/proxy/1aD5taat1attaa51Db1511b51ab9Da19/{JEJU_PROJECT_KEY}` | GET, 필수 `searchDate=YYYYMMDD`, 선택 `observatoryName`, `number`/`limit` |

- 페이지 대조: `number`·`limit`·`totCnt`·`hasMore`와 실제 반환 수를 기록한다.
- 579는 날짜별 요청. 부분 성공 시 성공/실패 날짜를 각각 집계한다.
- 필드: `baseDate`, `observatoryName`, `dailyRainfall`, `averageTemperature`.
- 일일 쿼터 1,000 표시(상세 페이지). 예산(`SOURCE_DAILY_BUDGET`) 내에서 관리.
- 확인된 가장 늦은 응답 2025-03-30은 표본 한계이며 전체 최종일로 단정하지 않는다.
- 578 코드 ↔ 579 명칭은 자동 동일 가정하지 않는다. 일대일 연결만, 모호하면 확인 요청.

## 2. 기상청 (보완)

| 자료 | 엔드포인트 | 조건 |
|---|---|---|
| ASOS 일자료 15059093 | `https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList` | `dataCd=ASOS`, `dateCd=DAY`, `startDt/endDt/stnIds`, `KMA_SERVICE_KEY` |
| 단기예보 15084084 | `https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst` | `base_date/base_time/nx/ny`, `KMA_SERVICE_KEY` |
| 초단기실황 15084084 | `https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst` | `base_date/base_time/nx/ny`, `KMA_SERVICE_KEY` |
| AWS 매분 (API허브) | `apihub.kma.go.kr` `nph-aws2_min` | 별도 `KMA_HUB_KEY` 필요 — **미확보, 제한 모드** |

- 공공데이터포털 키는 **Decoding 기준** 값. HTTP 클라이언트가 1회만 인코딩한다.
- `KMA_SERVICE_KEY`/`AT_SERVICE_KEY`는 포털 공통 키의 설정별 별칭(별도 발급 3개 아님).
- 관측시각·발표시각·예보 대상시각을 구분한다. 예보를 관측으로 표시하지 않는다.
- ASOS는 D-1까지. 현재 날씨는 제주12지역의 초단기실황 격자 관측을 사용한다. 강수량은1시간 누적이며 일강수와 구분한다. AWS 지점 관측은 별도 API허브 키가 필요하다.

## 3. aT 도매 (보완)

| 자료 | data.go.kr | 비고 |
|---|---|---|
| 표준코드 | 15141818 | 대분류 산채류 14·중분류 고사리 02 |
| 거래정산 | 15141809 | 필수: 거래정산일·도매시장 코드 |

- 실제 정산 경로는 `https://apis.data.go.kr/B552845/katSale/trades`다.
  `cond[trd_clcln_ymd::EQ]`·`cond[whsl_mrkt_cd::EQ]`와 `returnType=json`으로 요청하고 모든 페이지를 대조한다.
- 코드 경로는 `/B552845/katCode/goods`, `wholesaleMarkets`, `grades`, `packagings`다.
- 조회 날짜·시장·생건·등급·포장·단량·산지를 분리하며 실패한 시장을 완료된 집계에 섞지 않는다.
- 단가/총액 의미 미확정 시 환산·가중 평균 보류. 시장·산지·생/건·단량·등급·포장 분리.
- 429는 Retry-After 준수, 최대 3회 지연 재시도.

## 4. 조사가·상품 표시가 (링크 우선)

- 산림조합 forestinfo: 공식 조회 링크만. 자동 취득·재배포 권리 미확인.
  생산지 가격은 출하기 입력값이 이후에도 표시될 수 있음.
- 탐나오·오아시스: 공식 원문 링크 + 검증된 표본 카드(확인시점 명시).
  상품 표시가는 체결가·대표시세로 바꾸지 않는다.
- 링크만 제공한 카드: `source_mode=link`, `link_status=link_ready`,
  수치 미취득 시 `data_status=unavailable`(LINK_ONLY).

## 5. 모델

- **GPT-6 Luna** (`gpt-6-luna`): 공개 질문 구조화·검증된 결과 설명만.
  `OPENAI_API_KEY_FILE` 서버 주입. 키 미확보 시 제한 모드(결정론 카드만).
- **multilingual-e5-small**: 로컬 CPU 임베딩 384차원, `query: ` 접두사. 설치된 모델 리비전과 설정을 대조하며, 기본 `main` 참조의 고정은 인수 미완료 항목이다.
  512토큰 초과·미확인 입력은 잘라서 매칭하지 않고 캐시 우회.

## 6. 재생(Replay) 픽스처

`fixtures/`의 검증 CSV/JSON은 2026-11-05 기준 공개 표본이다.
실시간 조회 결과로 표시하지 않으며 `source_mode=replay`·`verified_on`을 명시한다.
입력 해시는 회귀 테스트가 재계산한다(선흘 SHA-256 `9e7751d7…4ac145`).
