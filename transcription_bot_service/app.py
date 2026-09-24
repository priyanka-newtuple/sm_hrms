from fastapi import FastAPI

app = FastAPI()


@app.post("/bot/start")
async def start_bot(payload: dict):
    # TODO: Implement Playwright automation and audio capture
    return {"success": False, "message": "Bot service not implemented"}


@app.post("/bot/stop")
async def stop_bot(payload: dict):
    # TODO: Implement bot shutdown
    return {"success": False, "message": "Bot service not implemented"}
