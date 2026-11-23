import psycopg2
import pytest

from pipeline.theme_area import TPU_AREA_FALLBACK
from pipeline.theme_load import assert_no_orphan_themes, load, set_official_areas
from pipeline.theme_registry import ensure as ensure_registry
from pipeline.tpu import load as load_tpu


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        ensure_registry(cur)
        cur.execute("TRUNCATE dw.dim_theme, dw.dim_subject RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE etl.theme_registry RESTART IDENTITY CASCADE")
        yield cur
        connection.commit()


def insert_subject(cursor, name, code, tpu_area=None):
    cursor.execute(
        "INSERT INTO dw.dim_subject (subject_name, subject_code, tpu_area) "
        "VALUES (%s, %s, %s) RETURNING subject_sk",
        (name, code, tpu_area),
    )
    return cursor.fetchone()[0]


def fetch_theme(cursor, theme_name):
    cursor.execute(
        "SELECT theme_sk, theme_key, subject_area FROM dw.dim_theme WHERE theme_name = %s",
        (theme_name,),
    )
    return cursor.fetchone()


def fetch_bridge(cursor, theme_sk):
    cursor.execute(
        "SELECT subject_sk FROM dw.bridge_theme_subject WHERE theme_sk = %s ORDER BY subject_sk",
        (theme_sk,),
    )
    return [r[0] for r in cursor.fetchall()]


def test_loads_a_theme_and_links_its_subjects(cursor):
    sk1 = insert_subject(cursor, "Atraso de vôo", 1)
    sk2 = insert_subject(cursor, "Cancelamento de vôo", 2)
    themes = [{"theme_name": "Voos", "subject_area": "CONSUMIDOR", "subject_sks": [sk1, sk2]}]

    load(cursor, themes)

    theme_sk, _, subject_area = fetch_theme(cursor, "Voos")
    assert subject_area == "CONSUMIDOR"
    assert fetch_bridge(cursor, theme_sk) == sorted([sk1, sk2])


def test_the_theme_key_survives_a_full_rebuild(cursor):
    sk = insert_subject(cursor, "Contratos", 1)
    load(cursor, [{"theme_name": "Contratos", "subject_area": "CIVIL", "subject_sks": [sk]}])
    _, first_key, _ = fetch_theme(cursor, "Contratos")

    cursor.execute("TRUNCATE dw.dim_theme, dw.dim_subject RESTART IDENTITY CASCADE")
    sk = insert_subject(cursor, "Contratos", 1)
    load(cursor, [{"theme_name": "Contratos", "subject_area": "CIVIL", "subject_sks": [sk]}])
    _, second_key, _ = fetch_theme(cursor, "Contratos")

    assert first_key == second_key


def test_set_official_areas_uses_the_majority(cursor):
    sk1 = insert_subject(cursor, "Assunto A", 1, tpu_area="DIREITO CIVIL")
    sk2 = insert_subject(cursor, "Assunto B", 2, tpu_area="DIREITO CIVIL")
    sk3 = insert_subject(cursor, "Assunto C", 3, tpu_area="DIREITO DO CONSUMIDOR")
    themes = [{"theme_name": "Tema", "subject_area": None, "subject_sks": [sk1, sk2, sk3]}]
    load(cursor, themes)

    set_official_areas(cursor)

    cursor.execute("SELECT tpu_area FROM dw.dim_theme WHERE theme_name = 'Tema'")
    assert cursor.fetchone() == ("DIREITO CIVIL",)


@pytest.mark.parametrize(
    ("tpu_area", "subject_area"),
    [
        ("DIREITO CIVIL", "CIVIL"),
        ("DIREITO ADMINISTRATIVO E OUTRAS MATÉRIAS DE DIREITO PÚBLICO", "ADMINISTRATIVO"),
        ("DIREITO PROCESSUAL CIVIL E DO TRABALHO", "PROCESSUAL"),
        ("DIREITO DO TRABALHO", "TRABALHISTA"),
        ("DIREITO DA CRIANÇA E DO ADOLESCENTE", "FAMILIA"),
        ("DIREITO À EDUCAÇÃO", "ADMINISTRATIVO"),
        ("REGISTROS PÚBLICOS", "CIVIL"),
        ("DIREITO ASSISTENCIAL", "PREVIDENCIARIO"),
        ("DIREITO MARÍTIMO", "EMPRESARIAL"),
        ("QUESTÕES DE ALTA COMPLEXIDADE, GRANDE IMPACTO E REPERCUSSÃO", "AMBIENTAL"),
    ],
)
def test_set_official_areas_tags_an_untagged_theme_by_its_tpu_area(cursor, tpu_area, subject_area):
    sk = insert_subject(cursor, "Assunto sem regra", 1, tpu_area=tpu_area)
    load(cursor, [{"theme_name": "Tema sem regra", "subject_area": None, "subject_sks": [sk]}])

    set_official_areas(cursor)

    assert fetch_theme(cursor, "Tema sem regra")[2] == subject_area


def test_set_official_areas_keeps_the_area_a_theme_already_has(cursor):
    sk = insert_subject(cursor, "Plano de saúde", 1, tpu_area="DIREITO DO CONSUMIDOR")
    load(cursor, [{"theme_name": "Plano de saúde", "subject_area": "SAUDE", "subject_sks": [sk]}])

    set_official_areas(cursor)

    assert fetch_theme(cursor, "Plano de saúde")[2] == "SAUDE"


def test_every_tpu_area_of_the_civil_scope_has_a_fallback_area():
    tpu = load_tpu()
    penal = set(tpu["assuntos_penal"]["raizes"].values())
    areas = {area["nome"] for area in tpu["areas"].values()} - penal

    assert areas <= set(TPU_AREA_FALLBACK)


def test_assert_no_orphan_themes_raises_when_one_has_no_subject(cursor):
    cursor.execute(
        "INSERT INTO dw.dim_theme (theme_key, theme_name) VALUES (1, 'Órfão')"
    )

    with pytest.raises(ValueError, match="Órfão"):
        assert_no_orphan_themes(cursor)


def test_assert_no_orphan_themes_does_not_raise_when_clean(cursor):
    sk = insert_subject(cursor, "Contratos", 1)
    load(cursor, [{"theme_name": "Contratos", "subject_area": "CIVIL", "subject_sks": [sk]}])

    assert_no_orphan_themes(cursor)
