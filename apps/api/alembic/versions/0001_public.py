"""public compartment initial schema (SRS §9)

Revision ID: 0001_public
Revises:
"""

from alembic import op

revision = "0001_public"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public_station (
            station_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            station_code TEXT,
            station_name_raw TEXT NOT NULL,
            station_name_normalized TEXT NOT NULL,
            public_longitude DOUBLE PRECISION,
            public_latitude DOUBLE PRECISION,
            altitude_m DOUBLE PRECISION,
            valid_from DATE,
            valid_to DATE,
            legal_area_code TEXT,
            source_manifest_id TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS station_mapping (
            mapping_id TEXT PRIMARY KEY,
            from_source TEXT NOT NULL,
            from_station_key TEXT NOT NULL,
            to_source TEXT NOT NULL,
            to_station_key TEXT NOT NULL,
            valid_from DATE,
            valid_to DATE,
            mapping_basis TEXT,
            verification_status TEXT NOT NULL DEFAULT 'unverified'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS source_manifest (
            manifest_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            sanitized_parameters JSONB NOT NULL DEFAULT '{}',
            requested_scope JSONB NOT NULL DEFAULT '{}',
            fetched_scope JSONB NOT NULL DEFAULT '{}',
            failed_scope JSONB NOT NULL DEFAULT '{}',
            page_number INTEGER,
            page_size INTEGER,
            returned_count INTEGER,
            total_count INTEGER,
            has_more BOOLEAN,
            fetched_at TIMESTAMPTZ,
            verified_on DATE,
            observed_period JSONB NOT NULL DEFAULT '{}',
            content_hash TEXT,
            parser_version TEXT NOT NULL DEFAULT '1',
            schema_version TEXT NOT NULL DEFAULT '1',
            rights_status TEXT,
            transport_status TEXT,
            source_mode TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS observation_value (
            observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id TEXT NOT NULL,
            provider_station_key TEXT NOT NULL,
            observation_date DATE NOT NULL,
            element TEXT NOT NULL,
            raw_value TEXT,
            normalized_numeric_value NUMERIC,
            unit TEXT,
            value_state TEXT NOT NULL,
            raw_quality_flag TEXT,
            accumulation_start TIMESTAMPTZ,
            accumulation_end TIMESTAMPTZ,
            accumulation_window TEXT NOT NULL DEFAULT '1d',
            manifest_id TEXT,
            duplicate_group TEXT,
            conflict_group TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_observation_lookup
        ON observation_value (source_id, provider_station_key, observation_date, element, accumulation_window)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_value (
            forecast_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id TEXT NOT NULL,
            grid_id TEXT NOT NULL,
            published_at TIMESTAMPTZ NOT NULL,
            target_at TIMESTAMPTZ NOT NULL,
            element TEXT NOT NULL,
            raw_value TEXT,
            normalized_value NUMERIC,
            unit TEXT,
            value_state TEXT NOT NULL,
            manifest_id TEXT,
            forecast_issue_version TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS price_observation (
            price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            channel TEXT NOT NULL,
            item_code TEXT,
            item_name TEXT,
            form TEXT,
            market_code TEXT,
            market_name TEXT,
            settlement_date DATE,
            origin_label_raw TEXT,
            origin_label_type TEXT,
            survey_region TEXT,
            survey_grade TEXT,
            survey_stage TEXT,
            survey_as_of DATE,
            product_option TEXT,
            net_weight_value NUMERIC,
            net_weight_unit TEXT,
            price_value NUMERIC,
            currency TEXT NOT NULL DEFAULT 'KRW',
            price_basis TEXT,
            shipping_value NUMERIC,
            shipping_condition TEXT,
            coupon_price NUMERIC,
            coupon_condition TEXT,
            checked_at TIMESTAMPTZ,
            source_url TEXT,
            manifest_id TEXT,
            comparability_key TEXT,
            conversion_rule_id TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public_evidence (
            evidence_id TEXT PRIMARY KEY,
            public_query_spec JSONB NOT NULL,
            source_manifest_ids JSONB NOT NULL DEFAULT '[]',
            quality_summary JSONB NOT NULL DEFAULT '{}',
            effective_scope JSONB NOT NULL DEFAULT '{}',
            formula_version TEXT NOT NULL,
            result_values JSONB NOT NULL,
            input_hashes JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public_response_cache (
            cache_entry_id TEXT PRIMARY KEY,
            public_query_text TEXT NOT NULL,
            exact_query_hash TEXT NOT NULL UNIQUE,
            condition_fingerprint TEXT NOT NULL,
            embedding vector(384),
            embedding_model TEXT NOT NULL,
            embedding_revision TEXT NOT NULL,
            dimensions INTEGER NOT NULL DEFAULT 384,
            public_answer JSONB NOT NULL,
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            source_versions JSONB NOT NULL DEFAULT '{}',
            data_hashes JSONB NOT NULL DEFAULT '[]',
            llm_model TEXT,
            prompt_version TEXT,
            tool_schema_version TEXT,
            safety_policy_version TEXT,
            published_at TIMESTAMPTZ,
            observation_period JSONB NOT NULL DEFAULT '{}',
            source_checked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            valid_until TIMESTAMPTZ NOT NULL,
            invalidated_at TIMESTAMPTZ,
            quality_passed BOOLEAN NOT NULL DEFAULT false,
            reusable BOOLEAN NOT NULL DEFAULT false,
            rights_status TEXT,
            hit_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cache_fingerprint
        ON public_response_cache (condition_fingerprint, valid_until)
        WHERE reusable = true AND invalidated_at IS NULL
        """
    )


def downgrade() -> None:
    for table in (
        "public_response_cache",
        "public_evidence",
        "price_observation",
        "forecast_value",
        "observation_value",
        "source_manifest",
        "station_mapping",
        "public_station",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
