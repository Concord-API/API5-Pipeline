import numpy as np
import psycopg2.extras

from pipeline.doctrine_link import METHOD, THRESHOLD, distinctive_tokens, lexical_match
from pipeline.embedding import MODEL

TOP_K = 10

INSERT = """
    INSERT INTO dw.bridge_theme_precedent
        (theme_sk, precedent_sk, link_method, similarity, embedding_model)
    VALUES %s
"""


def precedent_text(question, thesis):
    return " ".join(part for part in (question, thesis) if part)


def links(themes, precedents, encoder, threshold=THRESHOLD):
    if not themes or not precedents:
        return []
    theme_vectors = np.asarray(encoder([name for _, name in themes]), dtype=np.float32)
    precedent_vectors = np.asarray(encoder([text for _, text in precedents]), dtype=np.float32)
    similarities = theme_vectors @ precedent_vectors.T
    found = []
    for row, (theme_sk, name) in enumerate(themes):
        tokens = distinctive_tokens(name)
        for column, (precedent_sk, text) in enumerate(precedents):
            score = float(similarities[row, column])
            if score >= threshold and lexical_match(tokens, text):
                found.append((theme_sk, precedent_sk, METHOD, score, MODEL))
    return sorted(found, key=lambda tie: (tie[0], tie[1]))


def link(cursor, encoder):
    cursor.execute("SELECT theme_sk, theme_name FROM dw.dim_theme ORDER BY theme_sk")
    themes = cursor.fetchall()
    cursor.execute(
        "SELECT precedent_sk, question, thesis FROM dw.dim_precedent ORDER BY precedent_sk"
    )
    precedents = [
        (precedent_sk, precedent_text(question, thesis))
        for precedent_sk, question, thesis in cursor.fetchall()
    ]
    rows = links(themes, precedents, encoder)
    cursor.execute("DELETE FROM dw.bridge_theme_precedent")
    if rows:
        psycopg2.extras.execute_values(cursor, INSERT, rows)
    return len(rows)
