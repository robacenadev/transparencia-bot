import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def extrair_panorama(page: Page) -> dict:
    dados = {"nome": None, "cpf": None, "localidade": None}
    try:
        secao = await page.query_selector("section.dados-tabelados")
        if not secao:
            return dados
        spans = await secao.query_selector_all("span")
        textos = [(await s.inner_text()).strip() for s in spans]
        valores = [t for t in textos if t and not t.endswith(":")]
        dados["nome"]       = valores[0] if len(valores) > 0 else None
        dados["cpf"]        = valores[1] if len(valores) > 1 else None
        dados["localidade"] = valores[2] if len(valores) > 2 else None
    except Exception as e:
        logger.warning("[PARSER] Erro em extrair_panorama: %s", e)
    return dados


async def extrair_beneficios(page: Page, tipo_beneficio: str) -> list[dict]:
    registros = []
    try:
        await page.wait_for_selector("table tbody tr", timeout=15000)

        cabecalhos = []
        thead = await page.query_selector("table thead tr")
        if thead:
            ths = await thead.query_selector_all("th")
            cabecalhos = [(await th.inner_text()).strip() for th in ths]
            cabecalhos = [c for c in cabecalhos if c.lower() not in ("detalhar", "")]

        linhas = await page.query_selector_all("table tbody tr")
        for linha in linhas:
            celulas = await linha.query_selector_all("td")
            valores = [(await c.inner_text()).strip() for c in celulas]
            primeira = await linha.query_selector("td a")
            if primeira:
                valores = valores[1:]
            if not valores or "Nenhum registro" in valores[0]:
                continue
            if cabecalhos and len(cabecalhos) == len(valores):
                registros.append({"tipo": tipo_beneficio, "dados": dict(zip(cabecalhos, valores))})
            else:
                registros.append({"tipo": tipo_beneficio, "dados": valores})

    except Exception as e:
        logger.warning("[PARSER] Erro em extrair_beneficios '%s': %s", tipo_beneficio, e)

    return registros