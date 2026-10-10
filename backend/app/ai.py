import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


SYSTEM_PROMPT = """You are DocuMind, a grounded document assistant.
Answer only from the provided sources. If the sources do not support an answer, say that the evidence is insufficient.
Answer in Korean unless the user asks for another language. Keep the answer concise and cite sources using [filename, page/chunk].
"""


def _build_client():
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AzureOpenAI

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    if azure_endpoint and os.getenv("AZURE_OPENAI_USE_ENTRA", "true").lower() == "true":
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        return AzureOpenAI(
            azure_ad_token_provider=token_provider,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_endpoint=azure_endpoint,
        ), os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini-gs")
    if azure_endpoint and azure_key:
        return AzureOpenAI(
            api_key=azure_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            azure_endpoint=azure_endpoint,
        ), os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini-gs")

    return None, None


def generate_grounded_answer(question: str, sources: list[dict]) -> str | None:
    client, model = _build_client()
    if client is None or not sources:
        return None

    context = "\n\n".join(
        f"SOURCE {index}: {source['filename']} | page={source.get('page_number')} | chunk={source['chunk_id']}\n{source['excerpt']}"
        for index, source in enumerate(sources, start=1)
    )
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        max_tokens=700,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question:\n{question}\n\nSources:\n{context}"},
        ],
    )
    return response.choices[0].message.content or None
