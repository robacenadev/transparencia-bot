from fastapi import FastAPI
from api.routes import router

app = FastAPI(
    title="Transparência Bot API",
    description=(
        "Robô de automação web para consulta de pessoas físicas "
        "no Portal da Transparência do Governo Federal."
    ),
    version="1.0.0",
)

app.include_router(router)