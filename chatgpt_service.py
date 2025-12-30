from __future__ import annotations
import os
from typing import List, Union
from dotenv import load_dotenv
from openai import OpenAI

def get_text_embedding_1024(
    text: Union[str, List[str]],
    *,
    model: str = "text-embedding-3-large",
    dimensions: int = 1024,
) -> Union[List[float], List[List[float]]]:
    """
    Generate embeddings using OpenAI's text-embedding-3-large model.

    - Loads OPENAI_API_KEY from .env
    - Returns 1024-dim embedding(s) by setting `dimensions=1024`

    Args:
        text: Input text (string) or list of strings.
        model: Embedding model name.
        dimensions: Desired embedding dimension length.

    Returns:
        A single embedding list[float] for string input, or list of embeddings for list input.
    """
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Add it to your .env file.")

    client = OpenAI(api_key=api_key)

    resp = client.embeddings.create(
        model=model,
        input=text,
        dimensions=dimensions,
    )

    embeddings = [item.embedding for item in resp.data]
    return embeddings[0] if isinstance(text, str) else embeddings