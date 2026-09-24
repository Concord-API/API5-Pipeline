CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE dw.dim_court (
    court_sk smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    court_code text NOT NULL UNIQUE,
    court_name text NOT NULL,
    state_uf character(2) NOT NULL
);

CREATE TABLE dw.dim_judging_body (
    judging_body_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    court_sk smallint NOT NULL REFERENCES dw.dim_court (court_sk),
    body_name text NOT NULL,
    UNIQUE (court_sk, body_name)
);

CREATE TABLE dw.dim_case_class (
    case_class_sk smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    class_name text NOT NULL UNIQUE,
    claimant_type text,
    CONSTRAINT dim_case_class_claimant_check CHECK (
        claimant_type IS NULL
        OR claimant_type IN ('acusacao', 'fazenda', 'credor', 'defesa', 'autor_particular')
    )
);

CREATE TABLE dw.dim_decision_outcome (
    outcome_sk smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    outcome_code text NOT NULL UNIQUE,
    outcome_label text NOT NULL,
    counts_in_metric boolean NOT NULL DEFAULT true
);

CREATE TABLE dw.dim_case (
    case_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_number text NOT NULL UNIQUE,
    court_sk smallint NOT NULL REFERENCES dw.dim_court (court_sk),
    case_class_sk smallint REFERENCES dw.dim_case_class (case_class_sk),
    court_level text NOT NULL,
    secrecy_level smallint NOT NULL DEFAULT 0,
    filed_at date,
    source text NOT NULL,
    extracted_at timestamp with time zone NOT NULL,
    case_number_formatted text,
    source_link text,
    source_link_type text,
    CONSTRAINT dim_case_court_level_check CHECK (court_level IN ('First', 'Second', 'SpecialCourt', 'AppealPanel')),
    CONSTRAINT dim_case_secrecy_level_check CHECK (secrecy_level BETWEEN 0 AND 5),
    CONSTRAINT dim_case_source_link_pair_check CHECK ((source_link IS NULL) = (source_link_type IS NULL)),
    CONSTRAINT dim_case_source_link_type_check CHECK (source_link_type IS NULL OR source_link_type IN ('direto', 'portal'))
);

CREATE TABLE dw.dim_subject (
    subject_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_name text NOT NULL UNIQUE,
    subject_code integer NOT NULL,
    tpu_area text
);

CREATE TABLE dw.dim_theme (
    theme_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    theme_name text NOT NULL UNIQUE,
    subject_area text,
    label_origin text NOT NULL DEFAULT 'llm_curated',
    embedding_model text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    tpu_area text,
    theme_key bigint NOT NULL,
    CONSTRAINT dim_theme_subject_area_check CHECK (
        subject_area IS NULL
        OR subject_area IN (
            'ADMINISTRATIVO', 'AMBIENTAL', 'BANCARIO', 'CIVIL', 'CONSUMIDOR', 'EMPRESARIAL', 'FAMILIA',
            'IMOBILIARIO', 'PREVIDENCIARIO', 'PROCESSUAL', 'QUANTUM', 'SAUDE', 'TRABALHISTA', 'TRIBUTARIO'
        )
    )
);

CREATE UNIQUE INDEX idx_dim_theme_key ON dw.dim_theme (theme_key);

CREATE TABLE dw.bridge_theme_subject (
    theme_sk bigint NOT NULL REFERENCES dw.dim_theme (theme_sk) ON DELETE CASCADE,
    subject_sk bigint NOT NULL REFERENCES dw.dim_subject (subject_sk),
    PRIMARY KEY (theme_sk, subject_sk)
);

CREATE TABLE dw.bridge_case_subject (
    case_sk bigint NOT NULL REFERENCES dw.dim_case (case_sk),
    subject_sk bigint NOT NULL REFERENCES dw.dim_subject (subject_sk),
    PRIMARY KEY (case_sk, subject_sk)
);

CREATE TABLE dw.dim_movement (
    movement_sk smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    movement_code integer NOT NULL UNIQUE,
    movement_name text NOT NULL,
    outcome_sk smallint NOT NULL REFERENCES dw.dim_decision_outcome (outcome_sk),
    code_verified boolean NOT NULL DEFAULT false,
    polarity_reference text,
    CONSTRAINT dim_movement_polarity_check CHECK (
        polarity_reference IS NULL OR polarity_reference IN ('pretensao_autor', 'pretensao_recorrente')
    ),
    CONSTRAINT dim_movement_verified_needs_polarity CHECK (NOT code_verified OR polarity_reference IS NOT NULL)
);

CREATE TABLE dw.dim_date (
    date_sk integer PRIMARY KEY,
    full_date date NOT NULL UNIQUE,
    year smallint NOT NULL,
    quarter smallint NOT NULL,
    month smallint NOT NULL,
    month_name text NOT NULL,
    day smallint NOT NULL
);

CREATE TABLE dw.fact_case_event (
    event_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_sk bigint NOT NULL REFERENCES dw.dim_case (case_sk),
    court_sk smallint NOT NULL REFERENCES dw.dim_court (court_sk),
    judging_body_sk bigint REFERENCES dw.dim_judging_body (judging_body_sk),
    movement_sk smallint NOT NULL REFERENCES dw.dim_movement (movement_sk),
    date_sk integer REFERENCES dw.dim_date (date_sk),
    occurred_at timestamp with time zone NOT NULL,
    source text NOT NULL DEFAULT 'datajud',
    source_url text NOT NULL,
    extracted_at timestamp with time zone NOT NULL,
    natural_key text NOT NULL UNIQUE
);

CREATE TABLE dw.strength_config (
    id smallint PRIMARY KEY DEFAULT 1,
    weight_agreement real NOT NULL DEFAULT 0.45,
    weight_volume real NOT NULL DEFAULT 0.25,
    weight_coverage real NOT NULL DEFAULT 0.20,
    weight_recency real NOT NULL DEFAULT 0.10,
    volume_saturation integer NOT NULL DEFAULT 300,
    coverage_courts smallint NOT NULL DEFAULT 3,
    reference_year smallint NOT NULL DEFAULT EXTRACT(year FROM now())::smallint,
    methodology_version text NOT NULL,
    min_judged_for_percentage smallint NOT NULL DEFAULT 2,
    CONSTRAINT strength_config_check CHECK (
        abs(weight_agreement + weight_volume + weight_coverage + weight_recency - 1.0) < 0.001
    ),
    CONSTRAINT strength_config_id_check CHECK (id = 1),
    CONSTRAINT strength_config_min_judged_for_percentage_check CHECK (min_judged_for_percentage >= 1)
);

CREATE TABLE dw.search_synonym (
    term text PRIMARY KEY,
    expands_to text NOT NULL,
    note text
);

CREATE MATERIALIZED VIEW dw.case_current_result AS
SELECT DISTINCT ON (f.case_sk)
    f.case_sk,
    f.event_sk,
    m.outcome_sk,
    m.polarity_reference,
    cc.claimant_type,
    f.date_sk,
    f.court_sk,
    f.judging_body_sk
FROM dw.fact_case_event f
JOIN dw.dim_movement m ON m.movement_sk = f.movement_sk
JOIN dw.dim_case c ON c.case_sk = f.case_sk
LEFT JOIN dw.dim_case_class cc ON cc.case_class_sk = c.case_class_sk
JOIN dw.dim_decision_outcome o ON o.outcome_sk = m.outcome_sk
WHERE o.counts_in_metric AND m.code_verified
ORDER BY f.case_sk, f.occurred_at DESC, f.event_sk DESC
WITH NO DATA;

CREATE UNIQUE INDEX idx_case_current_result_case ON dw.case_current_result (case_sk);

CREATE MATERIALIZED VIEW dw.theme_summary AS
WITH agg AS (
    SELECT
        th.theme_sk,
        th.theme_name,
        th.subject_area,
        count(DISTINCT bts.subject_sk) AS subject_count,
        count(DISTINCT bcs.case_sk) AS case_count,
        count(DISTINCT ccr.court_sk) AS court_count,
        count(DISTINCT ccr.case_sk) AS judged_case_count,
        count(DISTINCT ccr.case_sk) FILTER (
            WHERE ccr.polarity_reference = 'pretensao_autor' AND o.outcome_code IN ('Granted', 'PartiallyGranted')
        ) AS claim_upheld_count,
        count(DISTINCT ccr.case_sk) FILTER (
            WHERE ccr.polarity_reference = 'pretensao_autor' AND o.outcome_code = 'Denied'
        ) AS claim_rejected_count,
        count(DISTINCT ccr.case_sk) FILTER (
            WHERE ccr.polarity_reference = 'pretensao_recorrente' AND o.outcome_code IN ('Granted', 'PartiallyGranted')
        ) AS appeal_upheld_count,
        count(DISTINCT ccr.case_sk) FILTER (
            WHERE ccr.polarity_reference = 'pretensao_recorrente' AND o.outcome_code = 'Denied'
        ) AS appeal_rejected_count,
        count(DISTINCT ccr.case_sk) FILTER (WHERE ccr.claimant_type IS NULL) AS unknown_claimant_count,
        min(d.year) AS period_start_year,
        max(d.year) AS period_end_year,
        max(d.full_date) AS last_decision_date
    FROM dw.dim_theme th
    JOIN dw.bridge_theme_subject bts ON bts.theme_sk = th.theme_sk
    JOIN dw.bridge_case_subject bcs ON bcs.subject_sk = bts.subject_sk
    LEFT JOIN dw.case_current_result ccr ON ccr.case_sk = bcs.case_sk
    LEFT JOIN dw.dim_decision_outcome o ON o.outcome_sk = ccr.outcome_sk
    LEFT JOIN dw.dim_date d ON d.date_sk = ccr.date_sk
    GROUP BY th.theme_sk, th.theme_name, th.subject_area
),
claimants AS (
    SELECT
        counts.theme_sk,
        jsonb_object_agg(coalesce(counts.claimant_type, 'desconhecido'), counts.n) AS claimant_breakdown,
        (array_agg(counts.claimant_type ORDER BY counts.n DESC NULLS LAST))[1] AS dominant_claimant
    FROM (
        SELECT bts.theme_sk, ccr.claimant_type, count(DISTINCT ccr.case_sk) AS n
        FROM dw.bridge_theme_subject bts
        JOIN dw.bridge_case_subject bcs ON bcs.subject_sk = bts.subject_sk
        JOIN dw.case_current_result ccr ON ccr.case_sk = bcs.case_sk
        GROUP BY bts.theme_sk, ccr.claimant_type
    ) counts
    GROUP BY counts.theme_sk
)
SELECT
    a.theme_sk,
    a.theme_name,
    a.subject_area,
    a.subject_count,
    a.case_count,
    a.court_count,
    a.judged_case_count,
    a.claim_upheld_count,
    a.claim_rejected_count,
    a.appeal_upheld_count,
    a.appeal_rejected_count,
    a.unknown_claimant_count,
    a.period_start_year,
    a.period_end_year,
    a.last_decision_date,
    c.claimant_breakdown,
    c.dominant_claimant,
    CASE c.dominant_claimant
        WHEN 'acusacao' THEN 'acolhimento da pretensão acusatória (procedência = condenação)'
        WHEN 'fazenda' THEN 'acolhimento da pretensão da Fazenda Pública'
        WHEN 'credor' THEN 'acolhimento da pretensão do credor/exequente'
        WHEN 'defesa' THEN 'acolhimento da pretensão da parte defensiva (embargante/impetrante)'
        WHEN 'autor_particular' THEN 'acolhimento da pretensão do autor'
        ELSE 'acolhimento da pretensão de quem propôs (autor não identificado)'
    END AS claim_polarity_label
FROM agg a
LEFT JOIN claimants c ON c.theme_sk = a.theme_sk
WITH NO DATA;

CREATE UNIQUE INDEX idx_theme_summary_pk ON dw.theme_summary (theme_sk);

CREATE MATERIALIZED VIEW dw.theme_strength AS
WITH base AS (
    SELECT
        s.theme_sk,
        s.theme_name,
        s.subject_area,
        s.court_count AS courts,
        s.last_decision_date,
        extract(year FROM s.last_decision_date)::smallint AS last_decision_year,
        s.dominant_claimant,
        s.claimant_breakdown,
        s.unknown_claimant_count,
        s.claim_upheld_count,
        s.claim_rejected_count,
        s.appeal_upheld_count,
        s.appeal_rejected_count,
        CASE
            WHEN s.claim_upheld_count + s.claim_rejected_count > 0 THEN 'pretensao_autor'
            WHEN s.appeal_upheld_count + s.appeal_rejected_count > 0 THEN 'pretensao_recorrente'
        END AS agreement_basis,
        CASE
            WHEN s.claim_upheld_count + s.claim_rejected_count > 0 THEN s.claim_upheld_count
            WHEN s.appeal_upheld_count + s.appeal_rejected_count > 0 THEN s.appeal_upheld_count
            ELSE 0
        END AS upheld,
        CASE
            WHEN s.claim_upheld_count + s.claim_rejected_count > 0 THEN s.claim_rejected_count
            WHEN s.appeal_upheld_count + s.appeal_rejected_count > 0 THEN s.appeal_rejected_count
            ELSE 0
        END AS rejected,
        CASE
            WHEN s.claim_upheld_count + s.claim_rejected_count > 0 THEN s.claim_polarity_label
            WHEN s.appeal_upheld_count + s.appeal_rejected_count > 0 THEN 'acolhimento da pretensão de quem recorreu'
        END AS claim_polarity_label,
        cfg.weight_agreement,
        cfg.weight_volume,
        cfg.weight_coverage,
        cfg.weight_recency,
        cfg.volume_saturation,
        cfg.coverage_courts,
        cfg.reference_year
    FROM dw.theme_summary s
    CROSS JOIN dw.strength_config cfg
),
components AS (
    SELECT
        b.*,
        (b.upheld + b.rejected) AS judged,
        CASE
            WHEN b.upheld + b.rejected = 0 THEN 0
            ELSE round(greatest(0, (greatest(b.upheld, b.rejected)::numeric / (b.upheld + b.rejected) - 0.5) * 2), 3)
        END AS agreement_value,
        CASE
            WHEN b.upheld + b.rejected = 0 THEN 0
            ELSE round(least(1, log(10::numeric, (b.upheld + b.rejected + 1)::numeric) / log(10::numeric, (b.volume_saturation + 1)::numeric)), 3)
        END AS volume_value,
        round(least(1, b.courts::numeric / b.coverage_courts), 3) AS coverage_value,
        CASE
            WHEN b.last_decision_date IS NULL THEN 0
            WHEN (b.reference_year - b.last_decision_year) <= 1 THEN 1
            WHEN (b.reference_year - b.last_decision_year) >= 6 THEN 0
            ELSE round(1 - ((b.reference_year - b.last_decision_year) - 1) / 5.0, 3)
        END AS recency_value
    FROM base b
),
scored AS (
    SELECT
        c.*,
        round((c.agreement_value * c.weight_agreement
             + c.volume_value * c.weight_volume
             + c.coverage_value * c.weight_coverage
             + c.recency_value * c.weight_recency) * 100)::integer AS score
    FROM components c
)
SELECT
    s.theme_sk,
    s.theme_name,
    s.subject_area,
    s.score,
    CASE
        WHEN s.score >= 90 THEN 'Consolidada'
        WHEN s.score >= 75 THEN 'Dominante'
        WHEN s.score >= 55 THEN 'Em formação'
        ELSE 'Divergente'
    END AS level,
    s.agreement_value,
    s.weight_agreement AS agreement_weight,
    s.volume_value,
    s.weight_volume AS volume_weight,
    s.coverage_value,
    s.weight_coverage AS coverage_weight,
    s.recency_value,
    s.weight_recency AS recency_weight,
    s.agreement_basis,
    s.dominant_claimant,
    s.claim_polarity_label,
    s.claimant_breakdown,
    s.unknown_claimant_count,
    s.judged,
    s.upheld,
    s.rejected,
    s.claim_upheld_count,
    s.claim_rejected_count,
    s.appeal_upheld_count,
    s.appeal_rejected_count,
    s.courts,
    s.last_decision_year,
    s.last_decision_date,
    s.volume_saturation,
    s.coverage_courts,
    s.reference_year
FROM scored s
WITH NO DATA;

CREATE UNIQUE INDEX idx_theme_strength_pk ON dw.theme_strength (theme_sk);
CREATE INDEX idx_theme_strength_score ON dw.theme_strength (score DESC);

CREATE TABLE dw.theme_narrative (
    theme_sk bigint PRIMARY KEY REFERENCES dw.dim_theme (theme_sk),
    lead jsonb NOT NULL,
    body jsonb NOT NULL,
    text_origin text NOT NULL,
    methodology_version text NOT NULL,
    generated_at date NOT NULL,
    CONSTRAINT theme_narrative_text_origin_check CHECK (text_origin IN ('template', 'curated'))
);
