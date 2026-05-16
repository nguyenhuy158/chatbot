"""LangGraph node implementations.

Phase 1: scaffold
Phase 2: RAG wired
Phase 3: Memory load + save wired
Phase 5: Tool planning + tool_call node + tool result feedback loop

Flow:
  load_memory → plan → [rag | tool | direct]
  rag → plan (so model can decide to follow up with tool)
  tool → plan (so model can chain tools or finalize)
  direct → generate → moderation → save_memory → END
"""
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.state import AgentState
from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.memory import extract_memories, memory_store
from app.rag import retrieve
from app.services.llm_gateway import llm_gateway
from app.tools import execute_tool, get_tool_specs_for_llm

logger = get_logger(__name__)


ROLE_COLLECTIONS = {
    "external": ["public_docs", "faq"],
    "internal": ["public_docs", "faq", "internal_sop"],
    "admin": ["public_docs", "faq", "internal_sop"],
}


# --- load_memory ---

async def load_memory(state: AgentState) -> dict:
    query = _latest_user_message(state)
    if not query:
        return {"memories": []}

    async with AsyncSessionLocal() as db:
        records = await memory_store.search(
            db=db,
            tenant_id=state["tenant_id"],
            user_id=state["user_id"],
            query=query,
            top_k=5,
        )
    memories = [
        {"id": str(r.id), "type": r.memory_type, "content": r.content}
        for r in records
    ]
    return {"memories": memories}


# --- plan ---

PLAN_SYSTEM = """You are the planner for an agentic chatbot. Decide the next action based on the conversation and available context.

Output ONLY valid JSON:
{
  "intent": "rag" | "tool" | "direct",
  "tool_calls": [{"name": "<tool>", "args": {...}}]  // only if intent="tool"
}

Rules:
- "rag": if the user is asking about company-specific info, policies, FAQs, or knowledge base content
- "tool": if you need current data (web), math, or time. List 1-3 tool calls.
- "direct": if you can answer from conversation context + memory + retrieved RAG (already in this turn)
- Stop after 3 iterations and answer with what you have.
"""


async def plan(state: AgentState) -> dict:
    iteration = state.get("iteration", 0) + 1
    role = state.get("role", "external")
    has_rag = bool(state.get("rag_results"))
    has_tool_results = bool(state.get("tool_results"))

    # Hard stop on max iterations
    if iteration > settings.LLM_MAX_ITERATIONS:
        return {"intent": "direct", "iteration": iteration, "pending_tool_calls": []}

    # First iteration: try RAG if collections accessible and no tools/rag yet
    if iteration == 1 and ROLE_COLLECTIONS.get(role) and not has_rag:
        return {"intent": "rag", "iteration": iteration, "pending_tool_calls": []}

    # Otherwise ask LLM to plan
    tool_specs = get_tool_specs_for_llm(role)
    tool_summary = "\n".join(
        f"- {t['name']}: {t['description']}" for t in tool_specs
    ) or "(no tools available)"

    rag_summary = ""
    if has_rag:
        snippets = state.get("rag_results", [])[:3]
        rag_summary = "RAG already returned " + str(len(state["rag_results"])) + " chunks. Top titles: " + ", ".join(
            s.get("title", "") for s in snippets
        )

    tool_result_summary = ""
    if has_tool_results:
        tool_result_summary = "Tool results so far: " + ", ".join(
            t.get("name", "") for t in state.get("tool_results", [])
        )

    user_q = _latest_user_message(state)
    context_block = f"User question: {user_q}\nAvailable tools:\n{tool_summary}\n{rag_summary}\n{tool_result_summary}"

    try:
        response = await llm_gateway.invoke(
            [
                SystemMessage(content=PLAN_SYSTEM),
                HumanMessage(content=context_block),
            ],
            tier="cheap",
        )
        content = str(response.content).strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        intent = data.get("intent", "direct")
        tool_calls = data.get("tool_calls", []) if intent == "tool" else []
        # Cap tool calls per iteration
        tool_calls = tool_calls[:3]

        logger.info("plan", intent=intent, iteration=iteration, tools=len(tool_calls))
        return {
            "intent": intent,
            "iteration": iteration,
            "pending_tool_calls": tool_calls,
        }
    except Exception as e:
        logger.warning("plan_failed_fallback_direct", error=str(e))
        return {"intent": "direct", "iteration": iteration, "pending_tool_calls": []}


# --- rag_search ---

async def rag_search(state: AgentState) -> dict:
    role = state.get("role", "external")
    collections = ROLE_COLLECTIONS.get(role, ROLE_COLLECTIONS["external"])
    query = _latest_user_message(state)
    if not query:
        return {"rag_results": [], "rag_citations": []}

    async with AsyncSessionLocal() as db:
        result = await retrieve(
            db=db,
            query=query,
            tenant_id=state["tenant_id"],
            collections=collections,
        )

    return {
        "rag_results": [
            {
                "content": c.content,
                "title": c.document_title,
                "page": c.page,
                "distance": c.distance,
            }
            for c in result.chunks
        ],
        "rag_citations": [c.to_dict() for c in result.citations],
        "metadata": {
            **(state.get("metadata") or {}),
            "rag_context": result.context_for_llm,
            "rag_sources": result.source_list,
        },
    }


# --- tool_call ---

async def tool_call(state: AgentState) -> dict:
    """Execute all pending tool calls from the planner. Accumulate results."""
    pending = state.get("pending_tool_calls", []) or []
    if not pending:
        return {"tool_results": state.get("tool_results", [])}

    role = state.get("role", "external")
    results = list(state.get("tool_results", []) or [])

    async with AsyncSessionLocal() as db:
        for call in pending:
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            try:
                result = await execute_tool(
                    db=db,
                    tool_name=name,
                    raw_args=args,
                    user_id=state["user_id"],
                    tenant_id=state["tenant_id"],
                    role=role,
                )
                results.append({
                    "name": name,
                    "args": args,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                })
                logger.info("tool_executed", name=name, success=result.success)
            except Exception as e:
                logger.warning("tool_exec_failed", name=name, error=str(e))
                results.append({
                    "name": name,
                    "args": args,
                    "success": False,
                    "output": None,
                    "error": str(e),
                })
        await db.commit()

    return {"tool_results": results, "pending_tool_calls": []}


# --- generate ---

async def generate(state: AgentState) -> dict:
    lang = state.get("lang", "vi")
    metadata = state.get("metadata", {}) or {}
    rag_context = metadata.get("rag_context", "")
    rag_sources = metadata.get("rag_sources", "")
    memories = state.get("memories", []) or []
    tool_results = state.get("tool_results", []) or []

    memory_section = ""
    if memories:
        mem_lines = [f"- ({m['type']}) {m['content']}" for m in memories]
        memory_section = "WHAT YOU REMEMBER ABOUT THIS USER:\n" + "\n".join(mem_lines) + "\n\n"

    tool_section = ""
    if tool_results:
        tool_lines = []
        for tr in tool_results:
            status = "OK" if tr.get("success") else "ERROR"
            output_str = json.dumps(tr.get("output"), default=str)[:1500]
            tool_lines.append(f"- {tr.get('name')} [{status}]: {output_str}")
        tool_section = "TOOL RESULTS:\n" + "\n".join(tool_lines) + "\n\n"

    if rag_context:
        system_text = (
            f"You are a helpful assistant. Respond in {lang}. Be concise and accurate.\n\n"
            f"{memory_section}{tool_section}"
            "You have retrieved passages tagged [N]. Cite inline like [1] or [2] when using them. "
            "Don't fabricate. If passages don't have the answer, say so.\n\n"
            "RETRIEVED CONTEXT:\n"
            f"{rag_context}"
        )
    else:
        system_text = (
            f"You are a helpful assistant. Respond in {lang}. Be concise and accurate.\n\n"
            f"{memory_section}{tool_section}"
        )

    system = SystemMessage(content=system_text)
    messages = [system] + state["messages"]
    response = await llm_gateway.invoke(messages, tier="main")

    answer = str(response.content)
    if rag_sources:
        answer = f"{answer}\n\n{rag_sources}"

    return {
        "final_answer": answer,
        "messages": [AIMessage(content=answer)],
    }


# --- save_memory ---

async def save_memory(state: AgentState) -> dict:
    user_msg = _latest_user_message(state)
    assistant_msg = state.get("final_answer", "")
    if not user_msg or not assistant_msg:
        return {}

    extracted = await extract_memories(user_msg, assistant_msg)
    if not extracted:
        return {}

    async with AsyncSessionLocal() as db:
        for mem in extracted:
            try:
                await memory_store.add(
                    db=db,
                    tenant_id=state["tenant_id"],
                    user_id=state["user_id"],
                    memory=mem,
                )
            except Exception as e:
                logger.warning("save_memory_failed_one", error=str(e))
        await db.commit()
    return {}


def _latest_user_message(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""
