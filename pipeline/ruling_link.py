import re

import numpy as np
import psycopg2.extras

from pipeline.doctrine_link import METHOD, THRESHOLD, distinctive_tokens, lexical_match
from pipeline.tpu import load as load_tpu

EXACT_METHOD = "cnj_exact"
TOP_K = 3
CHUNK = 4000

HEADING_END = re.compile(r"\s(?:\d+|[IVX]+)\s*[.)-]\s")
SEGMENT_END = re.compile(r"\.(?:\s+|$)")
NUMBER_ABBREVIATION = re.compile(r"\b(N|NR|ART|ARTS)\.\s*(?=\d)", re.IGNORECASE)
PROCEDURAL = re.compile(
    r"^(?:DIREITO\b|PROCESSUAL\b|PROCESSO\b|AGRAVO|AGINT|AGRG|EDCL|RECURSO|EMBARGOS|"
    r"HABEAS|MANDADO DE SEGURAN|S[ÚU]MULA|NEGATIVA DE PRESTA|OMISS|CONTRADI|OBSCURIDADE|"
    r"N[ÃA]O CONHECI|AUS[ÊE]NCIA DE IMPUGNA|IMPUGNA[ÇC][ÃA]O ESPEC|REEXAME|INCID[ÊE]NCIA|"
    r"[ÓO]BICE|PRECLUS[ÃA]O CONSUMATIVA|DECIS[ÃA]O MANTIDA|CASO EM EXAME|JULGAMENTO EXTRA|"
    r"DESPROVI|REJEITAD|PROVIMENTO|N[ÃA]O PROVI|PROVIDO|COMPET[ÊE]NCIA)",
    re.IGNORECASE,
)

EXACT_SQL = r"""
    INSERT INTO dw.bridge_theme_ruling (theme_sk, ruling_sk, link_method)
    SELECT DISTINCT bts.theme_sk, r.ruling_sk, %s
    FROM dw.dim_ruling r
    JOIN dw.dim_case c ON c.case_number = regexp_replace(r.case_number, '\D', '', 'g')
    JOIN dw.bridge_case_subject bcs ON bcs.case_sk = c.case_sk
    JOIN dw.bridge_theme_subject bts ON bts.subject_sk = bcs.subject_sk
    WHERE length(regexp_replace(r.case_number, '\D', '', 'g')) = 20
"""

UNTIED_SQL = """
    SELECT ruling_sk, summary FROM dw.dim_ruling r
    WHERE NOT EXISTS (SELECT 1 FROM dw.bridge_theme_ruling b WHERE b.ruling_sk = r.ruling_sk)
    ORDER BY ruling_sk
"""

INSERT = """
    INSERT INTO dw.bridge_theme_ruling
        (theme_sk, ruling_sk, link_method, similarity, similarity_threshold)
    VALUES %s
"""


def ruling_topic(summary):
    heading = " ".join(HEADING_END.split(summary or "", maxsplit=1)[0].split())
    heading = NUMBER_ABBREVIATION.sub(r"\1 ", heading)
    segments = [segment.strip() for segment in SEGMENT_END.split(heading)]
    return ". ".join(segment for segment in segments if segment and not PROCEDURAL.match(segment))


def area_names():
    return {area["nome"] for area in load_tpu()["areas"].values()}


def links(themes, rulings, encoder, threshold=THRESHOLD, top_k=TOP_K):
    topics = [(ruling_sk, ruling_topic(summary)) for ruling_sk, summary in rulings]
    topics = [(ruling_sk, topic) for ruling_sk, topic in topics if topic]
    if not themes or not topics:
        return []
    theme_vectors = np.asarray(encoder([name for _, name in themes]), dtype=np.float32)
    tokens = [distinctive_tokens(name) for _, name in themes]
    k = min(top_k, len(themes))
    found = []
    for start in range(0, len(topics), CHUNK):
        chunk = topics[start:start + CHUNK]
        ruling_vectors = np.asarray(encoder([topic for _, topic in chunk]), dtype=np.float32)
        similarities = ruling_vectors @ theme_vectors.T
        for row, (ruling_sk, topic) in enumerate(chunk):
            for column in np.argsort(-similarities[row], kind="stable")[:k]:
                score = float(similarities[row, column])
                if score >= threshold and lexical_match(tokens[column], topic):
                    found.append((themes[column][0], ruling_sk, METHOD, score, threshold))
    return sorted(found, key=lambda tie: (tie[0], tie[1]))


def link(cursor, encoder):
    cursor.execute("DELETE FROM dw.bridge_theme_ruling")
    cursor.execute(EXACT_SQL, (EXACT_METHOD,))
    exact = cursor.rowcount
    cursor.execute(
        "SELECT theme_sk, theme_name FROM dw.dim_theme WHERE NOT (theme_name = ANY(%s)) "
        "ORDER BY theme_sk",
        (sorted(area_names()),),
    )
    themes = cursor.fetchall()
    cursor.execute(UNTIED_SQL)
    rows = links(themes, cursor.fetchall(), encoder)
    if rows:
        psycopg2.extras.execute_values(cursor, INSERT, rows)
    return exact + len(rows)
