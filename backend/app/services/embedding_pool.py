import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List
from sentence_transformers import SentenceTransformer
from app.config import settings

MODEL_NAME = "all-MiniLM-L6-v2"

class EmbeddingPool:
    def __init__(self, num_workers: int = None, batch_size: int = None):
        self.num_workers = num_workers or settings.embedding_workers
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model: SentenceTransformer = None
        self._executor: ThreadPoolExecutor = None

    async def start(self):
        if os.getenv("LOAD_TEST_MODE"):
            # Skip model loading in load test mode — embed() returns random vectors
            return
        loop = asyncio.get_event_loop()
        self._executor = ThreadPoolExecutor(
            max_workers=self.num_workers,
            thread_name_prefix="embedding"
        )
        # Load model in thread to avoid blocking event loop
        self._model = await loop.run_in_executor(
            self._executor,
            lambda: SentenceTransformer(MODEL_NAME)
        )

    async def stop(self):
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    async def embed(self, text: str) -> List[float]:
        # ponytail: random vector for load tests — avoids model loading, zero cost
        if os.getenv("LOAD_TEST_MODE"):
            import random
            return [random.gauss(0, 0.1) for _ in range(384)]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._model.encode(
                [text], normalize_embeddings=True, show_progress_bar=False
            )[0].tolist()
        )
        return result

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if os.getenv("LOAD_TEST_MODE"):
            import random
            return [[random.gauss(0, 0.1) for _ in range(384)] for _ in texts]
        loop = asyncio.get_event_loop()
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_result = await loop.run_in_executor(
                self._executor,
                lambda b=batch: self._model.encode(
                    b, normalize_embeddings=True, show_progress_bar=False
                ).tolist()
            )
            all_embeddings.extend(batch_result)

        return all_embeddings

# Module-level singleton — started in main.py startup
embedding_pool = EmbeddingPool()
