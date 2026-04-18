from fastapi import APIRouter
from api.schemas import ConsultaRequest, ConsultaResponse
from bot.scraper import executar_consulta

router = APIRouter(prefix="/api/v1", tags=["Consulta"])


@router.post(
    "/consultar",
    response_model=ConsultaResponse,
    summary="Consulta uma pessoa no Portal da Transparência",
    description=(
        "Executa o robô para buscar dados de uma pessoa física pelo nome, CPF ou NIS. "
        "Retorna o panorama da relação com o Governo Federal, os benefícios encontrados "
        "e uma evidência da tela em Base64."
    ),
)
async def consultar(body: ConsultaRequest) -> ConsultaResponse:
    resultado = await executar_consulta(
        identificador=body.identificador,
        filtro_social=body.filtro_social,
    )
    return ConsultaResponse(**resultado)


@router.get("/health", tags=["Infra"], summary="Health check")
async def health():
    return {"status": "ok"}