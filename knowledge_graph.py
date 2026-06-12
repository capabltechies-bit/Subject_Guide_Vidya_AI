"""
knowledge_graph.py  ─  Week 3-4 New
Builds an academic knowledge graph from indexed study materials using Gemini.
Returns nodes and edges ready for vis.js / D3.js visualisation.
"""

import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv
from vector_store import get_all_chunks_sample

load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))

_MODEL = "gemini-2.5-flash"


def _call_gemini(system_prompt: str, user_msg: str, model_name: str = None, api_key: str = None) -> str:
    import llm_client
    return llm_client.call_llm(
        system_prompt=system_prompt,
        user_message=user_msg,
        model_name=model_name or _MODEL,
        gemini_key=api_key,
    )



def _safe_json(text: str) -> dict | list | None:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


# ── Node type → color mapping ─────────────────────────────────────────────────
_TYPE_COLORS = {
    "concept":     "#6c8ef5",   # blue    — main ideas
    "definition":  "#4ecb8d",   # green   — key terms
    "algorithm":   "#f0b84a",   # gold    — procedures
    "formula":     "#f07070",   # rose    — math
    "application": "#a78bfa",   # purple  — use cases
    "theory":      "#38bdf8",   # cyan    — theoretical frameworks
}

_TYPE_SIZES = {
    "concept":     30,
    "definition":  22,
    "algorithm":   28,
    "formula":     24,
    "application": 20,
    "theory":      26,
}

# ── KG extraction prompt ─────────────────────────────────────────────────────

_KG_SYSTEM = """\
You are an expert knowledge graph builder for academic content.
You MUST respond with ONLY a valid JSON object — no prose, no markdown fences, nothing else.

From the given study material excerpts, extract an academic knowledge graph.

Required JSON schema:
{
  "nodes": [
    {
      "id": "snake_case_unique_id",
      "label": "Human-readable topic name",
      "type": "concept|definition|algorithm|formula|application|theory",
      "description": "One-sentence description of this node"
    }
  ],
  "edges": [
    {
      "from": "source_node_id",
      "to": "target_node_id",
      "label": "relationship description",
      "type": "prerequisite|contains|related|applies_to|implements|extends|defines"
    }
  ]
}

Rules:
- Extract 12–20 meaningful topic nodes (not too granular, not too broad).
- Node IDs must be snake_case strings (e.g., "binary_tree", "sorting_algorithms").
- Every edge must reference existing node IDs.
- Edge labels should be concise verbs/phrases: "is a type of", "requires", "uses", "leads to", "implements", "is used in".
- Cover the most important conceptual relationships in the material.
- Types: concept (core idea), definition (key term), algorithm (step procedure), formula (math expression), application (real use case), theory (theoretical framework).
"""


def build_knowledge_graph(subject: str = None, model_name: str = None, api_key: str = None) -> dict:
    """
    Build a knowledge graph from all indexed documents.
    Returns {"nodes": [...], "edges": [...]} with colour/size annotations.
    """
    sample_chunks = get_all_chunks_sample(max_per_doc=6)
    if not sample_chunks:
        return {"nodes": [], "edges": [], "error": "No documents indexed yet."}

    # Combine samples, capped at ~5000 chars to stay within context
    combined = "\n\n---\n\n".join(sample_chunks)[:5000]
    filter_note = f"\nFocus primarily on the subject: {subject}." if subject else ""

    user_msg = f"""Study material excerpts:{filter_note}

{combined}

Extract the knowledge graph. Output ONLY the JSON object."""

    raw   = _call_gemini(_KG_SYSTEM, user_msg, model_name, api_key)
    graph = _safe_json(raw)

    if not isinstance(graph, dict) or "nodes" not in graph:
        return {"nodes": [], "edges": [], "error": "Could not parse knowledge graph from Gemini response."}

    # Annotate with visual properties
    for node in graph.get("nodes", []):
        ntype = node.get("type", "concept")
        node["color"] = _TYPE_COLORS.get(ntype, "#6c8ef5")
        node["size"]  = _TYPE_SIZES.get(ntype, 24)

    # Validate edges reference real node IDs
    valid_ids = {n["id"] for n in graph.get("nodes", [])}
    graph["edges"] = [
        e for e in graph.get("edges", [])
        if e.get("from") in valid_ids and e.get("to") in valid_ids
    ]

    return graph


def get_topic_subgraph(topic: str, full_graph: dict) -> dict:
    """
    Filter the full graph to show only nodes/edges connected to a topic.
    Performs a 1-hop neighbourhood expansion.
    """
    if not full_graph.get("nodes"):
        return full_graph

    topic_lower = topic.lower()

    # Seed: nodes whose label or description matches the topic
    seed_ids: set[str] = set()
    for node in full_graph["nodes"]:
        if (
            topic_lower in node.get("label", "").lower()
            or topic_lower in node.get("description", "").lower()
        ):
            seed_ids.add(node["id"])

    # 1-hop expansion
    for edge in full_graph["edges"]:
        if edge["from"] in seed_ids:
            seed_ids.add(edge["to"])
        if edge["to"] in seed_ids:
            seed_ids.add(edge["from"])

    filtered_nodes = [n for n in full_graph["nodes"] if n["id"] in seed_ids]
    filtered_edges = [
        e for e in full_graph["edges"]
        if e["from"] in seed_ids and e["to"] in seed_ids
    ]
    return {"nodes": filtered_nodes, "edges": filtered_edges}


# ── vis.js HTML renderer ──────────────────────────────────────────────────────

def render_graph_html(graph: dict, height: int = 520) -> str:
    """
    Produce a self-contained HTML string that renders the graph using vis.js.
    Suitable for use with st.components.v1.html().
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    vis_nodes = [
        {
            "id":    n["id"],
            "label": n["label"],
            "title": n.get("description", n["label"]),
            "color": {
                "background": n.get("color", "#6c8ef5"),
                "border":     "#ffffff33",
                "highlight":  {"background": "#ffffff", "border": n.get("color", "#6c8ef5")},
            },
            "size":  n.get("size", 24),
            "font":  {"color": "#eceef5", "size": 13},
        }
        for n in nodes
    ]

    vis_edges = [
        {
            "from":   e["from"],
            "to":     e["to"],
            "label":  e.get("label", ""),
            "arrows": "to",
            "color":  {"color": "#2a3045", "highlight": "#6c8ef5"},
            "font":   {"color": "#a0a8c0", "size": 10, "align": "middle"},
            "smooth": {"type": "continuous"},
        }
        for e in edges
    ]

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0d0f14; overflow: hidden; }}
    #network {{
      width: 100%;
      height: {height}px;
      background: #0d0f14;
      border: 1px solid #2a3045;
      border-radius: 12px;
    }}
  </style>
</head>
<body>
  <div id="network"></div>
  <script>
    const nodes = new vis.DataSet({nodes_json});
    const edges = new vis.DataSet({edges_json});

    const container = document.getElementById("network");
    const data      = {{ nodes, edges }};
    const options   = {{
      nodes: {{
        shape: "dot",
        borderWidth: 1.5,
        shadow: true,
      }},
      edges: {{
        width: 1.5,
        shadow: false,
        smooth: {{ type: "curvedCW", roundness: 0.15 }},
      }},
      physics: {{
        solver: "forceAtlas2Based",
        forceAtlas2Based: {{
          gravitationalConstant: -40,
          centralGravity: 0.008,
          springLength: 130,
          springConstant: 0.04,
          damping: 0.6,
        }},
        stabilization: {{ iterations: 200 }},
      }},
      interaction: {{
        hover: true,
        tooltipDelay: 150,
        navigationButtons: false,
        zoomView: true,
        dragView: true,
      }},
    }};

    new vis.Network(container, data, options);
  </script>
</body>
</html>
"""