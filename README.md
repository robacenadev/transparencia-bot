# Transparência Bot

Bot de automação web (RPA) para consulta de pessoas físicas no Portal da Transparência do Governo Federal, desenvolvido como desafio técnico para a vaga de Full Stack Developer Python (RPA e Hiperautomação).

## Sobre o Projeto

O bot realiza consultas automatizadas no Portal da Transparência, coletando dados do panorama da pessoa física, extraindo detalhes dos benefícios recebidos e retornando as informações em formato JSON com evidência em Base64.

## Stack

| Tecnologia | Versão | Uso |
|---|---|---|
| Python | 3.12 | Linguagem principal |
| FastAPI | 0.115 | API REST com documentação Swagger automática |
| Playwright | 1.47 | Automação do browser |
| Docker + Docker Compose | — | Containerização dos serviços |
| n8n | 2.14 | Orquestração do workflow (Parte 2) |

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
├── n8n/
│   └── workflow.json    # Workflow exportado do n8n (Parte 2)
├── docker-compose.yml   # Bot API (8001) + n8n (5678)
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Como Executar

**Pré-requisitos:** Docker e Docker Compose instalados.

```bash
git clone https://github.com/robacenadev/transparencia-bot.git
cd transparencia-bot
cp .env.example .env
docker compose up --build
```

| Serviço | URL |
|---|---|
| API (Swagger) | http://localhost:8001/docs |
| n8n | http://localhost:5678 |

### Configuração do n8n (Parte 2)

1. Acesse http://localhost:5678 e faça login (`admin` / `admin123`)
2. Vá em **Settings → Import workflow** e importe o arquivo `n8n/workflow.json`
3. Configure as credenciais do Google Drive e Google Sheets no n8n
4. Ative o workflow

## Variáveis de Ambiente

Crie um arquivo `.env` na raiz a partir do exemplo:

```bash
cp .env.example .env
```

Conteúdo do `.env.example`:

```env
HEADLESS=true
PLAYWRIGHT_TIMEOUT=45000
```

## Exemplos de Requisição

### Busca por nome
```bash
curl -X POST http://localhost:8001/api/v1/consultar \
  -H "Content-Type: application/json" \
  -d '{"identificador": "João da Silva", "filtro_social": false}'
```

### Busca por CPF
```bash
curl -X POST http://localhost:8001/api/v1/consultar \
  -H "Content-Type: application/json" \
  -d '{"identificador": "123.456.789-00"}'
```

### Busca com filtro social
```bash
curl -X POST http://localhost:8001/api/v1/consultar \
  -H "Content-Type: application/json" \
  -d '{"identificador": "Silva", "filtro_social": true}'
```

### Resposta de sucesso

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
    "RECEBIMENTOS DE RECURSOS": [
      {
        "tipo": "RECEBIMENTOS DE RECURSOS",
        "dados": {
          "Mês de disponibilização": "12/2020",
          "Parcela": "5",
          "UF": "MG",
          "Município": "BELO HORIZONTE",
          "Enquadramento": "EXTRACAD",
          "Valor (R$)": "600,00",
          "Observação": "NÃO HÁ"
        }
      }
    ]
  },
  "evidencia_base64": "iVBORw0KGgo..."
}
```

### Resposta de erro — nome inexistente

```json
{
  "status": "erro",
  "mensagem": "Foram encontrados 0 resultados para o termo 'Nome Inexistente'",
  "identificador": "Nome Inexistente",
  "panorama": null,
  "beneficios": null,
  "evidencia_base64": "iVBORw0KGgo..."
}
```

### Resposta de erro — CPF/NIS inexistente

```json
{
  "status": "erro",
  "mensagem": "Não foi possível retornar os dados no tempo de resposta solicitado",
  "identificador": "999.999.999-99",
  "panorama": null,
  "beneficios": null,
  "evidencia_base64": "iVBORw0KGgo..."
}
```

## Endpoints da API

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/v1/consultar` | Consulta uma pessoa no Portal da Transparência |
| GET | `/api/v1/health` | Health check da API |

## Decisões Técnicas

### Playwright com Chromium headless

O Portal da Transparência utiliza AWS CloudFront com WAF (Web Application Firewall). O Chromium headless do Playwright passa pelo WAF com as configurações de contexto aplicadas: user agent realista, anti-detecção via `add_init_script` e cabeçalhos de linguagem.

```python
await context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
    window.chrome = {runtime: {}};
""")
```

### Referer para navegação no panorama

O portal verifica o cabeçalho `Referer` ao acessar a página de detalhes da pessoa. Sem ele, a requisição retorna 403.

```python
await page.goto(url_panorama, referer=url_resultados, wait_until="load")
```

### Estrutura do accordion de benefícios

O `div.content` de cada seção de benefícios é **irmão** do `div.item`, não filho. A navegação usa o atributo `aria-controls` do botão para localizar o conteúdo correto.

```python
aria_controls = await header_btn.get_attribute("aria-controls")
content = await page.query_selector(f"#{aria_controls}")
```

### Evidência com accordion expandido

O screenshot é capturado ao final da execução, após voltar ao panorama, remover elementos `fixed`/`sticky` (banner de cookies) e expandir todos os accordions.

```python
await page.evaluate("""
    document.querySelectorAll('*').forEach(el => {
        const style = window.getComputedStyle(el);
        if (style.position === 'fixed' || style.position === 'sticky') {
            el.remove();
        }
    });
""")
```

### Detecção de CPF/NIS vs nome

A mensagem de erro varia conforme o tipo de identificador. CPF e NIS contêm apenas dígitos e pontuação.

```python
is_cpf_nis = bool(re.match(r'^[\d.\-/]+$', identificador.strip()))
```

### n8n como plataforma de orquestração (Parte 2)

O n8n foi escolhido por ser open source, ter integração nativa com Google Drive e Google Sheets, e estar disponível como serviço no mesmo `docker-compose` do projeto. O workflow implementado segue o fluxo:

```
Webhook ──────────────────────────→ HTTP Request → Google Drive → Google Sheets
Manual Trigger → Dados de Teste ──↗
```

## Desafios Enfrentados

**WAF CloudFront:** O Chromium headless padrão era detectado e bloqueado com erro 403. A solução foi combinar user agent realista com `add_init_script` para remover propriedades que identificam automação.

**Banner de cookies LGPD:** O portal exibe um banner de consentimento que sobrepõe os elementos da página. A solução definitiva foi remover via JavaScript todos os elementos com `position: fixed` ou `sticky` antes de capturar o screenshot.

**Estrutura do accordion:** O `div.content` dos benefícios não é filho do `div.item` — é irmão. O código usa `aria-controls` para localizar o elemento correto pelo ID.

**Carregamento assíncrono:** A página de resultados carrega os itens via JavaScript. O bot aguarda explicitamente o seletor `a.link-busca-nome` antes de prosseguir.

**Mudança na estrutura HTML:** Durante o desenvolvimento, o portal atualizou a estrutura das seções de benefícios de `section[data-collapse]` para `div.br-accordion`, exigindo atualização nos seletores.

## Autor

Gustavo Oliveira Saud  
[GitHub](https://github.com/robacenadev)
