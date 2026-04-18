import re
import logging
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from core.config import settings
from bot.parser import extrair_panorama, extrair_beneficios
from bot.screenshot import capturar_base64

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

URL_BASE = "https://portaldatransparencia.gov.br/pessoa-fisica/busca/lista"


def _detectar_tipo_identificador(identificador: str) -> bool:
    """Retorna True se o identificador for CPF ou NIS (apenas números e pontuação)."""
    return bool(re.match(r'^[\d.\-/]+$', identificador.strip()))


async def executar_consulta(identificador: str, filtro_social: bool = False) -> dict:
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
            is_cpf_nis = _detectar_tipo_identificador(identificador)
            mensagem = (
                "Não foi possível retornar os dados no tempo de resposta solicitado"
                if is_cpf_nis
                else f"Foram encontrados 0 resultados para o termo '{identificador}'"
            )
            resultado = {
                "status": "erro",
                "mensagem": mensagem,
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
    logger.debug("[PASSO 1] Acessando home do portal...")
    await page.goto("https://portaldatransparencia.gov.br", wait_until="load", timeout=60000)
    await page.wait_for_timeout(1000)

    # 2. Navega para URL de resultados
    url_busca = f"{URL_BASE}?termo={quote_plus(identificador)}&pagina=1&tamanhoPagina=10"
    if filtro_social:
        url_busca += "&beneficiarioProgramaSocial=true"
    logger.debug("[PASSO 2] Navegando para resultados: %s", url_busca)
    await page.goto(url_busca, wait_until="load", timeout=60000)

    # 3. Espera resultados ou mensagem de zero resultados
    logger.debug("[PASSO 3] Aguardando resultados...")
    await page.wait_for_selector(
        "a.link-busca-nome, .msgErro, .nenhum-resultado, [class*='resultado'] p",
        timeout=60000
    )
    if not await page.locator("a.link-busca-nome").count():
        is_cpf_nis = _detectar_tipo_identificador(identificador)
        mensagem = (
            "Não foi possível retornar os dados no tempo de resposta solicitado"
            if is_cpf_nis
            else f"Foram encontrados 0 resultados para o termo '{identificador}'"
        )
        return {
            "status": "erro",
            "mensagem": mensagem,
            "identificador": identificador,
            "panorama": None,
            "beneficios": None,
            "evidencia_base64": await capturar_base64(page),
        }

    # 4. Navega para o perfil do primeiro resultado
    url_resultados = page.url
    primeiro = page.locator("a.link-busca-nome").first
    href = await primeiro.get_attribute("href")
    logger.debug("[PASSO 4] Navegando para perfil: %s", href)
    await page.goto(
        f"https://portaldatransparencia.gov.br{href}",
        wait_until="load",
        timeout=60000,
        referer=url_resultados
    )

    # 5. Espera o panorama carregar
    logger.debug("[PASSO 5] Aguardando panorama...")
    await page.wait_for_selector("section.dados-tabelados", timeout=60000)
    await page.wait_for_timeout(3000)

    # 6. Extrai dados do panorama
    panorama = await extrair_panorama(page)
    logger.debug("[PASSO 6] Panorama: %s", panorama)

    # 7. Salva HTML para debug
    html_completo = await page.content()
    with open("/tmp/pagina_debug.html", "w", encoding="utf-8") as f:
        f.write(html_completo)

    # 8. Coleta benefícios navegando por cada seção do accordion
    logger.debug("[PASSO 7] Coletando benefícios...")
    beneficios_coletados = {}
    itens = await page.query_selector_all("div.br-accordion#accordion1 div.item")
    logger.debug("[PASSO 7] Total de itens: %d", len(itens))

    for item in itens:
        titulo = "?"
        try:
            titulo_el = await item.query_selector("button.header span.title")
            if not titulo_el:
                continue
            titulo = (await titulo_el.inner_text()).strip()
            logger.debug("[PASSO 7] Processando seção: '%s'", titulo)

            # Usa aria-controls para localizar o div.content irmão (não filho)
            header_btn = await item.query_selector("button.header")
            aria_controls = await header_btn.get_attribute("aria-controls")
            content = await page.query_selector(f"#{aria_controls}")

            if not content:
                logger.debug("[PASSO 7] div.content não encontrado para '%s'", titulo)
                beneficios_coletados[titulo] = None
                continue

            # Expande o accordion se necessário
            aria_expanded = await header_btn.get_attribute("aria-expanded")
            if aria_expanded != "true":
                await header_btn.click()
                await page.wait_for_timeout(800)

            # Busca link de detalhe dentro do content
            btn = (
                await content.query_selector("a.br-button.secondary")
                or await content.query_selector("a[href*='/beneficios/']")
                or await content.query_selector("a[href*='/pessoa-fisica/']")
            )

            if not btn:
                logger.debug("[PASSO 7] Nenhum link em '%s'", titulo)
                beneficios_coletados[titulo] = None
                continue

            url_panorama = page.url
            href_beneficio = await btn.get_attribute("href")
            logger.debug("[PASSO 7] Navegando para: %s", href_beneficio)
            await page.goto(
                f"https://portaldatransparencia.gov.br{href_beneficio}",
                wait_until="load",
                timeout=60000,
                referer=url_panorama,
            )
            await page.wait_for_timeout(2000)
            beneficios_coletados[titulo] = await extrair_beneficios(page, titulo)
            logger.debug("[PASSO 7] '%s' coletado. Voltando...", titulo)
            await page.go_back()
            await page.wait_for_selector("section.dados-tabelados", timeout=60000)
            # Reobtém itens pois o DOM pode ter sido reconstruído
            itens = await page.query_selector_all("div.br-accordion#accordion1 div.item")

        except Exception as ex:
            logger.warning("[PASSO 7] Erro em '%s': %s", titulo, ex)
            continue

    # 9. Volta ao panorama e captura evidência com accordion expandido
    logger.debug("[PASSO 8] Voltando ao panorama para capturar evidência final...")
    await page.goto(
        f"https://portaldatransparencia.gov.br{href}",
        wait_until="load",
        timeout=60000,
        referer=url_resultados
    )
    await page.wait_for_selector("section.dados-tabelados", timeout=60000)
    await page.wait_for_timeout(2000)

    # Remove todos os elementos fixed/sticky (banner de cookies, overlays, etc)
    await page.evaluate("""
        document.querySelectorAll('*').forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.position === 'fixed' || style.position === 'sticky') {
                el.remove();
            }
        });
    """)
    await page.wait_for_timeout(300)

    # Expande todos os accordions antes do print
    acordeoes = await page.query_selector_all("div.br-accordion#accordion1 button.header")
    for btn in acordeoes:
        expanded = await btn.get_attribute("aria-expanded")
        if expanded != "true":
            await btn.click()
            await page.wait_for_timeout(400)

    await page.wait_for_timeout(500)
    evidencia = await capturar_base64(page)
    logger.debug("[PASSO 8] Screenshot capturado com accordion expandido.")

    return {
        "status": "sucesso",
        "identificador": identificador,
        "panorama": panorama,
        "beneficios": beneficios_coletados,
        "evidencia_base64": evidencia,
    }