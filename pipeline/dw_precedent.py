from pipeline.stj_precedents import from_row, is_valid, tema_link

OUT_OF_SCOPE_AREAS = ("864", "11428", "10739")


def area_codes(tpu):
    return {int(code) for code in tpu.get("areas", {})}


def out_of_scope_codes(tpu):
    areas = tpu.get("areas", {})
    return {
        int(code)
        for area in OUT_OF_SCOPE_AREAS
        if area in areas
        for code in areas[area]["codigos"]
    }


def in_scope(tema, out_of_scope):
    codes = tema["subject_codes"]
    return not codes or any(code not in out_of_scope for code in codes)


def load(cursor, area_codes, out_of_scope=frozenset()):
    cursor.execute("SELECT payload, collected_at FROM raw.stj_precedent")
    temas = [(from_row(payload), collected_at) for payload, collected_at in cursor.fetchall()]
    valid = [
        (tema, collected_at)
        for tema, collected_at in temas
        if tema and is_valid(tema) and in_scope(tema, out_of_scope)
    ]

    cursor.execute("DELETE FROM dw.bridge_subject_precedent")
    cursor.execute(
        "DELETE FROM dw.dim_precedent WHERE (precedent_kind, precedent_number) "
        "NOT IN (SELECT kind, number FROM unnest(%s::text[], %s::int[]) AS v(kind, number))",
        ([tema["kind"] for tema, _ in valid], [tema["number"] for tema, _ in valid]),
    )
    for tema, collected_at in valid:
        cursor.execute(
            """
            INSERT INTO dw.dim_precedent
                (precedent_kind, precedent_number, thesis, question, status, judged_at,
                 judging_body, source_url, extracted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (precedent_kind, precedent_number) DO UPDATE
            SET thesis = EXCLUDED.thesis, question = EXCLUDED.question, status = EXCLUDED.status,
                judged_at = EXCLUDED.judged_at, judging_body = EXCLUDED.judging_body,
                source_url = EXCLUDED.source_url, extracted_at = EXCLUDED.extracted_at
            """,
            (
                tema["kind"], tema["number"], tema["thesis"], tema["question"], tema["status"],
                tema["judged_at"], tema["judging_body"], tema_link(tema["number"]), collected_at,
            ),
        )
        codes = [code for code in tema["subject_codes"] if code not in area_codes]
        if codes:
            cursor.execute(
                """
                INSERT INTO dw.bridge_subject_precedent (subject_sk, precedent_sk)
                SELECT s.subject_sk, p.precedent_sk
                FROM dw.dim_subject s
                JOIN dw.dim_precedent p
                  ON p.precedent_kind = %s AND p.precedent_number = %s
                WHERE s.subject_code = ANY(%s)
                ON CONFLICT DO NOTHING
                """,
                (tema["kind"], tema["number"], codes),
            )
    return len(valid)
