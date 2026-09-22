CLAIMANT_CODES = (219, 220, 221)
APPELLANT_CODES = (237, 238, 239)


def set_polarity(cursor):
    cursor.execute(
        "UPDATE dw.dim_movement SET polarity_reference = 'pretensao_autor' "
        "WHERE movement_code = ANY(%s)",
        (list(CLAIMANT_CODES),),
    )
    cursor.execute(
        "UPDATE dw.dim_movement SET polarity_reference = 'pretensao_recorrente' "
        "WHERE movement_code = ANY(%s)",
        (list(APPELLANT_CODES),),
    )
