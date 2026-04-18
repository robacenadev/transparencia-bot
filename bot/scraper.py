import logging

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from core.config import settings
from bot.parser import extrair_panorama, extrair_beneficios
from bot.screenshot import capturar_base64

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

URL_BASE = "https://portaldatransparencia.gov.br/pessoa-fisica/busca/lista"


async def executar_consulta(
    identificador: str,
    filtro_social: bool = False,
) -> dict:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=settings.headless,
            args=["--no-sandbox"]
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
            ignore_https_errors=True,
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"}
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt']});
            window.chrome = {runtime: {}};
        """)

        page = await context.new_page()
        page.set_default_timeout(settings.playwright_timeout)

        try:
            resultado = await _realizar_busca(page, identificador, filtro_social)
        except PlaywrightTimeout:
            resultado = {
                "status": "erro",
                "mensagem": "Não foi possível retornar os dados no tempo de resposta solicitado",
                "identificador": identificador,
                "evidencia_base64": await capturar_base64(page),
            }
        except Exception as e:
            resultado = {
                "status": "erro",
                "mensagem": str(e),
                "identificador": identificador,
                "evidencia_base64": None,
            }
        finally:
            await context.close()
            await browser.close()

    return resultado


async def _realizar_busca(page, identificador: str, filtro_social: bool) -> dict:

    # 1. Visita a home para estabelecer sessão com o WAF
    logger.debug("[PASSO 1] Acessando home do portal para estabelecer sessão...")
    await page.goto(
        "https://portaldatransparencia.gov.br",
        wait_until="load",
        timeout=60000
    )
    logger.debug("[PASSO 1] Home carregada. URL atual: %s", page.url)
    await page.wait_for_timeout(1000)

    # 2. Navega direto para URL de resultados com o termo
    from urllib.parse import quote_plus
    url_busca = f"{URL_BASE}?termo={quote_plus(identificador)}&pagina=1&tamanhoPagina=10"
    if filtro_social:
        url_busca += "&beneficiarioProgramaSocial=true"
    logger.debug("[PASSO 2] Navegando direto para resultados: %s", url_busca)
    await page.goto(url_busca, wait_until="load", timeout=60000)
    logger.debug("[PASSO 2] Página de resultados carregada. URL atual: %s", page.url)

    # 3. Espera resultados ou mensagem de zero resultados
    logger.debug("[PASSO 3] Aguardando resultados ou mensagem de erro...")
    resultado_locator = await page.wait_for_selector(
        "a.link-busca-nome, .msgErro, .nenhum-resultado, [class*='resultado'] p",
        timeout=60000
    )
    # Verifica se há resultados ou mensagem de zero resultados
    if not await page.locator("a.link-busca-nome").count():
        texto_pagina = await page.inner_text("body")
        logger.debug("[PASSO 3] Sem resultados. Texto: %s", texto_pagina[:200])
        return {
            "status": "erro",
            "mensagem": f"Foram encontrados 0 resultados para o termo '{identificador}'",
            "identificador": identificador,
            "panorama": None,
            "beneficios": None,
            "evidencia_base64": await capturar_base64(page),
        }
    logger.debug("[PASSO 3] Resultados encontrados. URL atual: %s", page.url)

    # 4. Navega para o panorama
    url_resultados = page.url
    primeiro = page.locator("a.link-busca-nome").first
    href = await primeiro.get_attribute("href")
    logger.debug("[PASSO 4] href do primeiro resultado: %s", href)

    logger.debug("[PASSO 4] Navegando para perfil: https://portaldatransparencia.gov.br%s", href)
    await page.goto(
        f"https://portaldatransparencia.gov.br{href}",
        wait_until="load",
        timeout=60000,
        referer=url_resultados
    )
    logger.debug("[PASSO 4] Perfil carregado. URL atual: %s", page.url)

    # 5. Espera o panorama carregar
    logger.debug("[PASSO 5] Aguardando 'section.dados-tabelados'...")
    await page.wait_for_selector("section.dados-tabelados", timeout=60000)
    # Aguarda JS renderizar seções de benefícios após a seção principal
    await page.wait_for_timeout(3000)
    logger.debug("[PASSO 5] Panorama carregado.")

    # 6. Captura evidência
    logger.debug("[PASSO 6] Capturando screenshot (base64)...")
    evidencia = await capturar_base64(page)
    logger.debug("[PASSO 6] Screenshot capturado. Tamanho base64: %d chars", len(evidencia))

    # 7. Extrai panorama
    logger.debug("[PASSO 7] Extraindo dados do panorama...")
    panorama = await extrair_panorama(page)
    logger.debug("[PASSO 7] Panorama extraído: %s", panorama)

    # 8. Coleta títulos das seções de benefícios
    logger.debug("[PASSO 8] Coletando seções de benefícios (div.br-accordion#accordion1)...")
    beneficios_coletados = {}
    itens = await page.query_selector_all("div.br-accordion#accordion1 div.item")
    logger.debug("[PASSO 8] Total de itens encontrados: %d", len(itens))

    html_completo = await page.content()
    with open("/tmp/pagina_debug.html", "w", encoding="utf-8") as f:
        f.write(html_completo)
    logger.debug("[PASSO 8] HTML salvo em /tmp/pagina_debug.html (%d chars)", len(html_completo))

    for item in itens:
        titulo = "?"
        try:
            titulo_el = await item.query_selector("button.header span.title")
            if not titulo_el:
                logger.debug("[PASSO 8] Item sem 'button.header span.title', pulando.")
                continue
            titulo = (await titulo_el.inner_text()).strip()
            logger.debug("[PASSO 8] Processando seção: '%s'", titulo)

            # Expande o item clicando no header (accordion pode estar fechado)
            header_btn = await item.query_selector("button.header")
            if header_btn:
                aria_expanded = await header_btn.get_attribute("aria-expanded")
                if aria_expanded != "true":
                    await header_btn.click()
                    await page.wait_for_timeout(500)

            # Busca link de detalhes dentro do div.content
            content = await item.query_selector("div.content")
            btn = None
            if content:
                btn = (
                    await content.query_selector("a.br-button.secondary")
                    or await content.query_selector("a.br-button")
                    or await content.query_selector("a[href*='/pessoa-fisica/']")
                )

            if not btn:
                if content:
                    links = await content.query_selector_all("a")
                    hrefs = [await l.get_attribute("href") for l in links]
                    logger.debug("[PASSO 8] Links em '%s': %s", titulo, hrefs)
                else:
                    logger.debug("[PASSO 8] div.content NÃO encontrado na seção '%s'", titulo)
                beneficios_coletados[titulo] = None
                continue

            url_panorama = page.url
            href_beneficio = await btn.get_attribute("href")
            logger.debug("[PASSO 8] Navegando para benefício: %s", href_beneficio)
            await page.goto(
                f"https://portaldatransparencia.gov.br{href_beneficio}",
                wait_until="load",
                timeout=60000,
                referer=url_panorama,
            )
            await page.wait_for_selector("table#tabelaDetalheDisponibilizado", timeout=30000)
            beneficios_coletados[titulo] = await extrair_beneficios(page, titulo)
            logger.debug("[PASSO 8] Benefício '%s' coletado. Voltando ao panorama...", titulo)
            await page.go_back()
            await page.wait_for_selector("section.dados-tabelados", timeout=60000)
            # Reobtém itens pois o DOM foi reconstruído após navegação
            itens = await page.query_selector_all("div.br-accordion#accordion1 div.item")
            logger.debug("[PASSO 8] Retornou ao panorama.")
        except Exception as ex:
            logger.warning("[PASSO 8] Erro ao processar seção '%s': %s", titulo, ex)
            continue

    return {
        "status": "sucesso",
        "identificador": identificador,
        "panorama": panorama,
        "beneficios": beneficios_coletados,
        "evidencia_base64": evidencia,
    }