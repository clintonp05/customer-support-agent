import structlog
import logging
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar('request_id', default='')
channel_id_var: ContextVar[str] = ContextVar('channel_id', default='')


def setup_logging():
    logging.basicConfig(
        format='%(message)s',
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger():
    return structlog.get_logger().bind(
        request_id=request_id_var.get(),
        channel_id=channel_id_var.get(),
    )


def bind_request_context(request_id: str, channel_id: str):
    request_id_var.set(request_id)
    channel_id_var.set(channel_id)


def get_request_context():
    return {
        'request_id': request_id_var.get(),
        'channel_id': channel_id_var.get(),
    }
