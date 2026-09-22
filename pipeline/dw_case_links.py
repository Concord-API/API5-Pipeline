def format_case_numbers(cursor):
    cursor.execute("""
        UPDATE dw.dim_case
        SET case_number_formatted =
            substr(case_number, 1, 7) || '-' || substr(case_number, 8, 2) || '.' ||
            substr(case_number, 10, 4) || '.' || substr(case_number, 14, 1) || '.' ||
            substr(case_number, 15, 2) || '.' || substr(case_number, 17, 4)
        WHERE case_number IS NOT NULL AND length(case_number) = 20
    """)


def set_source_links(cursor):
    cursor.execute("""
        UPDATE dw.dim_case c
        SET source_link =
            'https://esaj.tjsp.jus.br/cpopg/search.do?conversationId='
            || '&dadosConsulta.localPesquisa.cdLocal=-1'
            || '&cbPesquisa=NUMPROC'
            || '&dadosConsulta.tipoNuProcesso=UNIFICADO'
            || '&numeroDigitoAnoUnificado=' || substr(c.case_number, 1, 7) || '-'
                || substr(c.case_number, 8, 2) || '.' || substr(c.case_number, 10, 4)
            || '&foroNumeroUnificado=' || substr(c.case_number, 17, 4)
            || '&dadosConsulta.valorConsultaNuUnificado=' || c.case_number_formatted
            || '&dadosConsulta.valorConsulta=',
            source_link_type = 'direto'
        FROM dw.dim_court ct
        WHERE ct.court_sk = c.court_sk
          AND ct.court_code = 'TJSP'
          AND c.court_level IN ('First', 'SpecialCourt')
          AND c.case_number_formatted IS NOT NULL
    """)
    cursor.execute("""
        UPDATE dw.dim_case c
        SET source_link =
            'https://esaj.tjsp.jus.br/cposg/search.do?conversationId='
            || '&paginaConsulta=1'
            || '&cbPesquisa=NUMPROC'
            || '&tipoNuProcesso=UNIFICADO'
            || '&numeroDigitoAnoUnificado=' || substr(c.case_number, 1, 7) || '-'
                || substr(c.case_number, 8, 2) || '.' || substr(c.case_number, 10, 4)
            || '&foroNumeroUnificado=' || substr(c.case_number, 17, 4)
            || '&dePesquisaNuUnificado=' || c.case_number_formatted
            || '&dePesquisa=',
            source_link_type = 'direto'
        FROM dw.dim_court ct
        WHERE ct.court_sk = c.court_sk
          AND ct.court_code = 'TJSP'
          AND c.court_level IN ('Second', 'AppealPanel')
          AND c.case_number_formatted IS NOT NULL
    """)
    cursor.execute("""
        UPDATE dw.dim_case c
        SET source_link = 'https://www3.tjrj.jus.br/consultaprocessual/',
            source_link_type = 'portal'
        FROM dw.dim_court ct
        WHERE ct.court_sk = c.court_sk AND ct.court_code = 'TJRJ'
    """)
    cursor.execute("""
        UPDATE dw.dim_case c
        SET source_link = 'https://www4.tjmg.jus.br/juridico/sf/proc_resultado.jsp',
            source_link_type = 'portal'
        FROM dw.dim_court ct
        WHERE ct.court_sk = c.court_sk AND ct.court_code = 'TJMG'
    """)
