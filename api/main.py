from fastapi import FastAPI
from api.invoices import router as invoices_router
from api.chat import router as chat_router

app = FastAPI(title="AutomatingSales API", version="1.0")

app.include_router(invoices_router)
app.include_router(chat_router)


@app.get("/")
def root():
    return {"message": "AutomatingSales API is running"}
