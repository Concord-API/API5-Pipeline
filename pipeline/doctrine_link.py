import re
import unicodedata

import numpy as np
import psycopg2.extras

from pipeline.embedding import MODEL

THRESHOLD = 0.55
TOP_K = 10
METHOD = "embedding_cosine+lexical"
MIN_TOKEN_LENGTH = 4
PREFIX_LENGTH = 7
CHUNK = 4000
STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "a", "o",
    "as", "os", "por", "para", "com", "sem", "ao", "aos", "um", "uma", "ou", "que",
    "art", "arts", "outros", "outras", "geral", "gerais", "demais", "afins",
}

INSERT = """
    INSERT INTO dw.bridge_subject_doctrine
        (subject_sk, doctrine_sk, link_method, similarity, embedding_model)
    VALUES %s
"""


def normalize(text):
    return "".join(
        char for char in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(char) != "Mn"
    )


def distinctive_tokens(name):
    return [
        token for token in re.findall(r"[a-z0-9]+", normalize(name))
        if token not in STOPWORDS and len(token) >= MIN_TOKEN_LENGTH
    ]


def lexical_match(tokens, title):
    if not tokens:
        return False
    text = normalize(title)
    hits = sum(1 for token in tokens if token[:PREFIX_LENGTH] in text)
    return hits >= min(2, len(tokens))


def links(subjects, articles, encoder, threshold=THRESHOLD, top_k=TOP_K):
    if not subjects or not articles:
        return []
    subject_vectors = np.asarray(encoder([name for _, name in subjects]), dtype=np.float32)
    article_vectors = np.asarray(encoder([title for _, title in articles]), dtype=np.float32)
    tokens = [distinctive_tokens(name) for _, name in subjects]
    k = min(top_k, len(subjects))
    found = []
    for start in range(0, len(articles), CHUNK):
        similarities = article_vectors[start:start + CHUNK] @ subject_vectors.T
        for row, (doctrine_sk, title) in enumerate(articles[start:start + CHUNK]):
            for column in np.argsort(-similarities[row], kind="stable")[:k]:
                score = float(similarities[row, column])
                if score >= threshold and lexical_match(tokens[column], title):
                    found.append((subjects[column][0], doctrine_sk, METHOD, score, MODEL))
    return sorted(found, key=lambda link: (link[0], link[1]))


def link(cursor, encoder):
    cursor.execute("SELECT subject_sk, subject_name FROM dw.dim_subject ORDER BY subject_sk")
    subjects = cursor.fetchall()
    cursor.execute("SELECT doctrine_sk, title FROM dw.dim_doctrine ORDER BY doctrine_sk")
    articles = cursor.fetchall()
    rows = links(subjects, articles, encoder)
    cursor.execute("DELETE FROM dw.bridge_subject_doctrine")
    if rows:
        psycopg2.extras.execute_values(cursor, INSERT, rows)
    return len(rows)
