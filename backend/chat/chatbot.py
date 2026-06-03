"""
Chatbot — GPT-4o over retrieved knowledge-graph context.

Retrieval (handled by Retriever) gives us two kinds of context:
  • Chunks   — raw text passages ranked by relevance
  • Subgraph — entity→relation→entity triples from N-hop traversal

Both are serialised into the user message.  The LLM answers the question
using that context and cites the source (collection + record ID) for every
claim it makes.

Streaming
---------
``chat()`` is a generator that yields text delta strings as they arrive from
OpenAI.  Callers (FastAPI StreamingResponse, CLI, tests) consume the stream.

Usage
-----
    from chat.chatbot import Chatbot
    from chat.retriever import Retriever
    from graph import get_graph_plugin

    bot = Chatbot(Retriever(get_graph_plugin()))

    for token in bot.chat("What are Acme Corp's payment obligations?"):
        print(token, end="", flush=True)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Generator, TYPE_CHECKING

from dotenv import load_dotenv
from openai import OpenAI

if TYPE_CHECKING:
    from chat.retriever import Retriever, RetrievalResult

# ── env ───────────────────────────────────────────────────────────────────────
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    load_dotenv(_env)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")

logger = logging.getLogger(__name__)

# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a knowledge-graph assistant.  You answer questions using the context \
provided — text passages retrieved from a knowledge graph and the graph's own \
entity–relation triples.

Rules:
1. Answer only from the provided context.  If the answer is not there, say so.
2. Cite every fact with its source in brackets, e.g. [contracts#3] or [emails#abc].
3. Be concise.  Use bullet points for lists of facts.
4. When the graph triples add detail not explicit in the passages, include it.
"""

_USER_TEMPLATE = """\
## Retrieved passages
{passages}

## Knowledge graph
{graph}

## Question
{query}
"""


# ── chatbot ───────────────────────────────────────────────────────────────────

class Chatbot:
    """
    GPT-4o chatbot grounded in retrieved knowledge-graph context.

    Parameters
    ----------
    retriever : Retriever instance (handles both vector + graph paths).
    model     : OpenAI model name (default from OPENAI_MODEL env var).
    api_key   : OpenAI API key   (default from OPENAI_API_KEY env var).
    top_chunks: Maximum number of ranked chunks to include in the prompt.
    top_edges : Maximum number of subgraph edges to include as triples.
    """

    def __init__(
        self,
        retriever:  "Retriever",
        model:      str = OPENAI_MODEL,
        api_key:    str = OPENAI_API_KEY,
        top_chunks: int = 6,
        top_edges:  int = 60,
    ) -> None:
        self._retriever  = retriever
        self._client     = OpenAI(api_key=api_key)
        self._model      = model
        self._top_chunks = top_chunks
        self._top_edges  = top_edges

    # ── public ────────────────────────────────────────────────────────────────

    def chat(self, query: str) -> Generator[str, None, None]:
        """
        Retrieve context and stream a GPT-4o answer.

        Yields text delta strings as they arrive.
        """
        result = self._retriever.retrieve(query)
        messages = self._build_messages(query, result)

        logger.info(
            "Chatbot: %d chunks | %d triples | model=%s",
            min(len(result.chunks), self._top_chunks),
            min(len(result.subgraph_edges), self._top_edges),
            self._model,
        )

        stream = self._client.chat.completions.create(
            model    = self._model,
            messages = messages,
            stream   = True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_messages(
        self,
        query:  str,
        result: "RetrievalResult",
    ) -> list[dict[str, str]]:
        passages = _format_passages(result.chunks[: self._top_chunks])
        graph    = _format_graph(
            result.subgraph_nodes,
            result.subgraph_edges[: self._top_edges],
        )

        return [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": _USER_TEMPLATE.format(
                passages = passages,
                graph    = graph or "(none)",
                query    = query.strip(),
            )},
        ]


# ── formatters ────────────────────────────────────────────────────────────────

def _format_passages(chunks) -> str:
    if not chunks:
        return "(no passages retrieved)"
    parts = []
    for i, c in enumerate(chunks, 1):
        label = f"{c.collection}#{c.record_id}"
        parts.append(f"[{i}] {label}  (score {c.score:.2f}, via {'+'.join(c.via)})\n{c.text.strip()}")
    return "\n\n".join(parts)


def _node_label(node: dict) -> str:
    """
    Format a node dict as a readable Cypher-like label with any extra
    attributes (all keys except id, name, type).

        (Acme Corp:Organization)
        (Net 30:Contractual_Term {value: "30 days"})
    """
    name = node.get("name", node.get("id", "?"))
    type_ = node.get("type", "")
    extras = {k: v for k, v in node.items() if k not in ("id", "name", "type")}
    if extras:
        attr_str = ", ".join(f'{k}: "{v}"' for k, v in extras.items())
        return f"({name}:{type_} {{{attr_str}}})"
    return f"({name}:{type_})"


def _format_graph(nodes: list[dict], edges: list[dict]) -> str:
    """
    Render the subgraph as Cypher-style triples with entity names and types.

    Each edge is formatted as:
        (SrcName:SrcType) -[RELATION]-> (DstName:DstType)

    Attributes on either node are included in curly braces when present.
    """
    if not edges:
        return ""

    # Build id → node dict so we can look up attributes for edge endpoints.
    # Falls back to just name+type if a node isn't in the traversal set.
    node_by_id: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}

    seen: set[tuple] = set()
    lines: list[str] = []

    for e in edges:
        key = (e["src"], e["type"], e["dst"])
        if key in seen:
            continue
        seen.add(key)

        # Resolve source node — prefer full node dict, fall back to edge fields
        src_node = node_by_id.get(e["src"], {
            "name": e.get("src_name", e["src"]),
            "type": e.get("src_type", ""),
        })
        dst_node = node_by_id.get(e["dst"], {
            "name": e.get("dst_name", e["dst"]),
            "type": e.get("dst_type", ""),
        })

        lines.append(
            f"{_node_label(src_node)} -[{e['type']}]-> {_node_label(dst_node)}"
        )

    return "\n".join(lines)
