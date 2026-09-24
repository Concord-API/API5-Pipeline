--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: dw; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA dw;


--
-- Name: expand_query(text); Type: FUNCTION; Schema: dw; Owner: -
--

CREATE FUNCTION dw.expand_query(p_query text) RETURNS text
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
    SELECT btrim(coalesce((
        SELECT string_agg(coalesce(s.expands_to, w.tok), ' ' ORDER BY w.ord)
        FROM unnest(regexp_split_to_array(dw.norm_pt(coalesce(p_query, '')), '\s+'))
             WITH ORDINALITY AS w(tok, ord)
        LEFT JOIN dw.search_synonym s ON s.term = w.tok
    ), ''))
$$;


--
-- Name: norm_pt(text); Type: FUNCTION; Schema: dw; Owner: -
--

CREATE FUNCTION dw.norm_pt(txt text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$ SELECT lower(public.unaccent('public.unaccent'::regdictionary, txt)) $$;


--
-- Name: search_themes(text, integer); Type: FUNCTION; Schema: dw; Owner: -
--

CREATE FUNCTION dw.search_themes(p_query text, p_limit integer DEFAULT 20) RETURNS TABLE(theme_key bigint, theme_name text, subject_area text, rank real, "position" bigint)
    LANGUAGE sql STABLE STRICT PARALLEL SAFE
    AS $$
    WITH ranked AS (
        SELECT t.theme_sk,
               t.theme_key,
               t.theme_name,
               t.subject_area,
               greatest(
                   ts_rank(t.search_vector, websearch_to_tsquery('dw.pt_unaccent'::regconfig, dw.expand_query(p_query))) * 10,
                   word_similarity(dw.norm_pt(p_query), t.theme_name_norm)
               ) AS rank
        FROM dw.dim_theme t
    )
    SELECT r.theme_key,
           r.theme_name,
           r.subject_area,
           r.rank,
           row_number() OVER (ORDER BY ts.score DESC, ts.judged DESC, r.theme_name) AS position
    FROM ranked r
    JOIN dw.theme_summary s ON s.theme_sk = r.theme_sk
    JOIN dw.theme_strength ts ON ts.theme_sk = r.theme_sk
    WHERE r.rank >= 0.5
      AND s.judged_case_count > 0
    ORDER BY position
    LIMIT p_limit
$$;


--
-- Name: top_themes(integer); Type: FUNCTION; Schema: dw; Owner: -
--

CREATE FUNCTION dw.top_themes(p_limit integer DEFAULT 20) RETURNS TABLE(theme_key bigint, theme_name text, subject_area text, rank real, "position" bigint)
    LANGUAGE sql STABLE STRICT PARALLEL SAFE
    AS $$
    SELECT t.theme_key,
           t.theme_name,
           t.subject_area,
           NULL::real AS rank,
           row_number() OVER (ORDER BY coalesce(ts.judged, 0) DESC, t.theme_name) AS position
    FROM dw.dim_theme t
    JOIN dw.theme_summary s ON s.theme_sk = t.theme_sk
    LEFT JOIN dw.theme_strength ts ON ts.theme_sk = t.theme_sk
    WHERE s.judged_case_count > 0
    ORDER BY position
    LIMIT p_limit
$$;


--
-- Name: pt_unaccent; Type: TEXT SEARCH CONFIGURATION; Schema: dw; Owner: -
--

CREATE TEXT SEARCH CONFIGURATION dw.pt_unaccent (
    PARSER = pg_catalog."default" );

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR asciiword WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR word WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR numword WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR email WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR url WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR host WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR sfloat WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR version WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR hword_numpart WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR hword_part WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR hword_asciipart WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR numhword WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR asciihword WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR hword WITH public.unaccent, portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR url_path WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR file WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR "float" WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR "int" WITH simple;

ALTER TEXT SEARCH CONFIGURATION dw.pt_unaccent
    ADD MAPPING FOR uint WITH simple;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bridge_case_subject; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.bridge_case_subject (
    case_sk bigint NOT NULL,
    subject_sk bigint NOT NULL
);


--
-- Name: bridge_subject_doctrine; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.bridge_subject_doctrine (
    subject_sk bigint NOT NULL,
    doctrine_sk bigint NOT NULL,
    link_method text NOT NULL,
    similarity real,
    embedding_model text
);


--
-- Name: bridge_theme_subject; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.bridge_theme_subject (
    theme_sk bigint NOT NULL,
    subject_sk bigint NOT NULL
);


--
-- Name: dim_case; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_case (
    case_sk bigint NOT NULL,
    case_number text NOT NULL,
    court_sk smallint NOT NULL,
    case_class_sk smallint,
    court_level text NOT NULL,
    secrecy_level smallint DEFAULT 0 NOT NULL,
    filed_at date,
    source text NOT NULL,
    extracted_at timestamp with time zone NOT NULL,
    case_number_formatted text,
    source_link text,
    source_link_type text,
    CONSTRAINT dim_case_court_level_check CHECK ((court_level = ANY (ARRAY['First'::text, 'Second'::text, 'SpecialCourt'::text, 'AppealPanel'::text]))),
    CONSTRAINT dim_case_secrecy_level_check CHECK (((secrecy_level >= 0) AND (secrecy_level <= 5))),
    CONSTRAINT dim_case_source_link_pair_check CHECK (((source_link IS NULL) = (source_link_type IS NULL))),
    CONSTRAINT dim_case_source_link_type_check CHECK (((source_link_type IS NULL) OR (source_link_type = ANY (ARRAY['direto'::text, 'portal'::text]))))
);


--
-- Name: dim_case_class; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_case_class (
    case_class_sk smallint NOT NULL,
    class_name text NOT NULL,
    claimant_type text,
    CONSTRAINT dim_case_class_claimant_check CHECK (((claimant_type IS NULL) OR (claimant_type = ANY (ARRAY['acusacao'::text, 'fazenda'::text, 'credor'::text, 'defesa'::text, 'autor_particular'::text]))))
);


--
-- Name: dim_decision_outcome; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_decision_outcome (
    outcome_sk smallint NOT NULL,
    outcome_code text NOT NULL,
    outcome_label text NOT NULL,
    counts_in_metric boolean DEFAULT true NOT NULL
);


--
-- Name: dim_movement; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_movement (
    movement_sk smallint NOT NULL,
    movement_code integer NOT NULL,
    movement_name text NOT NULL,
    outcome_sk smallint NOT NULL,
    code_verified boolean DEFAULT false NOT NULL,
    polarity_reference text,
    CONSTRAINT dim_movement_polarity_check CHECK (((polarity_reference IS NULL) OR (polarity_reference = ANY (ARRAY['pretensao_autor'::text, 'pretensao_recorrente'::text])))),
    CONSTRAINT dim_movement_verified_needs_polarity CHECK (((NOT code_verified) OR (polarity_reference IS NOT NULL)))
);


--
-- Name: fact_case_event; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.fact_case_event (
    event_sk bigint NOT NULL,
    case_sk bigint NOT NULL,
    court_sk smallint NOT NULL,
    judging_body_sk bigint,
    movement_sk smallint NOT NULL,
    date_sk integer,
    occurred_at timestamp with time zone NOT NULL,
    source text DEFAULT 'datajud'::text NOT NULL,
    source_url text NOT NULL,
    extracted_at timestamp with time zone NOT NULL,
    natural_key text NOT NULL
);


--
-- Name: case_current_result; Type: MATERIALIZED VIEW; Schema: dw; Owner: -
--

CREATE MATERIALIZED VIEW dw.case_current_result AS
 SELECT DISTINCT ON (f.case_sk) f.case_sk,
    f.event_sk,
    m.outcome_sk,
    m.polarity_reference,
    cc.claimant_type,
    f.date_sk,
    f.court_sk,
    f.judging_body_sk
   FROM ((((dw.fact_case_event f
     JOIN dw.dim_movement m ON ((m.movement_sk = f.movement_sk)))
     JOIN dw.dim_case c ON ((c.case_sk = f.case_sk)))
     LEFT JOIN dw.dim_case_class cc ON ((cc.case_class_sk = c.case_class_sk)))
     JOIN dw.dim_decision_outcome o ON ((o.outcome_sk = m.outcome_sk)))
  WHERE (o.counts_in_metric AND m.code_verified)
  ORDER BY f.case_sk, f.occurred_at DESC, f.event_sk DESC
  WITH NO DATA;


--
-- Name: dim_doctrine; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_doctrine (
    doctrine_sk bigint NOT NULL,
    title text NOT NULL,
    authors text,
    journal_name text,
    publication_year smallint,
    doi text,
    article_url text,
    subject_area text,
    source text NOT NULL,
    extracted_at timestamp with time zone NOT NULL,
    CONSTRAINT dim_doctrine_check CHECK (((doi IS NOT NULL) OR (article_url IS NOT NULL)))
);


--
-- Name: data_provenance; Type: MATERIALIZED VIEW; Schema: dw; Owner: -
--

CREATE MATERIALIZED VIEW dw.data_provenance AS
 SELECT 'cases'::text AS block,
    fact_case_event.source,
    max(fact_case_event.extracted_at) AS extracted_at,
    count(DISTINCT fact_case_event.case_sk) AS row_count
   FROM dw.fact_case_event
  GROUP BY fact_case_event.source
UNION ALL
 SELECT 'doctrine'::text AS block,
    dim_doctrine.source,
    max(dim_doctrine.extracted_at) AS extracted_at,
    count(*) AS row_count
   FROM dw.dim_doctrine
  GROUP BY dim_doctrine.source
  WITH NO DATA;


--
-- Name: dim_case_case_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_case ALTER COLUMN case_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_case_case_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_case_class_case_class_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_case_class ALTER COLUMN case_class_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_case_class_case_class_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_court; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_court (
    court_sk smallint NOT NULL,
    court_code text NOT NULL,
    court_name text NOT NULL,
    state_uf character(2) NOT NULL
);


--
-- Name: dim_court_court_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_court ALTER COLUMN court_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_court_court_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_date; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_date (
    date_sk integer NOT NULL,
    full_date date NOT NULL,
    year smallint NOT NULL,
    quarter smallint NOT NULL,
    month smallint NOT NULL,
    month_name text NOT NULL,
    day smallint NOT NULL
);


--
-- Name: dim_decision_outcome_outcome_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_decision_outcome ALTER COLUMN outcome_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_decision_outcome_outcome_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_doctrine_doctrine_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_doctrine ALTER COLUMN doctrine_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_doctrine_doctrine_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_judging_body; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_judging_body (
    judging_body_sk bigint NOT NULL,
    court_sk smallint NOT NULL,
    body_name text NOT NULL
);


--
-- Name: dim_judging_body_judging_body_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_judging_body ALTER COLUMN judging_body_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_judging_body_judging_body_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_movement_movement_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_movement ALTER COLUMN movement_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_movement_movement_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_subject; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_subject (
    subject_sk bigint NOT NULL,
    subject_name text NOT NULL,
    subject_code integer NOT NULL,
    tpu_area text
);


--
-- Name: dim_subject_subject_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_subject ALTER COLUMN subject_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_subject_subject_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: dim_theme; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.dim_theme (
    theme_sk bigint NOT NULL,
    theme_name text NOT NULL,
    subject_area text,
    label_origin text DEFAULT 'llm_curated'::text NOT NULL,
    embedding_model text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tpu_area text,
    theme_key bigint NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('dw.pt_unaccent'::regconfig, theme_name)) STORED,
    theme_name_norm text GENERATED ALWAYS AS (dw.norm_pt(theme_name)) STORED,
    CONSTRAINT dim_theme_subject_area_check CHECK (((subject_area IS NULL) OR (subject_area = ANY (ARRAY['ADMINISTRATIVO'::text, 'AMBIENTAL'::text, 'BANCARIO'::text, 'CIVIL'::text, 'CONSUMIDOR'::text, 'EMPRESARIAL'::text, 'FAMILIA'::text, 'IMOBILIARIO'::text, 'PREVIDENCIARIO'::text, 'PROCESSUAL'::text, 'QUANTUM'::text, 'SAUDE'::text, 'TRABALHISTA'::text, 'TRIBUTARIO'::text]))))
);


--
-- Name: dim_theme_theme_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.dim_theme ALTER COLUMN theme_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.dim_theme_theme_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: fact_case_event_event_sk_seq; Type: SEQUENCE; Schema: dw; Owner: -
--

ALTER TABLE dw.fact_case_event ALTER COLUMN event_sk ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME dw.fact_case_event_event_sk_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: search_synonym; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.search_synonym (
    term text NOT NULL,
    expands_to text NOT NULL,
    note text
);


--
-- Name: strength_config; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.strength_config (
    id smallint DEFAULT 1 NOT NULL,
    weight_agreement real DEFAULT 0.45 NOT NULL,
    weight_volume real DEFAULT 0.25 NOT NULL,
    weight_coverage real DEFAULT 0.20 NOT NULL,
    weight_recency real DEFAULT 0.10 NOT NULL,
    volume_saturation integer DEFAULT 300 NOT NULL,
    coverage_courts smallint DEFAULT 3 NOT NULL,
    reference_year smallint DEFAULT (EXTRACT(year FROM now()))::smallint NOT NULL,
    methodology_version text NOT NULL,
    min_judged_for_percentage smallint DEFAULT 2 NOT NULL,
    CONSTRAINT strength_config_check CHECK ((abs(((((weight_agreement + weight_volume) + weight_coverage) + weight_recency) - (1.0)::double precision)) < (0.001)::double precision)),
    CONSTRAINT strength_config_id_check CHECK ((id = 1)),
    CONSTRAINT strength_config_min_judged_for_percentage_check CHECK ((min_judged_for_percentage >= 1))
);


--
-- Name: theme_narrative; Type: TABLE; Schema: dw; Owner: -
--

CREATE TABLE dw.theme_narrative (
    theme_sk bigint NOT NULL,
    lead jsonb NOT NULL,
    body jsonb NOT NULL,
    text_origin text NOT NULL,
    methodology_version text NOT NULL,
    generated_at date NOT NULL,
    CONSTRAINT theme_narrative_text_origin_check CHECK ((text_origin = ANY (ARRAY['template'::text, 'curated'::text])))
);


--
-- Name: theme_provenance; Type: VIEW; Schema: dw; Owner: -
--

CREATE VIEW dw.theme_provenance AS
 WITH theme_cases AS (
         SELECT DISTINCT bts.theme_sk,
            bcs.case_sk
           FROM (dw.bridge_theme_subject bts
             JOIN dw.bridge_case_subject bcs ON ((bcs.subject_sk = bts.subject_sk)))
        ), theme_doctrine AS (
         SELECT DISTINCT bts.theme_sk,
            bsd.doctrine_sk
           FROM (dw.bridge_theme_subject bts
             JOIN dw.bridge_subject_doctrine bsd ON ((bsd.subject_sk = bts.subject_sk)))
        ), sources AS (
         SELECT tc.theme_sk,
            'cases'::text AS block,
            f.source,
            max(f.extracted_at) AS extracted_at,
            count(DISTINCT f.case_sk) AS row_count
           FROM (theme_cases tc
             JOIN dw.fact_case_event f ON ((f.case_sk = tc.case_sk)))
          GROUP BY tc.theme_sk, f.source
        UNION ALL
         SELECT td.theme_sk,
            'doctrine'::text AS block,
            d.source,
            max(d.extracted_at) AS extracted_at,
            count(*) AS row_count
           FROM (theme_doctrine td
             JOIN dw.dim_doctrine d ON ((d.doctrine_sk = td.doctrine_sk)))
          GROUP BY td.theme_sk, d.source
        )
 SELECT s.theme_sk,
    s.block,
    s.source,
    s.extracted_at,
    s.row_count,
    cfg.methodology_version
   FROM (sources s
     LEFT JOIN dw.strength_config cfg ON (true));


--
-- Name: theme_summary; Type: MATERIALIZED VIEW; Schema: dw; Owner: -
--

CREATE MATERIALIZED VIEW dw.theme_summary AS
 WITH agg AS (
         SELECT th.theme_sk,
            th.theme_name,
            th.subject_area,
            count(DISTINCT bts.subject_sk) AS subject_count,
            count(DISTINCT bcs.case_sk) AS case_count,
            count(DISTINCT ccr.court_sk) AS court_count,
            count(DISTINCT ccr.case_sk) AS judged_case_count,
            count(DISTINCT ccr.case_sk) FILTER (WHERE ((ccr.polarity_reference = 'pretensao_autor'::text) AND (o.outcome_code = ANY (ARRAY['Granted'::text, 'PartiallyGranted'::text])))) AS claim_upheld_count,
            count(DISTINCT ccr.case_sk) FILTER (WHERE ((ccr.polarity_reference = 'pretensao_autor'::text) AND (o.outcome_code = 'Denied'::text))) AS claim_rejected_count,
            count(DISTINCT ccr.case_sk) FILTER (WHERE ((ccr.polarity_reference = 'pretensao_recorrente'::text) AND (o.outcome_code = ANY (ARRAY['Granted'::text, 'PartiallyGranted'::text])))) AS appeal_upheld_count,
            count(DISTINCT ccr.case_sk) FILTER (WHERE ((ccr.polarity_reference = 'pretensao_recorrente'::text) AND (o.outcome_code = 'Denied'::text))) AS appeal_rejected_count,
            count(DISTINCT ccr.case_sk) FILTER (WHERE (ccr.claimant_type IS NULL)) AS unknown_claimant_count,
            min(d.year) AS period_start_year,
            max(d.year) AS period_end_year,
            max(d.full_date) AS last_decision_date
           FROM (((((dw.dim_theme th
             JOIN dw.bridge_theme_subject bts ON ((bts.theme_sk = th.theme_sk)))
             JOIN dw.bridge_case_subject bcs ON ((bcs.subject_sk = bts.subject_sk)))
             LEFT JOIN dw.case_current_result ccr ON ((ccr.case_sk = bcs.case_sk)))
             LEFT JOIN dw.dim_decision_outcome o ON ((o.outcome_sk = ccr.outcome_sk)))
             LEFT JOIN dw.dim_date d ON ((d.date_sk = ccr.date_sk)))
          GROUP BY th.theme_sk, th.theme_name, th.subject_area
        ), claimants AS (
         SELECT counts.theme_sk,
            jsonb_object_agg(COALESCE(counts.claimant_type, 'desconhecido'::text), counts.n) AS claimant_breakdown,
            (array_agg(counts.claimant_type ORDER BY counts.n DESC NULLS LAST))[1] AS dominant_claimant
           FROM ( SELECT bts.theme_sk,
                    ccr.claimant_type,
                    count(DISTINCT ccr.case_sk) AS n
                   FROM ((dw.bridge_theme_subject bts
                     JOIN dw.bridge_case_subject bcs ON ((bcs.subject_sk = bts.subject_sk)))
                     JOIN dw.case_current_result ccr ON ((ccr.case_sk = bcs.case_sk)))
                  GROUP BY bts.theme_sk, ccr.claimant_type) counts
          GROUP BY counts.theme_sk
        )
 SELECT a.theme_sk,
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
            WHEN 'acusacao'::text THEN 'acolhimento da pretensão acusatória (procedência = condenação)'::text
            WHEN 'fazenda'::text THEN 'acolhimento da pretensão da Fazenda Pública'::text
            WHEN 'credor'::text THEN 'acolhimento da pretensão do credor/exequente'::text
            WHEN 'defesa'::text THEN 'acolhimento da pretensão da parte defensiva (embargante/impetrante)'::text
            WHEN 'autor_particular'::text THEN 'acolhimento da pretensão do autor'::text
            ELSE 'acolhimento da pretensão de quem propôs (autor não identificado)'::text
        END AS claim_polarity_label
   FROM (agg a
     LEFT JOIN claimants c ON ((c.theme_sk = a.theme_sk)))
  WITH NO DATA;


--
-- Name: theme_strength; Type: MATERIALIZED VIEW; Schema: dw; Owner: -
--

CREATE MATERIALIZED VIEW dw.theme_strength AS
 WITH base AS (
         SELECT s_1.theme_sk,
            s_1.theme_name,
            s_1.subject_area,
            s_1.court_count AS courts,
            s_1.last_decision_date,
            (EXTRACT(year FROM s_1.last_decision_date))::smallint AS last_decision_year,
            s_1.dominant_claimant,
            s_1.claimant_breakdown,
            s_1.unknown_claimant_count,
            s_1.claim_upheld_count,
            s_1.claim_rejected_count,
            s_1.appeal_upheld_count,
            s_1.appeal_rejected_count,
                CASE
                    WHEN ((s_1.claim_upheld_count + s_1.claim_rejected_count) > 0) THEN 'pretensao_autor'::text
                    WHEN ((s_1.appeal_upheld_count + s_1.appeal_rejected_count) > 0) THEN 'pretensao_recorrente'::text
                    ELSE NULL::text
                END AS agreement_basis,
                CASE
                    WHEN ((s_1.claim_upheld_count + s_1.claim_rejected_count) > 0) THEN s_1.claim_upheld_count
                    WHEN ((s_1.appeal_upheld_count + s_1.appeal_rejected_count) > 0) THEN s_1.appeal_upheld_count
                    ELSE (0)::bigint
                END AS upheld,
                CASE
                    WHEN ((s_1.claim_upheld_count + s_1.claim_rejected_count) > 0) THEN s_1.claim_rejected_count
                    WHEN ((s_1.appeal_upheld_count + s_1.appeal_rejected_count) > 0) THEN s_1.appeal_rejected_count
                    ELSE (0)::bigint
                END AS rejected,
                CASE
                    WHEN ((s_1.claim_upheld_count + s_1.claim_rejected_count) > 0) THEN s_1.claim_polarity_label
                    WHEN ((s_1.appeal_upheld_count + s_1.appeal_rejected_count) > 0) THEN 'acolhimento da pretensão de quem recorreu'::text
                    ELSE NULL::text
                END AS claim_polarity_label,
            cfg.weight_agreement,
            cfg.weight_volume,
            cfg.weight_coverage,
            cfg.weight_recency,
            cfg.volume_saturation,
            cfg.coverage_courts,
            cfg.reference_year
           FROM (dw.theme_summary s_1
             CROSS JOIN dw.strength_config cfg)
        ), components AS (
         SELECT b.theme_sk,
            b.theme_name,
            b.subject_area,
            b.courts,
            b.last_decision_date,
            b.last_decision_year,
            b.dominant_claimant,
            b.claimant_breakdown,
            b.unknown_claimant_count,
            b.claim_upheld_count,
            b.claim_rejected_count,
            b.appeal_upheld_count,
            b.appeal_rejected_count,
            b.agreement_basis,
            b.upheld,
            b.rejected,
            b.claim_polarity_label,
            b.weight_agreement,
            b.weight_volume,
            b.weight_coverage,
            b.weight_recency,
            b.volume_saturation,
            b.coverage_courts,
            b.reference_year,
            (b.upheld + b.rejected) AS judged,
                CASE
                    WHEN ((b.upheld + b.rejected) = 0) THEN (0)::numeric
                    ELSE round(GREATEST((0)::numeric, ((((GREATEST(b.upheld, b.rejected))::numeric / ((b.upheld + b.rejected))::numeric) - 0.5) * (2)::numeric)), 3)
                END AS agreement_value,
                CASE
                    WHEN ((b.upheld + b.rejected) = 0) THEN (0)::numeric
                    ELSE round(LEAST((1)::numeric, (log((10)::numeric, (((b.upheld + b.rejected) + 1))::numeric) / log((10)::numeric, ((b.volume_saturation + 1))::numeric))), 3)
                END AS volume_value,
            round(LEAST((1)::numeric, ((b.courts)::numeric / (b.coverage_courts)::numeric)), 3) AS coverage_value,
                CASE
                    WHEN (b.last_decision_date IS NULL) THEN (0)::numeric
                    WHEN ((b.reference_year - b.last_decision_year) <= 1) THEN (1)::numeric
                    WHEN ((b.reference_year - b.last_decision_year) >= 6) THEN (0)::numeric
                    ELSE round(((1)::numeric - ((((b.reference_year - b.last_decision_year) - 1))::numeric / 5.0)), 3)
                END AS recency_value
           FROM base b
        ), scored AS (
         SELECT c.theme_sk,
            c.theme_name,
            c.subject_area,
            c.courts,
            c.last_decision_date,
            c.last_decision_year,
            c.dominant_claimant,
            c.claimant_breakdown,
            c.unknown_claimant_count,
            c.claim_upheld_count,
            c.claim_rejected_count,
            c.appeal_upheld_count,
            c.appeal_rejected_count,
            c.agreement_basis,
            c.upheld,
            c.rejected,
            c.claim_polarity_label,
            c.weight_agreement,
            c.weight_volume,
            c.weight_coverage,
            c.weight_recency,
            c.volume_saturation,
            c.coverage_courts,
            c.reference_year,
            c.judged,
            c.agreement_value,
            c.volume_value,
            c.coverage_value,
            c.recency_value,
            (round(((((((c.agreement_value)::double precision * c.weight_agreement) + ((c.volume_value)::double precision * c.weight_volume)) + ((c.coverage_value)::double precision * c.weight_coverage)) + ((c.recency_value)::double precision * c.weight_recency)) * (100)::double precision)))::integer AS score
           FROM components c
        )
 SELECT theme_sk,
    theme_name,
    subject_area,
    score,
        CASE
            WHEN (score >= 90) THEN 'Consolidada'::text
            WHEN (score >= 75) THEN 'Dominante'::text
            WHEN (score >= 55) THEN 'Em formação'::text
            ELSE 'Divergente'::text
        END AS level,
    agreement_value,
    weight_agreement AS agreement_weight,
    volume_value,
    weight_volume AS volume_weight,
    coverage_value,
    weight_coverage AS coverage_weight,
    recency_value,
    weight_recency AS recency_weight,
    agreement_basis,
    dominant_claimant,
    claim_polarity_label,
    claimant_breakdown,
    unknown_claimant_count,
    judged,
    upheld,
    rejected,
    claim_upheld_count,
    claim_rejected_count,
    appeal_upheld_count,
    appeal_rejected_count,
    courts,
    last_decision_year,
    last_decision_date,
    volume_saturation,
    coverage_courts,
    reference_year
   FROM scored s
  WITH NO DATA;


--
-- Name: bridge_case_subject bridge_case_subject_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_case_subject
    ADD CONSTRAINT bridge_case_subject_pkey PRIMARY KEY (case_sk, subject_sk);


--
-- Name: bridge_subject_doctrine bridge_subject_doctrine_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_subject_doctrine
    ADD CONSTRAINT bridge_subject_doctrine_pkey PRIMARY KEY (subject_sk, doctrine_sk);


--
-- Name: bridge_theme_subject bridge_theme_subject_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_theme_subject
    ADD CONSTRAINT bridge_theme_subject_pkey PRIMARY KEY (theme_sk, subject_sk);


--
-- Name: dim_case dim_case_case_number_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_case
    ADD CONSTRAINT dim_case_case_number_key UNIQUE (case_number);


--
-- Name: dim_case_class dim_case_class_class_name_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_case_class
    ADD CONSTRAINT dim_case_class_class_name_key UNIQUE (class_name);


--
-- Name: dim_case_class dim_case_class_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_case_class
    ADD CONSTRAINT dim_case_class_pkey PRIMARY KEY (case_class_sk);


--
-- Name: dim_case dim_case_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_case
    ADD CONSTRAINT dim_case_pkey PRIMARY KEY (case_sk);


--
-- Name: dim_court dim_court_court_code_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_court
    ADD CONSTRAINT dim_court_court_code_key UNIQUE (court_code);


--
-- Name: dim_court dim_court_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_court
    ADD CONSTRAINT dim_court_pkey PRIMARY KEY (court_sk);


--
-- Name: dim_date dim_date_full_date_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_date
    ADD CONSTRAINT dim_date_full_date_key UNIQUE (full_date);


--
-- Name: dim_date dim_date_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_date
    ADD CONSTRAINT dim_date_pkey PRIMARY KEY (date_sk);


--
-- Name: dim_decision_outcome dim_decision_outcome_outcome_code_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_decision_outcome
    ADD CONSTRAINT dim_decision_outcome_outcome_code_key UNIQUE (outcome_code);


--
-- Name: dim_decision_outcome dim_decision_outcome_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_decision_outcome
    ADD CONSTRAINT dim_decision_outcome_pkey PRIMARY KEY (outcome_sk);


--
-- Name: dim_doctrine dim_doctrine_doi_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_doctrine
    ADD CONSTRAINT dim_doctrine_doi_key UNIQUE (doi);


--
-- Name: dim_doctrine dim_doctrine_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_doctrine
    ADD CONSTRAINT dim_doctrine_pkey PRIMARY KEY (doctrine_sk);


--
-- Name: dim_doctrine dim_doctrine_source_url_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_doctrine
    ADD CONSTRAINT dim_doctrine_source_url_key UNIQUE (source, article_url);


--
-- Name: dim_judging_body dim_judging_body_court_sk_body_name_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_judging_body
    ADD CONSTRAINT dim_judging_body_court_sk_body_name_key UNIQUE (court_sk, body_name);


--
-- Name: dim_judging_body dim_judging_body_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_judging_body
    ADD CONSTRAINT dim_judging_body_pkey PRIMARY KEY (judging_body_sk);


--
-- Name: dim_movement dim_movement_movement_code_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_movement
    ADD CONSTRAINT dim_movement_movement_code_key UNIQUE (movement_code);


--
-- Name: dim_movement dim_movement_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_movement
    ADD CONSTRAINT dim_movement_pkey PRIMARY KEY (movement_sk);


--
-- Name: dim_subject dim_subject_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_subject
    ADD CONSTRAINT dim_subject_pkey PRIMARY KEY (subject_sk);


--
-- Name: dim_subject dim_subject_subject_name_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_subject
    ADD CONSTRAINT dim_subject_subject_name_key UNIQUE (subject_name);


--
-- Name: dim_theme dim_theme_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_theme
    ADD CONSTRAINT dim_theme_pkey PRIMARY KEY (theme_sk);


--
-- Name: dim_theme dim_theme_theme_name_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_theme
    ADD CONSTRAINT dim_theme_theme_name_key UNIQUE (theme_name);


--
-- Name: fact_case_event fact_case_event_natural_key_key; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_natural_key_key UNIQUE (natural_key);


--
-- Name: fact_case_event fact_case_event_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_pkey PRIMARY KEY (event_sk);


--
-- Name: search_synonym search_synonym_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.search_synonym
    ADD CONSTRAINT search_synonym_pkey PRIMARY KEY (term);


--
-- Name: strength_config strength_config_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.strength_config
    ADD CONSTRAINT strength_config_pkey PRIMARY KEY (id);


--
-- Name: theme_narrative theme_narrative_pkey; Type: CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.theme_narrative
    ADD CONSTRAINT theme_narrative_pkey PRIMARY KEY (theme_sk);


--
-- Name: idx_bridge_case_subject_subject; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_bridge_case_subject_subject ON dw.bridge_case_subject USING btree (subject_sk);


--
-- Name: idx_bridge_theme_subject_subject; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_bridge_theme_subject_subject ON dw.bridge_theme_subject USING btree (subject_sk);


--
-- Name: idx_case_current_result_case; Type: INDEX; Schema: dw; Owner: -
--

CREATE UNIQUE INDEX idx_case_current_result_case ON dw.case_current_result USING btree (case_sk);


--
-- Name: idx_case_current_result_polarity; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_case_current_result_polarity ON dw.case_current_result USING btree (polarity_reference);


--
-- Name: idx_data_provenance_pk; Type: INDEX; Schema: dw; Owner: -
--

CREATE UNIQUE INDEX idx_data_provenance_pk ON dw.data_provenance USING btree (block, source);


--
-- Name: idx_dim_case_source_link_type; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_dim_case_source_link_type ON dw.dim_case USING btree (source_link_type);


--
-- Name: idx_dim_subject_subject_code; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_dim_subject_subject_code ON dw.dim_subject USING btree (subject_code);


--
-- Name: idx_dim_subject_tpu_area; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_dim_subject_tpu_area ON dw.dim_subject USING btree (tpu_area);


--
-- Name: idx_dim_theme_fts; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_dim_theme_fts ON dw.dim_theme USING gin (search_vector);


--
-- Name: idx_dim_theme_key; Type: INDEX; Schema: dw; Owner: -
--

CREATE UNIQUE INDEX idx_dim_theme_key ON dw.dim_theme USING btree (theme_key);


--
-- Name: idx_dim_theme_name_trgm; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_dim_theme_name_trgm ON dw.dim_theme USING gin (theme_name_norm public.gin_trgm_ops);


--
-- Name: idx_fact_case_event_case; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_fact_case_event_case ON dw.fact_case_event USING btree (case_sk);


--
-- Name: idx_fact_case_event_court; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_fact_case_event_court ON dw.fact_case_event USING btree (court_sk);


--
-- Name: idx_fact_case_event_date; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_fact_case_event_date ON dw.fact_case_event USING btree (date_sk);


--
-- Name: idx_fact_case_event_extracted_at; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_fact_case_event_extracted_at ON dw.fact_case_event USING btree (extracted_at);


--
-- Name: idx_fact_case_event_movement; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_fact_case_event_movement ON dw.fact_case_event USING btree (movement_sk);


--
-- Name: idx_theme_strength_pk; Type: INDEX; Schema: dw; Owner: -
--

CREATE UNIQUE INDEX idx_theme_strength_pk ON dw.theme_strength USING btree (theme_sk);


--
-- Name: idx_theme_strength_score; Type: INDEX; Schema: dw; Owner: -
--

CREATE INDEX idx_theme_strength_score ON dw.theme_strength USING btree (score DESC);


--
-- Name: idx_theme_summary_pk; Type: INDEX; Schema: dw; Owner: -
--

CREATE UNIQUE INDEX idx_theme_summary_pk ON dw.theme_summary USING btree (theme_sk);


--
-- Name: bridge_case_subject bridge_case_subject_case_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_case_subject
    ADD CONSTRAINT bridge_case_subject_case_sk_fkey FOREIGN KEY (case_sk) REFERENCES dw.dim_case(case_sk);


--
-- Name: bridge_case_subject bridge_case_subject_subject_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_case_subject
    ADD CONSTRAINT bridge_case_subject_subject_sk_fkey FOREIGN KEY (subject_sk) REFERENCES dw.dim_subject(subject_sk);


--
-- Name: bridge_subject_doctrine bridge_subject_doctrine_doctrine_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_subject_doctrine
    ADD CONSTRAINT bridge_subject_doctrine_doctrine_sk_fkey FOREIGN KEY (doctrine_sk) REFERENCES dw.dim_doctrine(doctrine_sk);


--
-- Name: bridge_subject_doctrine bridge_subject_doctrine_subject_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_subject_doctrine
    ADD CONSTRAINT bridge_subject_doctrine_subject_sk_fkey FOREIGN KEY (subject_sk) REFERENCES dw.dim_subject(subject_sk);


--
-- Name: bridge_theme_subject bridge_theme_subject_subject_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_theme_subject
    ADD CONSTRAINT bridge_theme_subject_subject_sk_fkey FOREIGN KEY (subject_sk) REFERENCES dw.dim_subject(subject_sk);


--
-- Name: bridge_theme_subject bridge_theme_subject_theme_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.bridge_theme_subject
    ADD CONSTRAINT bridge_theme_subject_theme_sk_fkey FOREIGN KEY (theme_sk) REFERENCES dw.dim_theme(theme_sk) ON DELETE CASCADE;


--
-- Name: dim_case dim_case_case_class_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_case
    ADD CONSTRAINT dim_case_case_class_sk_fkey FOREIGN KEY (case_class_sk) REFERENCES dw.dim_case_class(case_class_sk);


--
-- Name: dim_case dim_case_court_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_case
    ADD CONSTRAINT dim_case_court_sk_fkey FOREIGN KEY (court_sk) REFERENCES dw.dim_court(court_sk);


--
-- Name: dim_judging_body dim_judging_body_court_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_judging_body
    ADD CONSTRAINT dim_judging_body_court_sk_fkey FOREIGN KEY (court_sk) REFERENCES dw.dim_court(court_sk);


--
-- Name: dim_movement dim_movement_outcome_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.dim_movement
    ADD CONSTRAINT dim_movement_outcome_sk_fkey FOREIGN KEY (outcome_sk) REFERENCES dw.dim_decision_outcome(outcome_sk);


--
-- Name: fact_case_event fact_case_event_case_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_case_sk_fkey FOREIGN KEY (case_sk) REFERENCES dw.dim_case(case_sk);


--
-- Name: fact_case_event fact_case_event_court_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_court_sk_fkey FOREIGN KEY (court_sk) REFERENCES dw.dim_court(court_sk);


--
-- Name: fact_case_event fact_case_event_date_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_date_sk_fkey FOREIGN KEY (date_sk) REFERENCES dw.dim_date(date_sk);


--
-- Name: fact_case_event fact_case_event_judging_body_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_judging_body_sk_fkey FOREIGN KEY (judging_body_sk) REFERENCES dw.dim_judging_body(judging_body_sk);


--
-- Name: fact_case_event fact_case_event_movement_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.fact_case_event
    ADD CONSTRAINT fact_case_event_movement_sk_fkey FOREIGN KEY (movement_sk) REFERENCES dw.dim_movement(movement_sk);


--
-- Name: theme_narrative theme_narrative_theme_sk_fkey; Type: FK CONSTRAINT; Schema: dw; Owner: -
--

ALTER TABLE ONLY dw.theme_narrative
    ADD CONSTRAINT theme_narrative_theme_sk_fkey FOREIGN KEY (theme_sk) REFERENCES dw.dim_theme(theme_sk);


--
-- PostgreSQL database dump complete
--
