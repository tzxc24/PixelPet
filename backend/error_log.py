"""Log service failure metadata without request or provider contents."""
import logging

logger = logging.getLogger('pixelpet.service_errors')


def service_failure(stage: str, status: int) -> None:
    logger.warning('stage=%s status=%d', stage, status)
