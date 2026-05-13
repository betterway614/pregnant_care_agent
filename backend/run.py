"""AI-Care 后端启动入口"""
import os
import uvicorn

if __name__ == "__main__":
    use_reload = os.environ.get("RELOAD", "0") == "1"
    port = int(os.environ.get("PORT", "9999"))

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=use_reload,
        timeout_graceful_shutdown=30,
    )
