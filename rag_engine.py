import logging
from typing import Generator, List, Optional

from google import genai
from google.genai import types

_logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = (
    "You are PawPal+, an expert pet care assistant integrated into a daily scheduling app. "
    "You receive two types of context with every question:\n"
    "1. RETRIEVED KNOWLEDGE: Relevant pet care facts retrieved from a curated knowledge base\n"
    "2. OWNER'S PET DATA: The owner's actual pets, their species, and currently scheduled tasks\n\n"
    "Instructions:\n"
    "- Use the retrieved knowledge to give accurate, evidence-based pet care advice\n"
    "- Personalize your response using the owner's specific pet data (names, species, existing tasks)\n"
    "- If asked what tasks to add, reference existing tasks to avoid suggesting duplicates\n"
    "- Be specific and actionable — give concrete recommendations with realistic time estimates\n"
    "- Keep responses focused (2-4 paragraphs)\n"
    "- If the retrieved knowledge does not cover the question well, say so clearly and fall back "
    "to general expertise"
)


class RAGEngine:
    """Retrieval-Augmented Generation engine for pet care Q&A.

    Builds a TF-IDF index over a knowledge base of pet care chunks at
    construction time, then retrieves the most relevant chunks for each
    query and passes them — together with the owner's live pet data — to
    Gemini to produce a personalized answer.
    """

    def __init__(self, chunks: List[str]) -> None:
        self.chunks = chunks
        self._build_index()
        _logger.info("RAG index built with %d knowledge chunks", len(chunks))

    def _build_index(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=5000,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.chunks)

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """Return the top-k most relevant knowledge chunks for *query*."""
        from sklearn.metrics.pairwise import cosine_similarity
        try:
            query_vec = self.vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self.tfidf_matrix)[0]
            top_indices = scores.argsort()[-top_k:][::-1]
            results = [
                (self.chunks[i], float(scores[i]))
                for i in top_indices
                if scores[i] > 0.01
            ]
            _logger.info(
                "Retrieved %d chunk(s) | query='%s' | scores=%s",
                len(results),
                query[:60],
                [round(s, 3) for _, s in results],
            )
            return [chunk for chunk, _ in results]
        except Exception as exc:
            _logger.error("Retrieval error for query '%s': %s", query[:60], exc)
            return []

    def _build_user_message(
        self, question: str, pet_context: str, retrieved: List[str]
    ) -> str:
        if retrieved:
            knowledge_section = "\n\n".join(f"• {chunk}" for chunk in retrieved)
        else:
            knowledge_section = (
                "No closely matching entries found in the knowledge base for this query."
            )
        return (
            f"RETRIEVED PET CARE KNOWLEDGE:\n{knowledge_section}\n\n"
            f"OWNER'S CURRENT PET DATA:\n{pet_context}\n\n"
            f"Question: {question}"
        )

    def stream_answer(
        self,
        question: str,
        pet_context: str,
        api_key: str,
        retrieved_chunks: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        """Stream an answer token-by-token using the Gemini API."""
        if retrieved_chunks is None:
            retrieved_chunks = self.retrieve(question)

        user_message = self._build_user_message(question, pet_context, retrieved_chunks)
        _logger.info("Starting streamed Gemini call | question='%s'", question[:60])

        try:
            client = genai.Client(api_key=api_key)
            response_stream = client.models.generate_content_stream(
                model=MODEL,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=1024,
                ),
            )
            last_chunk = None
            for chunk in response_stream:
                last_chunk = chunk
                if chunk.text:
                    yield chunk.text
            if last_chunk and last_chunk.usage_metadata:
                _logger.info(
                    "Stream complete | input=%d | output=%d",
                    last_chunk.usage_metadata.prompt_token_count or 0,
                    last_chunk.usage_metadata.candidates_token_count or 0,
                )
        except Exception as exc:
            _logger.error("Gemini API error: %s", exc)
            msg = str(exc)
            if any(k in msg for k in ("API_KEY", "UNAUTHENTICATED", "PERMISSION_DENIED")):
                raise ValueError(
                    "Invalid API key. Check your GEMINI_API_KEY in the .env file."
                )
            elif "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                raise ValueError("API rate limit exceeded. Please wait a moment and try again.")
            elif "connect" in msg.lower() or "network" in msg.lower():
                raise ValueError(
                    "Cannot connect to AI service. Check your internet connection."
                )
            else:
                raise ValueError(f"AI service error: {exc}")

    def answer(self, question: str, pet_context: str, api_key: str) -> str:
        """Return a complete (non-streaming) answer — useful for automated tests."""
        retrieved = self.retrieve(question)
        user_message = self._build_user_message(question, pet_context, retrieved)
        _logger.info("Starting non-streamed Gemini call | question='%s'", question[:60])

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=MODEL,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=1024,
                ),
            )
            _logger.info(
                "Answer complete | input=%d | output=%d",
                response.usage_metadata.prompt_token_count or 0,
                response.usage_metadata.candidates_token_count or 0,
            )
            return response.text
        except Exception as exc:
            _logger.error("Gemini API error: %s", exc)
            msg = str(exc)
            if any(k in msg for k in ("API_KEY", "UNAUTHENTICATED", "PERMISSION_DENIED")):
                raise ValueError("Invalid API key. Check your GEMINI_API_KEY.")
            elif "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                raise ValueError("Rate limit exceeded. Please wait and try again.")
            elif "connect" in msg.lower():
                raise ValueError("Cannot connect to AI service.")
            else:
                raise ValueError(f"AI service error: {exc}")
