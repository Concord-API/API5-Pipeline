import sys

import numpy as np
import psycopg2
from sklearn.cluster import AgglomerativeClustering

from pipeline import config, theme_build

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
THRESHOLD = 0.20


def local_encoder(names):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL, device="cpu").encode(list(names), normalize_embeddings=True)


def clusters(names, vectors, threshold):
    if len(names) < 2:
        return [list(names)]
    labels = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="average"
    ).fit_predict(np.asarray(vectors, dtype=np.float32))
    grouped = {}
    for name, label in zip(names, labels):
        grouped.setdefault(int(label), []).append(name)
    return list(grouped.values())


def curated(group, groups):
    return any(set(group) <= set(curation["aliases"]) for curation in groups)


def proposals(names, groups, case_counts, encoder=local_encoder, threshold=THRESHOLD):
    names = list(names)
    if not names:
        return []
    found = []
    for group in clusters(names, encoder(names), threshold):
        if len(group) > 1 and not curated(group, groups):
            members = sorted(group, key=lambda name: (-case_counts.get(name, 0), name))
            found.append({
                "total_cases": sum(case_counts.get(name, 0) for name in group),
                "members": members,
            })
    return sorted(found, key=lambda proposal: (-proposal["total_cases"], proposal["members"]))


def subject_case_counts(cursor):
    cursor.execute(
        "SELECT s.subject_name, count(DISTINCT b.case_sk) "
        "FROM dw.dim_subject s LEFT JOIN dw.bridge_case_subject b ON b.subject_sk = s.subject_sk "
        "GROUP BY s.subject_name ORDER BY s.subject_name"
    )
    return dict(cursor.fetchall())


def main(groups=None, encoder=local_encoder):
    config.load_env()
    try:
        dsn = config.database_url()
    except config.ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        counts = subject_case_counts(cursor)
    groups = theme_build.load_groups() if groups is None else groups
    found = proposals(counts, groups, counts, encoder=encoder)
    print(f"{len(found)} groups to review ({len(counts)} subjects, threshold {THRESHOLD})")
    for proposal in found:
        print(f"{proposal['total_cases']:>6} cases :: {' | '.join(proposal['members'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
