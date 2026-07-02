from fastapi import FastAPI

app = FastAPI(
    title="Yomiba",
    version="0.0.1"
)


@app.get("/")
def root():
    return {
        "message": "Welcome to Yomiba!"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }