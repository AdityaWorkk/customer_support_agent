from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings


def get_chat_model(model: str | None = None, temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    """Single seam for the LLM provider. Swap the body to change vendors."""
    kwargs = {}
    if settings.LLM_THINKING_BUDGET >= 0:
        kwargs["thinking_budget"] = settings.LLM_THINKING_BUDGET
    return ChatGoogleGenerativeAI(model=model or settings.LLM_MODEL, google_api_key=settings.GOOGLE_API_KEY,
                                  temperature=temperature, max_retries=2, timeout=60, **kwargs)


def text_of(content) -> str:
    """Gemini may return a string or a list of content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in content if isinstance(p, (str, dict)))
    return ""
