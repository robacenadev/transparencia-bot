from playwright.async_api import Page


async def extrair_panorama(page: Page) -> dict:
    """
    Extrai os dados da tela 'Panorama da relação da pessoa com o Governo Federal'.
    """
    dados = {}

    try:
        spans = await page.query_selector_all("section.dados-tabelados span")
        valores = [await s.inner_text() for s in spans]
        dados["nome"]       = valores[0] if len(valores) > 0 else None
        dados["cpf"]        = valores[1] if len(valores) > 1 else None
        dados["localidade"] = valores[2] if len(valores) > 2 else None
    except Exception:
        dados["nome"]       = None
        dados["cpf"]        = None
        dados["localidade"] = None

    return dados


async def extrair_beneficios(page: Page, tipo_beneficio: str) -> list[dict]:
    """
    Coleta os dados da tabela de detalhes de um benefício.
    """
    registros = []

    try:
        # Aguarda a tabela carregar
        await page.wait_for_selector(
            "table#tabelaDetalheDisponibilizado tbody tr",
            timeout=10000
        )
        linhas = await page.query_selector_all(
            "table#tabelaDetalheDisponibilizado tbody tr"
        )

        for linha in linhas:
            celulas = await linha.query_selector_all("td")
            valores = [await c.inner_text() for c in celulas]
            # Ignora linhas vazias ou com "Nenhum registro encontrado"
            if valores and "Nenhum registro" not in valores[0]:
                registros.append({
                    "tipo": tipo_beneficio,
                    "dados": valores
                })

    except Exception:
        pass

    return registros