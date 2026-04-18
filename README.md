# Transparência Bot

Bot de automação web (RPA) para consulta de pessoas físicas no Portal da Transparência do Governo Federal, desenvolvido como desafio técnico para a vaga de Full Stack Developer Python (RPA e Hiperautomação).

## Sobre o Projeto

O bot realiza consultas automatizadas no Portal da Transparência, coletando dados do panorama da pessoa física e retornando as informações em formato JSON com evidência em Base64.

## Stack

| Tecnologia | Uso |
|---|---|
| Python 3.12 | Linguagem principal |
| FastAPI | API REST com documentação Swagger automática |
| Playwright | Automação do browser |
| Docker + Docker Compose | Containerização dos serviços |
| n8n | Orquestração do workflow (Parte 2) |

## Estrutura do Projeto

```
transparencia-bot/
├── bot/
│   ├── scraper.py       # Lógica principal de automação
│   ├── parser.py        # Extração de dados da página
│   └── screenshot.py    # Captura de evidência em Base64
├── api/
│   ├── main.py          # FastAPI app
│   ├── routes.py        # Endpoints
│   └── schemas.py       # Modelos Pydantic
├── core/
│   └── config.py        # Configurações
├── docker-compose.yml   # Bot API (8001) + n8n (5678)
├── Dockerfile
└── requirements.txt
```

## Como Executar

**Pré-requisitos:** Docker e Docker Compose instalados.

```bash
git clone https://github.com/robacenadev/transparencia-bot.git
cd transparencia-bot
cp .env.example .env
docker compose up
```

| Serviço | URL |
|---|---|
| API (Swagger) | http://localhost:8001/docs |
| n8n | http://localhost:5678 |

### Exemplo de requisição

```bash
curl -X POST http://localhost:8001/api/v1/consultar \
  -H "Content-Type: application/json" \
  -d '{"identificador": "João da Silva", "filtro_social": false}'
```

### Resposta

```json
{
  "status": "sucesso",
  "identificador": "João da Silva",
  "panorama": {
    "nome": "JOÃO DA SILVA",
    "cpf": "***.123.456-**",
    "localidade": "BELO HORIZONTE - MG"
  },
  "beneficios": {
    "RECEBIMENTOS DE RECURSOS": null
  },
  "evidencia_base64": "iVBORw0KGgo..."
}
```

## Decisões Técnicas

### Playwright com Chrome real

O Portal da Transparência utiliza AWS CloudFront com WAF (Web Application Firewall) que detecta e bloqueia automações baseadas em Chromium padrão, retornando erro 403. A solução foi utilizar `channel="chrome"` no Playwright, que aciona o Chrome real instalado no sistema, bypassando a detecção do WAF.

```python
browser = await pw.chromium.launch(
    headless=True,
    channel="chrome",
    args=["--no-sandbox"]
)
```

### Referer para navegação no panorama

O portal verifica o cabeçalho `Referer` ao acessar a página de detalhes da pessoa. Sem ele, a requisição retorna 403. A solução foi passar a URL da página de resultados como referer ao navegar para o panorama.

```python
await page.goto(
    url_panorama,
    referer=url_resultados,
    wait_until="load"
)
```

### n8n como plataforma de orquestração (Parte 2)

O n8n foi escolhido por ser uma plataforma de automação open source com suporte nativo a Google Drive e Google Sheets, além de já fazer parte do stack do candidato em projetos anteriores. O workflow implementado recebe uma requisição via webhook, aciona a API do bot, salva o JSON resultante no Google Drive e registra os dados no Google Sheets.

## Desafios Enfrentados

**WAF CloudFront:** O principal desafio foi identificar que o portal utiliza WAF com detecção de automação. Chromium headless padrão era bloqueado sistematicamente. A solução com Chrome real (`channel="chrome"`) resolveu o problema.

**Banner de cookies LGPD:** O portal exibe um banner de consentimento em cada sessão. Após diversas tentativas de clique automatizado, a solução foi injetar o cookie de aceite (`lgpd-cookie`) diretamente no contexto do browser antes de qualquer navegação, combinado com um `MutationObserver` via `add_init_script` como fallback.

**Carregamento assíncrono dos resultados:** A página de busca carrega os resultados via JavaScript após o carregamento inicial do DOM. Foi necessário aguardar o seletor `a.link-busca-nome` estar presente antes de prosseguir com a navegação.

**Mudança na estrutura HTML:** Durante o desenvolvimento, o portal atualizou a estrutura HTML das seções de benefícios. O seletor `section[data-collapse]` foi substituído por `div.br-accordion`, exigindo atualização no parser.

## Endpoints da API

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/v1/consultar` | Consulta uma pessoa no Portal da Transparência |
| GET | `/api/v1/health` | Health check da API |

## Configuração

Crie um arquivo `.env` na raiz:

```env
HEADLESS=true
PLAYWRIGHT_TIMEOUT=45000
```

## Autor

Gustavo Oliveira Saud
[GitHub](https://github.com/robacenadev)
