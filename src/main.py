from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router as api_router
from src.constants import X_REQUEST_ID_HEADER, X_CHANNEL_ID_HEADER, MISSING_HEADERS_ERROR
from src.observability.logger import setup_logging, bind_request_context, get_logger
from src.db.connector import init_db_pool, close_db_pool
from src.rag.retriever import get_retriever


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Noon Prep Support Agent",
        description="Customer support microservice using LangGraph orchestration",
        version="0.1.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_context(request: Request, call_next):
        request_id = request.headers.get(X_REQUEST_ID_HEADER)
        channel_id = request.headers.get(X_CHANNEL_ID_HEADER)

        if not request_id or not channel_id:
            return JSONResponse({"detail": MISSING_HEADERS_ERROR}, status_code=400)

        bind_request_context(request_id, channel_id)
        logger = get_logger().bind(method=request.method, path=request.url.path)
        request.state.logger = logger
        logger.info("request.received")

        response = await call_next(request)
        logger.info("request.completed", status_code=response.status_code)
        return response

    app.include_router(api_router)
    app.add_event_handler("startup", startup)
    app.add_event_handler("shutdown", shutdown)
    return app


async def startup():
    logger = get_logger()
    logger.info("startup", msg="Noon Prep API starting up")
    try:
        init_db_pool(minconn=1, maxconn=10, retries=5, delay_s=1.0)
    except Exception as exc:
        logger.exception("startup.db_init_failed", exc=str(exc))
        logger.warning("startup.db_unavailable", msg="Proceeding without DB connection. Some features may fail.")

    # Initialize RAG retriever and embedder once at startup to avoid repeated model downloads
    try:
        get_retriever()
        logger.info("startup.rag_initialized", msg="RAG retriever and embedder initialized")
    except Exception as exc:
        logger.exception("startup.rag_init_failed", exc=str(exc))


async def shutdown():
    logger = get_logger()
    logger.info("shutdown", msg="Noon Prep API shutting down")
    try:
        close_db_pool()
    except Exception as exc:
        logger.exception("shutdown.db_close_failed", exc=str(exc))


app = create_app()
