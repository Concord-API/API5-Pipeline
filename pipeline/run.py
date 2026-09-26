from datetime import datetime, timezone

from pipeline import (
    doctrine_link,
    dw_case,
    dw_case_links,
    dw_date,
    dw_doctrine,
    dw_fact,
    dw_movement_polarity,
    dw_reference,
    dw_subject,
    integrity,
    load_file,
    search_synonym,
    staging,
    strength_config,
    theme_build,
    theme_load,
    theme_narrative,
    theme_registry,
)
from pipeline.embedding import local_encoder
from pipeline.staging_schema import ensure as ensure_staging
from pipeline.transform import flatten


def read_raw_cases(cursor):
    cursor.execute("SELECT id, tribunal, source_url, collected_at, payload FROM raw.datajud_case")
    return cursor.fetchall()


def transform_all(cursor, tpu, movement_names=None):
    ensure_staging(cursor)
    rows = []
    for raw_id, tribunal, source_url, collected_at, payload in read_raw_cases(cursor):
        rows.extend(
            flatten(raw_id, tribunal, source_url, collected_at, payload, tpu, movement_names)
        )
    staging.load(cursor, rows)
    return len(rows)


def load_dimensions(cursor, tpu, calendar_until):
    dw_reference.seed_courts(cursor)
    dw_reference.seed_outcomes(cursor)
    dw_reference.seed_verified_movements(cursor)
    dw_reference.load_case_classes(cursor)
    dw_reference.load_judging_bodies(cursor)
    dw_reference.load_movements(cursor)
    dw_case.load(cursor)
    dw_subject.load_subjects(cursor)
    dw_subject.set_tpu_areas(cursor, tpu)
    dw_subject.assert_no_penal_subjects(cursor, tpu)
    dw_subject.load_bridge(cursor)
    dw_date.seed(cursor, calendar_until)
    dw_fact.load(cursor)
    dw_movement_polarity.set_polarity(cursor)
    dw_case_links.format_case_numbers(cursor)
    dw_case_links.set_source_links(cursor)
    dw_doctrine.transform(cursor)
    dw_doctrine.load(cursor)


def subject_pairs(cursor):
    cursor.execute("SELECT subject_name, subject_sk FROM dw.dim_subject")
    return cursor.fetchall()


def load_themes(cursor, groups):
    theme_registry.ensure(cursor)
    themes = theme_build.build(subject_pairs(cursor), groups)
    theme_load.load(cursor, themes)
    theme_load.set_official_areas(cursor)
    theme_load.assert_no_orphan_themes(cursor)


def run(cursor, dsn, tpu, groups, output_path, runner=None, encoder=local_encoder):
    today = datetime.now(timezone.utc).date()
    transform_all(cursor, tpu)
    load_dimensions(cursor, tpu, today.year + 1)
    doctrine_link.link(cursor, encoder)
    load_themes(cursor, groups)
    strength_config.seed(cursor, today.year)
    search_synonym.seed(cursor, search_synonym.load())
    theme_narrative.generate(cursor, today)
    integrity.assert_clean(cursor, tpu)
    cursor.connection.commit()
    return load_file.generate(cursor, dsn, output_path, runner=runner)
