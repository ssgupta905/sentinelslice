"""InferenceService — manages Elasticsearch inference endpoint lifecycle."""
import logging
from services.elastic_service import ElasticService

logger = logging.getLogger(__name__)


class InferenceService:
    def __init__(self, elastic_svc: ElasticService):
        self.es_svc = elastic_svc

    def configure_inference(self, inference_id: str, openai_api_key: str, model_id: str):
        self.es_svc.configure_inference(
            inference_id=inference_id,
            openai_api_key=openai_api_key,
            model_id=model_id,
        )
        logger.info("Inference endpoint configured via ElasticService.")
