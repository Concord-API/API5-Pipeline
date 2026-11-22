import numpy as np
import psycopg2.extras

from pipeline.doctrine_link import METHOD, THRESHOLD, distinctive_tokens, lexical_match

EXACT_METHOD = "cnj_exact"
TOP_K = 3
CHUNK = 4000

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


def links(themes, rulings, encoder, threshold=THRESHOLD, top_k=TOP_K):
    if not themes or not rulings:
        return []
    theme_vectors = np.asarray(encoder([name for _, name in themes]), dtype=np.float32)
    tokens = [distinctive_tokens(name) for _, name in themes]
    k = min(top_k, len(themes))
    found = []
    for start in range(0, len(rulings), CHUNK):
        chunk = rulings[start:start + CHUNK]
        ruling_vectors = np.asarray(encoder([summary for _, summary in chunk]), dtype=np.float32)
        similarities = ruling_vectors @ theme_vectors.T
        for row, (ruling_sk, summary) in enumerate(chunk):
            for column in np.argsort(-similarities[row], kind="stable")[:k]:
                score = float(similarities[row, column])
                if score >= threshold and lexical_match(tokens[column], summary):
                    found.append((themes[column][0], ruling_sk, METHOD, score, threshold))
    return sorted(found, key=lambda tie: (tie[0], tie[1]))


def link(cursor, encoder):
    cursor.execute("DELETE FROM dw.bridge_theme_ruling")
    cursor.execute(EXACT_SQL, (EXACT_METHOD,))
    exact = cursor.rowcount
    cursor.execute("SELECT theme_sk, theme_name FROM dw.dim_theme ORDER BY theme_sk")
    themes = cursor.fetchall()
    cursor.execute(UNTIED_SQL)
    rows = links(themes, cursor.fetchall(), encoder)
    if rows:
        psycopg2.extras.execute_values(cursor, INSERT, rows)
    return exact + len(rows)
