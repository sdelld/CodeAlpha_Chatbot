"""Hybrid retrieval over the knowledge base.

Lexical: TF-IDF (words + character n-grams) — works offline, robust to typos.
Semantic: Gemini embeddings (multilingual), cached on disk by content hash so documents are embedded only once.
Scores are combined; without an API key the lexical score is used alone.
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion

from .config import settings
from .knowledge import get_knowledge
from .lang import normalise_numbers, to_english_terms

log = logging.getLogger(__name__)


class Retriever:
    def __init__(self, knowledge=None, embedder=None):
        self.kb = knowledge or get_knowledge()
        self.docs = self.kb.documents
        self.vectorizer = FeatureUnion(
            [
                ("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")),
                ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)),
            ]
        )
        self.matrix = self.vectorizer.fit_transform([f"{d.title}. {d.text}" for d in self.docs])
        self.embedder = embedder
        self.doc_vectors = None
        self._query_cache = OrderedDict()
        self._lock = threading.Lock()
        if embedder is not None:
            self._load_embeddings()

    # ---------- embeddings ----------
    def _cache_path(self):
        return settings.cache_dir / f"embeddings-{settings.embedding_model}.json"

    def _load_embeddings(self):
        path = self._cache_path()
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        texts = [f"{d.title}. {d.text}" for d in self.docs]
        keys = [hashlib.sha256(t.encode()).hexdigest()[:24] for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in cache]
        if missing:
            try:
                vectors = self.embedder.embed([t for _, t in missing], task="RETRIEVAL_DOCUMENT")
                for (k, _), v in zip(missing, vectors, strict=True):
                    cache[k] = v
                settings.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(cache), encoding="utf-8")
                log.info("embeddings_cached", extra={"new": len(missing), "total": len(cache)})
            except Exception as e:  # keep working with lexical retrieval only
                log.warning("embeddings_unavailable", extra={"error": str(e)[:200]})
                self.embedder = None
                return
        m = np.array([cache[k] for k in keys], dtype=np.float32)
        self.doc_vectors = m / np.linalg.norm(m, axis=1, keepdims=True)

    def _query_vector(self, text):
        with self._lock:
            if text in self._query_cache:
                self._query_cache.move_to_end(text)
                return self._query_cache[text]
        v = np.array(self.embedder.embed([text], task="RETRIEVAL_QUERY")[0], dtype=np.float32)
        v /= np.linalg.norm(v)
        with self._lock:
            self._query_cache[text] = v
            if len(self._query_cache) > 2000:
                self._query_cache.popitem(last=False)
        return v

    # ---------- search ----------
    def search(self, query, k=5, kinds=None):
        expanded = to_english_terms(normalise_numbers(query))
        lexical = (self.matrix @ self.vectorizer.transform([expanded]).T).toarray().ravel()
        scores = lexical
        semantic = None
        if self.embedder is not None and self.doc_vectors is not None:
            try:
                semantic = self.doc_vectors @ self._query_vector(query)
                scores = 0.45 * lexical / (lexical.max() or 1) + 0.55 * np.clip(semantic, 0, None)
            except Exception as e:
                log.warning("query_embedding_failed", extra={"error": str(e)[:200]})
        order = np.argsort(-scores)
        hits = []
        for i in order:
            d = self.docs[i]
            if kinds and d.kind not in kinds:
                continue
            hits.append(
                {
                    "doc": d,
                    "score": float(scores[i]),
                    "lexical": float(lexical[i]),
                    "semantic": float(semantic[i]) if semantic is not None else None,
                }
            )
            if len(hits) >= k:
                break
        return hits
