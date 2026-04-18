# Debug: Benefícios Vazios — Portal da Transparência Bot

## Problema
Bot retorna `beneficios: {}` (vazio) apesar do usuário ter benefícios cadastrados no portal.
- Panorama (nome, CPF, localidade) extrai OK
- Seções de benefícios: `section[data-collapse]` retorna **0 elementos**

## Stack
- FastAPI + Playwright (Python 3.12)
- Docker: serviço `bot-api`, porta `8001:8000`
- URL base: `https://portaldatransparencia.gov.br/pessoa-fisica/busca/lista`

## Arquivos Relevantes
| Arquivo | Papel |
|---|---|
| `bot/scraper.py` | Lógica principal de scraping (8 passos) |
| `bot/parser.py` | Extrai panorama e benefícios do HTML |
| `api/main.py` | FastAPI app |
| `api/routes.py` | Endpoint POST `/consultar` |
| `docker-compose.yml` | Serviço: `bot-api` (não `bot`) |

## O que foi feito nessa sessão

### Diagnósticos adicionados ao `scraper.py`

**PASSO 5** — adicionado wait extra após carregar panorama:
```python
await page.wait_for_selector("section.dados-tabelados", timeout=60000)
await page.wait_for_timeout(3000)  # <- adicionado
```

**PASSO 8** — tentativas de diagnóstico:
1. Dump dos irmãos de `section.dados-tabelados` via JS evaluate → output mostrou HTML do header/nav (top of page), não os benefícios
2. **Atual (último estado):** salva HTML completo em arquivo:
```python
if not secoes:
    html_completo = await page.content()
    with open("/tmp/pagina_debug.html", "w", encoding="utf-8") as f:
        f.write(html_completo)
    logger.debug("[PASSO 8] HTML completo salvo em /tmp/pagina_debug.html (%d chars)", len(html_completo))
```

## Próximo Passo (pendente)

Rebuild + testar + extrair o HTML para descobrir o seletor real:

```bash
cd ~/transparencia-bot

# Rebuild
docker compose build --no-cache bot-api
docker compose up -d bot-api

# Testar
curl -s -X POST http://localhost:8001/consultar \
  -H "Content-Type: application/json" \
  -d '{"identificador":"344225698"}' | python3 -m json.tool | head -20

# Copiar HTML gerado
docker compose cp bot-api:/tmp/pagina_debug.html ./pagina_debug.html
```

Depois abrir `pagina_debug.html` no browser e inspecionar a estrutura das seções de benefícios para achar o seletor correto (substituto de `section[data-collapse]`).

## Hipóteses
- Portal mudou estrutura HTML e `section[data-collapse]` não existe mais
- Benefícios podem estar em elemento diferente (ex: `div[data-collapse]`, `.br-card`, `.collapse-section`, etc.)
- Pode haver lazy load / requisição AJAX separada para benefícios

## Comandos Úteis

```bash
# Logs em tempo real
docker compose logs -f bot-api

# Só linhas do PASSO 8
docker compose logs bot-api 2>&1 | grep "PASSO 8"

# Shell dentro do container
docker compose exec bot-api bash
```
