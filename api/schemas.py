from pydantic import BaseModel, Field


class ConsultaRequest(BaseModel):
    identificador: str = Field(
        ...,
        description="Nome completo, CPF ou NIS da pessoa a consultar",
        examples=["João Silva", "123.456.789-00"],
    )
    filtro_social: bool = Field(
        default=False,
        description="Aplica o filtro 'BENEFICIÁRIO DE PROGRAMA SOCIAL'",
    )


class ConsultaResponse(BaseModel):
    status: str = Field(description="'sucesso' ou 'erro'")
    identificador: str
    mensagem: str | None = None
    panorama: dict | None = None
    beneficios: dict | None = None
    evidencia_base64: str | None = Field(
        default=None,
        description="Screenshot da tela em Base64, usado como evidência da execução",
    )