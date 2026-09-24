import requests

from pipeline.datajud import collect as datajud_collect
from pipeline.dw_reference import verified_movement_codes
from pipeline.tpu import datajud_civil_query

TRIBUNALS = ("tjsp", "tjrj", "tjmg")

CORE_QUOTA = 700
SUPPORT_QUOTA = 250

AREA_QUOTAS = {
    **{code: CORE_QUOTA for code in ("899", "1156", "8826", "9985", "14", "195")},
    **{
        code: SUPPORT_QUOTA
        for code in ("12480", "7724", "10110", "864", "9633", "12734", "12775")
    },
}


def datajud_url(tribunal: str) -> str:
    return f"https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search"


def new_session(api_key: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"APIKey {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Ratio-DW/1.0 (FATEC API-5)",
    })
    return session


def harvest(
    session, cursor, tpu, tribunals=TRIBUNALS, area_quotas=AREA_QUOTAS, collect=datajud_collect
) -> int:
    total = 0
    for tribunal in tribunals:
        for area_code, quota in area_quotas.items():
            query = datajud_civil_query(tpu, area_code, verified_movement_codes())
            total += collect(session, cursor, datajud_url(tribunal), tribunal, query, quota)
            cursor.connection.commit()
    return total
