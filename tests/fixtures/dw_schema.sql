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
