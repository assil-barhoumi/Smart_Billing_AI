from fastapi import FastAPI
from api.invoices import router as invoices_router

app = FastAPI(title="AutomatingSales API", version="1.0")

app.include_router(invoices_router)


@app.get("/")
def root():
    return {"message": "AutomatingSales API is running"}
