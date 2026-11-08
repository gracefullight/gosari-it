# 서버 구성과 데이터 구조

## 서버 구성

센터 PC 한 대에서 Docker Compose로 컨테이너 2개를 띄운다. 브라우저는 `127.0.0.1:8765` 한 곳만 접속한다.

```mermaid
flowchart LR
    B["브라우저<br/>React UI · MapLibre · 음성 인식"]
    subgraph PC["센터 PC · Docker Compose"]
        APP["app 컨테이너<br/>Litestar API + 정적 UI<br/>로컬 임베딩 e5-small(CPU)<br/>127.0.0.1:8765"]
        INIT["db-init (1회)<br/>DB 역할 생성 · alembic migration"]
        DB[("db 컨테이너<br/>PostgreSQL 18 + pgvector<br/>내부 네트워크 전용")]
    end
    subgraph EXT["기관·외부 API (서버에서 호출)"]
        KMA["기상청 초단기실황·단기예보·ASOS"]
        JEJU["제주데이터허브 578·579"]
        AT["aT 도매 정산"]
        VW["브이월드 연속지적도·토지소유"]
        OM["Open-Meteo (예보 대체·과거 재분석)"]
        OAI["OpenAI GPT-6 Luna"]
    end
    subgraph DIRECT["브라우저가 직접 쓰는 서비스"]
        OSM["OSM 타일 · 주소 검색"]
        GSV["Google 거리뷰 링크"]
    end
    B -->|"HTTP · SSE"| APP
    B --> OSM
    B -.->|"사용자 클릭"| GSV
    INIT --> DB
    APP --> DB
    APP --> KMA & JEJU & AT & VW & OM
    APP -->|"공개 조건·도구 결과만"| OAI
```

- app 컨테이너는 읽기 전용 루트, 비root 사용자, 외부 포트는 8765 하나다. 설정은 `apps/api/.env`에서 읽는다.
- db 컨테이너는 호스트에 포트를 열지 않는다. 네이티브 개발 때만 `compose.native.yaml`로 `127.0.0.1:15432`를 연다.
- 개인 기록 원문은 OpenAI에 보내지 않는다. 모델에는 공개 조건, 도구 결과, 개인 검색의 종류·건수만 간다.
- 기획서의 시스템 구성도: [제주고사리_시스템구조도_v0.21.svg](proposal/assets/제주고사리_시스템구조도_v0.21.svg)

실행 흐름과 캐시 규칙은 [에이전트 실행·캐시 구조](agent-runtime.md), 설정값은 [설치·운영 매뉴얼](install-manual.md)에 있다.

## ERD

테이블 14개가 한 DB에 있다. 개인 기록 4개 테이블은 `app_session`을 외래 키로 참조하며 세션이 끝나면 함께 지운다. 공개 자료 테이블은 외래 키 없이 `station_id`·`source_id`·`evidence_id` 문자열로 느슨하게 연결한다. 응답 캐시의 `embedding`은 pgvector 384차원이며 현재는 순차 탐색이고 벡터 인덱스는 만들지 않았다.

### 세션과 개인 기록

```mermaid
erDiagram
    app_session {
        text session_id PK
        timestamptz created_at
        timestamptz expires_at
        timestamptz last_activity_at
        text lifecycle
        jsonb control_state
    }
    personal_notebook_entry {
        text record_id PK
        text session_id FK
        int4 revision
        date experience_date
        jsonb companion_aliases
        text activity_text
        text amount_value
        text amount_unit
        timestamptz created_at
        timestamptz updated_at
        text location_address
        float8 latitude
        float8 longitude
        text private_region_id
        jsonb public_evidence_ids
    }
    personal_private_region {
        text region_id PK
        text session_id FK
        int4 revision
        text kind
        text public_area_code
        text coarse_grid
        text local_alias
        jsonb selected_station_mapping_ids
        timestamptz created_at
        timestamptz updated_at
        date visited_on
        float8 latitude
        float8 longitude
    }
    personal_contact {
        text contact_id PK
        text session_id FK
        int4 revision
        text name
        text relationship
        text notes
        timestamptz created_at
        timestamptz updated_at
    }
    personal_share_draft {
        text share_draft_id PK
        text session_id FK
        int4 revision
        jsonb items
        bool message_enabled
        text editable_message
        jsonb source_record_ids
        jsonb public_evidence_ids
        timestamptz prepared_at
    }
    app_session ||--o{ personal_contact : "session_id"
    app_session ||--o{ personal_notebook_entry : "session_id"
    app_session ||--o{ personal_private_region : "session_id"
    app_session ||--o{ personal_share_draft : "session_id"
```

### 공개 자료와 근거

```mermaid
erDiagram
    public_station {
        text station_id PK
        text source_id
        text station_code
        text station_name_raw
        text station_name_normalized
        float8 public_longitude
        float8 public_latitude
        float8 altitude_m
        date valid_from
        date valid_to
        text legal_area_code
        text source_manifest_id
    }
    station_mapping {
        text mapping_id PK
        text from_source
        text from_station_key
        text to_source
        text to_station_key
        date valid_from
        date valid_to
        text mapping_basis
        text verification_status
    }
    observation_value {
        int8 observation_id PK
        text source_id
        text provider_station_key
        date observation_date
        text element
        text raw_value
        numeric normalized_numeric_value
        text unit
        text value_state
        text raw_quality_flag
        timestamptz accumulation_start
        timestamptz accumulation_end
        text accumulation_window
        text manifest_id
        text duplicate_group
        text conflict_group
    }
    forecast_value {
        int8 forecast_id PK
        text source_id
        text grid_id
        timestamptz published_at
        timestamptz target_at
        text element
        text raw_value
        numeric normalized_value
        text unit
        text value_state
        text manifest_id
        text forecast_issue_version
    }
    price_observation {
        int8 price_id PK
        text channel
        text item_code
        text item_name
        text form
        text market_code
        text market_name
        date settlement_date
        text origin_label_raw
        text origin_label_type
        text survey_region
        text survey_grade
        text survey_stage
        date survey_as_of
        text product_option
        numeric net_weight_value
        text net_weight_unit
        numeric price_value
        text currency
        text price_basis
        numeric shipping_value
        text shipping_condition
        numeric coupon_price
        text coupon_condition
        timestamptz checked_at
        text source_url
        text manifest_id
        text comparability_key
        text conversion_rule_id
    }
    source_manifest {
        text manifest_id PK
        text source_id
        text dataset_id
        text operation
        jsonb sanitized_parameters
        jsonb requested_scope
        jsonb fetched_scope
        jsonb failed_scope
        int4 page_number
        int4 page_size
        int4 returned_count
        int4 total_count
        bool has_more
        timestamptz fetched_at
        date verified_on
        jsonb observed_period
        text content_hash
        text parser_version
        text schema_version
        text rights_status
        text transport_status
        text source_mode
    }
    public_evidence {
        text evidence_id PK
        jsonb public_query_spec
        jsonb source_manifest_ids
        jsonb quality_summary
        jsonb effective_scope
        text formula_version
        jsonb result_values
        jsonb input_hashes
        timestamptz created_at
    }
```

### 캐시

```mermaid
erDiagram
    public_source_cache {
        text cache_key PK
        jsonb public_query_spec
        jsonb normalized_result
        jsonb source_manifests
        jsonb observed_period
        text content_hash
        text parser_version
        text schema_version
        text source_version
        timestamptz created_at
        timestamptz valid_until
        timestamptz invalidated_at
        bool quality_passed
        int8 hit_count
        timestamptz last_used_at
    }
    public_response_cache {
        text cache_entry_id PK
        text public_query_text
        text exact_query_hash UK
        text condition_fingerprint
        vector embedding
        text embedding_model
        text embedding_revision
        int4 dimensions
        jsonb public_answer
        jsonb evidence_ids
        jsonb source_versions
        jsonb data_hashes
        text llm_model
        text prompt_version
        text tool_schema_version
        text safety_policy_version
        timestamptz published_at
        jsonb observation_period
        timestamptz source_checked_at
        timestamptz created_at
        timestamptz valid_until
        timestamptz invalidated_at
        bool quality_passed
        bool reusable
        text rights_status
        int4 hit_count
        timestamptz last_used_at
        text answer_hash
    }
```

| 테이블 | 역할 |
| --- | --- |
| app_session | 브라우저 세션. 개인 기록의 소유 단위이며 기본 365일 보관 |
| personal_notebook_entry | 내 수첩 채취 기록(위치·참고 자료 포함) |
| personal_private_region | 관심 장소 핀·방문일·메모 |
| personal_contact | 지인 관계 |
| personal_share_draft | 나눔 기록과 공유 파일 초안 |
| public_station | 공개 관측 지점 카탈로그 |
| station_mapping | 지역 이름과 관측 지점의 연결 |
| observation_value | 관측값(일자료·실황) 정규화 행 |
| forecast_value | 단기예보 정규화 행 |
| price_observation | 가격 정규화 행(소매·조사가·도매) |
| source_manifest | 원천별 취득 시각·버전·쿼터 기록 |
| public_evidence | 조회 결과의 근거(원문 링크·해시·시점) |
| public_source_cache | 기관 조회 결과 캐시(조건 해시 단위) |
| public_response_cache | 대화 응답 캐시. exact 해시와 의미 벡터를 한 행에 저장 |
