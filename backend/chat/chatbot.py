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
OpenAI.  In debug mode it yields SSE-formatted JSON events (``data: {...}\\n\\n``)
for every pipeline step before streaming token events.

Usage
-----
    from chat.chatbot import Chatbot
    from chat.retriever import Retriever
    from graph import get_graph_plugin

    bot = Chatbot(Retriever(get_graph_plugin()))

    # Normal streaming
    for token in bot.chat("What are Acme Corp's payment obligations?"):
        print(token, end="", flush=True)

    # Debug streaming — yields SSE step events then token events
    for event in bot.chat("...", debug=True):
        print(event)
"""

from __future__ import annotations

import json
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
## Retrieved passages (Graph RAG)
{passages}

## Knowledge graph (Cypher traversal)
{graph}

## Question
{query}
"""


# ── SSE helper ────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    """Encode a dict as an SSE data event: ``data: {...}\\n\\n``."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    def chat(self, query: str, debug: bool = False) -> Generator[str, None, None]:
        """
        Retrieve context and stream a GPT-4o answer.

        Normal mode  — yields raw text delta strings.
        Debug mode   — yields SSE-formatted JSON events:
            {"t":"step", "step":"retrieval"|"graph"|"prompt", ...}
            {"t":"token", "content":"..."}
            {"t":"done"}
        """
        result   = self._retriever.retrieve(query)
        messages = self._build_messages(query, result)

        if debug:
            yield from self._debug_steps(result, messages)

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
                if debug:
                    yield _sse({"t": "token", "content": delta})
                else:
                    yield delta

        if debug:
            yield _sse({"t": "done"})

    # ── debug steps ───────────────────────────────────────────────────────────

    def _debug_steps(
        self,
        result:   "RetrievalResult",
        messages: list[dict],
    ) -> Generator[str, None, None]:
        """Yield SSE step events describing every pipeline stage."""

        # Classify chunks by retrieval path
        vec_chunks  = [c for c in result.chunks if c.via == ["vector"]]
        grph_chunks = [c for c in result.chunks if c.via == ["graph"]]
        both_chunks = [c for c in result.chunks if len(c.via) > 1]

        # ── Step 1: Retrieval ─────────────────────────────────────────────────
        yield _sse({
            "t":     "step",
            "step":  "retrieval",
            "label": "Retrieval",
            "detail": {
                "embedding_dim":   768,
                "path_a_chunks":   len(vec_chunks) + len(both_chunks),
                "path_b_entities": len(result.entity_matches),
                "path_b_chunks":   len(grph_chunks) + len(both_chunks),
                "boosted_chunks":  len(both_chunks),
                "total_ranked":    len(result.chunks),
            },
            "entities": [
                {
                    "name": e.name,
                    "type": e.type,
                    "dist": round(e.score, 3),
                }
                for e in result.entity_matches
            ],
            "chunks": [
                {
                    "collection": c.collection,
                    "record_id":  c.record_id,
                    "score":      round(c.score, 3),
                    "via":        c.via,
                    "preview":    c.text[:200].strip(),
                }
                for c in result.chunks[: self._top_chunks]
            ],
        })

        # ── Step 2: Graph traversal ───────────────────────────────────────────
        yield _sse({
            "t":     "step",
            "step":  "graph",
            "label": "Graph Traversal",
            "detail": {
                "anchors": len(result.entity_matches),
                "hops":    2,
                "nodes":   len(result.subgraph_nodes),
                "edges":   len(result.subgraph_edges),
            },
            "edges": [
                {
                    "src": e.get("src_name", e["src"]),
                    "rel": e["type"],
                    "dst": e.get("dst_name", e["dst"]),
                }
                for e in result.subgraph_edges[: 40]
            ],
        })

        # ── Step 3: LLM prompt ────────────────────────────────────────────────
        yield _sse({
            "t":     "step",
            "step":  "prompt",
            "label": "LLM Prompt",
            "detail": {
                "model":    self._model,
                "messages": len(messages),
            },
            "messages": messages,
        })

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_messages(
        self,
        query:  str,
        result: "RetrievalResult",
    ) -> list[dict[str, str]]:
        passages = _format_passages(result.chunks[: self._top_chunks])
        graph    = _format_graph(
            result.entity_matches,
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
    Format a node dict as a Cypher-like node label with any extra attributes.

        (Acme Corp:Organization)
        (Net 30:Contractual_Term {value: "30 days"})
    """
    name  = node.get("name", node.get("id", "?"))
    type_ = node.get("type", "")
    extras = {k: v for k, v in node.items() if k not in ("id", "name", "type")}
    if extras:
        attr_str = ", ".join(f'{k}: "{v}"' for k, v in extras.items())
        return f"({name}:{type_} {{{attr_str}}})"
    return f"({name}:{type_})"


def _format_graph(
    entity_matches: list,
    nodes:          list[dict],
    edges:          list[dict],
) -> str:
    """
    Render the full Cypher traversal context for the LLM.

    Structure
    ---------
    Matched entities   — the KNN anchors directly tied to the query,
                         listed with all their attributes.
    Subgraph entities  — every other node reachable in the traversal.
    Relationships      — all edges within the subgraph, formatted as
                             (SrcName:SrcType) -[RELATION]-> (DstName:DstType)
    """
    if not entity_matches and not nodes and not edges:
        return ""

    parts: list[str] = []

    # ── 1. Matched entity anchors ──────────────────────────────────────────────
    if entity_matches:
        anchor_ids = {e.entity_id for e in entity_matches}
        parts.append("Matched entities:")
        node_by_id: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}
        for match in entity_matches:
            node = node_by_id.get(match.entity_id, {
                "name": match.name,
                "type": match.type,
            })
            parts.append(f"  {_node_label(node)}")
    else:
        anchor_ids: set[str] = set()

    # ── 2. Remaining subgraph nodes ────────────────────────────────────────────
    other_nodes = [n for n in nodes if n.get("id") not in anchor_ids]
    if other_nodes:
        parts.append("Subgraph entities:")
        for n in other_nodes:
            parts.append(f"  {_node_label(n)}")

    # ── 3. All relationships within the subgraph ───────────────────────────────
    if edges:
        node_by_id = {n["id"]: n for n in nodes if "id" in n}
        seen: set[tuple] = set()
        rel_lines: list[str] = []

        for e in edges:
            key = (e["src"], e["type"], e["dst"])
            if key in seen:
                continue
            seen.add(key)

            src_node = node_by_id.get(e["src"], {
                "name": e.get("src_name", e["src"]),
                "type": e.get("src_type", ""),
            })
            dst_node = node_by_id.get(e["dst"], {
                "name": e.get("dst_name", e["dst"]),
                "type": e.get("dst_type", ""),
            })
            rel_lines.append(
                f"  {_node_label(src_node)} -[{e['type']}]-> {_node_label(dst_node)}"
            )

        parts.append("Relationships:")
        parts.extend(rel_lines)

    return "\n".join(parts)
