"""
Bug Detection Engine — 12 categories, 35 specific bug patterns.
Reads a parsed run dict and returns a structured bug report.
"""
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.services.run_loader import get_all_test_cases


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_run(run: dict, prev_runs: List[dict] = None) -> dict:
    bugs = []
    for tc in get_all_test_cases(run):
        bugs.extend(_check_data_quality(tc))
        bugs.extend(_check_config(tc))
        bugs.extend(_check_consistency(tc))
        trace = tc.get("trace")
        if trace:
            bugs.extend(_check_chunking(tc, trace))
            bugs.extend(_check_retrieval(tc, trace))
            bugs.extend(_check_llm(tc, trace))
            bugs.extend(_check_prompt(tc, trace))
            bugs.extend(_check_tools(tc, trace))
            bugs.extend(_check_agent(tc, trace))
            bugs.extend(_check_latency(tc, trace))
            bugs.extend(_check_cost(tc, trace))
    if prev_runs:
        bugs.extend(_check_regressions(run, prev_runs))

    for b in bugs:
        b.setdefault("bugId", str(uuid.uuid4())[:8].upper())

    return {
        "runFile":  run.get("_filename", ""),
        "total":    len(bugs),
        "critical": sum(1 for b in bugs if b["severity"] == "critical"),
        "warning":  sum(1 for b in bugs if b["severity"] == "warning"),
        "info":     sum(1 for b in bugs if b["severity"] == "info"),
        "bugs":     bugs,
    }


def _bug(code, btype, severity, tc_name, span_type, span_name, title, evidence, why, fix) -> dict:
    return {
        "bugId":     code,
        "type":      btype,
        "severity":  severity,
        "testCase":  tc_name,
        "spanType":  span_type,
        "spanName":  span_name,
        "title":     title,
        "evidence":  evidence,
        "why":       why,
        "fix":       fix,
        "resolved":  False,
    }


def _get_metric_score(tc: dict, name: str) -> Optional[float]:
    for m in (tc.get("metricsData") or []):
        if m.get("name", "").lower() == name.lower():
            return m.get("score")
    return None


def _get_metric(tc: dict, name: str) -> Optional[dict]:
    for m in (tc.get("metricsData") or []):
        if m.get("name", "").lower() == name.lower():
            return m
    return None


def _spans_by_type(trace: dict, span_type: str) -> list:
    key_map = {
        "llm":       "llmSpans",
        "retriever": "retrieverSpans",
        "tool":      "toolSpans",
        "agent":     "agentSpans",
        "base":      "baseSpans",
    }
    return trace.get(key_map.get(span_type, "baseSpans")) or []


def _all_spans(trace: dict) -> list:
    spans = []
    for k in ("baseSpans", "agentSpans", "llmSpans", "retrieverSpans", "toolSpans"):
        spans.extend(trace.get(k) or [])
    return spans


def _span_dur_ms(span: dict) -> Optional[float]:
    from datetime import datetime
    s, e = span.get("startTime"), span.get("endTime")
    if not s or not e:
        return None
    try:
        return round((datetime.fromisoformat(e.replace("Z", "+00:00")) -
                      datetime.fromisoformat(s.replace("Z", "+00:00"))).total_seconds() * 1000, 2)
    except Exception:
        return None


# ─── BUG TYPE 1: CHUNKING ────────────────────────────────────────────────────

def _check_chunking(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    context_recall = _get_metric_score(tc, "contextual recall")

    for span in _spans_by_type(trace, "retriever"):
        sname = span.get("name", "retriever")
        chunk_size = span.get("chunkSize")
        chunks = span.get("retrievalContext") or tc.get("retrievalContext") or []
        avg_chars = round(sum(len(c) for c in chunks) / len(chunks), 1) if chunks else 0

        if chunk_size and chunk_size < 200 and context_recall is not None and context_recall < 0.5:
            bugs.append(_bug("CHUNK-001", "CHUNKING", "critical", name, "retriever", sname,
                "Chunk size too small — key information split across boundaries",
                {"chunkSize": chunk_size, "avgChunkChars": avg_chars, "contextRecall": context_recall,
                 "retrievedChunks": len(chunks)},
                f"Context Recall is {context_recall:.2f} (below 0.5). Chunks are only {chunk_size} chars, "
                "likely splitting sentences. Key facts fall between chunk boundaries.",
                "Increase chunk_size to 512-1024. Add sentence-aware splitter. Add 10-15% overlap."))

        if chunk_size and chunk_size > 3000:
            answer_rel = _get_metric_score(tc, "answer relevancy")
            if answer_rel is not None and answer_rel < 0.6:
                bugs.append(_bug("CHUNK-002", "CHUNKING", "warning", name, "retriever", sname,
                    "Chunk size too large — irrelevant text diluting retrieval precision",
                    {"chunkSize": chunk_size, "answerRelevancy": answer_rel},
                    f"Large chunks ({chunk_size} chars) include irrelevant text, diluting retrieval precision.",
                    "Reduce chunk_size to 512-1024 chars."))

        if chunks and len(chunks) > 0:
            last_chars = [c[-1] if c else "" for c in chunks]
            mid_sentence = sum(1 for ch in last_chars if ch not in ".!?\"'")
            if mid_sentence / len(last_chars) > 0.6:
                bugs.append(_bug("CHUNK-004", "CHUNKING", "warning", name, "retriever", sname,
                    "Chunks ending mid-sentence — wrong splitter strategy",
                    {"midSentenceChunks": mid_sentence, "totalChunks": len(last_chars)},
                    "Character-based splitter ignoring sentence boundaries. Chunks cut off mid-sentence.",
                    "Use RecursiveCharacterTextSplitter with separators=['\\n\\n','\\n','. ',' ']. "
                    "Or use a sentence-aware splitter."))

    return bugs


# ─── BUG TYPE 2: RETRIEVAL ───────────────────────────────────────────────────

def _check_retrieval(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    context_recall    = _get_metric_score(tc, "contextual recall")
    context_precision = _get_metric_score(tc, "contextual precision")

    for span in _spans_by_type(trace, "retriever"):
        sname = span.get("name", "retriever")
        top_k   = span.get("topK")
        embedder = span.get("embedder")
        chunks  = span.get("retrievalContext") or tc.get("retrievalContext") or []

        if not chunks:
            bugs.append(_bug("RETRIEVAL-005", "RETRIEVAL", "critical", name, "retriever", sname,
                "Empty retrieval context — vector DB returned no results",
                {"retrievalContext": [], "topK": top_k, "embedder": embedder},
                "Vector DB returned no results. Query may be out of distribution or DB unreachable.",
                "Check vector DB connectivity. Verify embedder model matches index. Add fallback retrieval."))
            continue

        if top_k is not None and top_k <= 2 and context_recall is not None and context_recall < 0.5:
            bugs.append(_bug("RETRIEVAL-001", "RETRIEVAL", "warning", name, "retriever", sname,
                "Too few chunks retrieved (low top_k) — key facts never retrieved",
                {"topK": top_k, "contextRecall": context_recall},
                f"Only {top_k} chunks retrieved. Not enough coverage to find all relevant facts.",
                "Increase top_k to 5-10. Consider adding a reranker to improve precision at higher k."))

        if top_k is not None and top_k >= 20 and context_precision is not None and context_precision < 0.4:
            bugs.append(_bug("RETRIEVAL-002", "RETRIEVAL", "warning", name, "retriever", sname,
                "Too many chunks retrieved (noisy context) — precision degraded",
                {"topK": top_k, "contextPrecision": context_precision},
                f"Retrieving {top_k} chunks adds irrelevant noise, confusing the LLM.",
                "Reduce top_k to 5-8. Add a reranker (cross-encoder) to filter irrelevant chunks."))

        if not embedder:
            bugs.append(_bug("RETRIEVAL-003", "RETRIEVAL", "warning", name, "retriever", sname,
                "Missing embedder — cannot verify embedding model consistency",
                {"embedder": None},
                "Embedder model not recorded. Cannot verify same model used for indexing and querying.",
                "Set embedder field in @observe(type='retriever', embedder='text-embedding-3-small'). "
                "Ensure same model used at index time."))

        if context_precision is not None and context_precision < 0.3:
            bugs.append(_bug("RETRIEVAL-004", "RETRIEVAL", "warning", name, "retriever", sname,
                "Low retrieval relevance — chunks unrelated to query",
                {"contextPrecision": context_precision, "retrievedChunks": len(chunks)},
                "Retrieved chunks are mostly irrelevant to the query. Embedder may not capture domain semantics.",
                "Consider domain-specific embedding model. Add keyword search hybrid. Fine-tune embedder."))

    return bugs


# ─── BUG TYPE 3: LLM ─────────────────────────────────────────────────────────

KNOWN_CONTEXT_LIMITS = {
    "gpt-4o": 128000, "gpt-4": 8192, "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385, "claude-3-opus": 200000,
    "claude-3-sonnet": 200000, "claude-3-haiku": 200000,
    "claude-sonnet-4-6": 200000, "gemini-pro": 32000,
}

def _check_llm(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    faithfulness = _get_metric_score(tc, "faithfulness")

    for span in _spans_by_type(trace, "llm"):
        sname = span.get("name", "llm")
        model = span.get("model", "")
        inp_tokens = span.get("inputTokenCount") or 0
        out_tokens = span.get("outputTokenCount") or 0

        if faithfulness is not None and faithfulness < 0.5:
            bugs.append(_bug("LLM-001", "LLM_GENERATION", "critical", name, "llm", sname,
                "Hallucination — model fabricating facts not in context",
                {"faithfulness": faithfulness, "model": model},
                f"Faithfulness score {faithfulness:.2f} indicates model generated facts absent from retrieval context.",
                "Add system instruction: 'Answer ONLY based on provided context. Say I don't know if unsure.' "
                "Lower temperature to 0.0. Add faithfulness check in production."))

        if model:
            limit = KNOWN_CONTEXT_LIMITS.get(model.lower().split("/")[-1], 0)
            if limit and inp_tokens > limit * 0.8:
                bugs.append(_bug("LLM-002", "LLM_GENERATION", "warning", name, "llm", sname,
                    f"Context window near limit — {inp_tokens}/{limit} tokens used ({int(inp_tokens/limit*100)}%)",
                    {"model": model, "inputTokens": inp_tokens, "contextLimit": limit, "usagePct": round(inp_tokens/limit, 2)},
                    "Prompt + context is using over 80% of the model's context window. Information may be truncated.",
                    "Reduce chunk count (lower top_k). Compress system prompt. Use a model with larger context window."))

        if out_tokens and out_tokens < 15:
            bugs.append(_bug("LLM-004", "LLM_GENERATION", "warning", name, "llm", sname,
                "Output too short — likely incomplete answer",
                {"outputTokens": out_tokens},
                f"Model generated only {out_tokens} output tokens. max_tokens may be too low or model refused.",
                "Increase max_tokens. Check if model hit stop sequences prematurely. Review system prompt."))

        dur = _span_dur_ms(span)
        if dur and dur > 15000:
            bugs.append(_bug("LLM-006", "LLM_GENERATION", "info", name, "llm", sname,
                f"High LLM latency — {dur:.0f}ms exceeds 15s",
                {"durationMs": dur, "model": model, "inputTokens": inp_tokens},
                "LLM call took over 15 seconds. Could be model overloaded, very large prompt, or slow TTFT.",
                "Enable streaming. Reduce prompt size. Consider a faster model for latency-sensitive paths."))

    # Model ignoring context
    if faithfulness is not None and faithfulness < 0.4:
        context = tc.get("retrievalContext") or []
        if context:
            for span in _spans_by_type(trace, "llm"):
                inp = str(span.get("input") or "")
                if "context" not in inp.lower() and "provided" not in inp.lower():
                    bugs.append(_bug("LLM-003", "LLM_GENERATION", "critical",
                        name, "llm", span.get("name", "llm"),
                        "Model ignoring retrieval context — prompt has no grounding instruction",
                        {"faithfulness": faithfulness, "hasContextInPrompt": False},
                        "Retrieval context was provided but prompt doesn't instruct model to use it. "
                        "Model defaults to parametric knowledge.",
                        "Add to system prompt: 'Use ONLY the following context to answer. "
                        "Do not use prior knowledge.'"))
    return bugs


# ─── BUG TYPE 4: PROMPT ──────────────────────────────────────────────────────

def _check_prompt(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    answer_rel = _get_metric_score(tc, "answer relevancy")
    faithfulness = _get_metric_score(tc, "faithfulness")
    expected = tc.get("expectedOutput") or ""

    if answer_rel is not None and answer_rel < 0.5:
        bugs.append(_bug("PROMPT-001", "PROMPT", "warning", name, "llm", "",
            "Low answer relevancy — prompt instructions too vague",
            {"answerRelevancy": answer_rel},
            f"Answer Relevancy {answer_rel:.2f} indicates model answering off-topic.",
            "Add specific task description to system prompt. Specify expected format and scope."))

    for span in _spans_by_type(trace, "llm"):
        inp = str(span.get("input") or "")
        inp_tokens = span.get("inputTokenCount") or 0

        if faithfulness is not None and faithfulness < 0.5:
            grounding_phrases = ["only", "based on", "provided context", "given context", "do not use"]
            has_grounding = any(p in inp.lower() for p in grounding_phrases)
            if not has_grounding:
                bugs.append(_bug("PROMPT-002", "PROMPT", "critical", name, "llm", span.get("name", "llm"),
                    "Missing grounding instruction in prompt — hallucination risk",
                    {"faithfulness": faithfulness, "hasGroundingInstruction": False},
                    "Prompt does not restrict model to provided context, allowing hallucination.",
                    "Add to system prompt: 'Answer ONLY based on the context below. "
                    "If the answer is not in the context, say: I don't know.'"))

        if expected and isinstance(expected, str):
            expected_is_json = expected.strip().startswith("{") or expected.strip().startswith("[")
            actual = str(tc.get("actualOutput") or "")
            actual_is_json = actual.strip().startswith("{") or actual.strip().startswith("[")
            if expected_is_json and not actual_is_json:
                bugs.append(_bug("PROMPT-003", "PROMPT", "warning", name, "llm", span.get("name", "llm"),
                    "Missing output format instruction — expected JSON but got plain text",
                    {"expectedFormat": "JSON", "actualFormat": "text"},
                    "Expected output is structured (JSON/list) but actual output is plain text.",
                    "Add format instruction to prompt: 'Respond ONLY with valid JSON. "
                    "Do not include any other text.'"))
            break  # check once per test case

        if inp_tokens > 2000 and "system" in inp.lower():
            sys_content_len = len([l for l in inp.split("\\n") if "system" in l.lower()])
            if sys_content_len > 20:
                bugs.append(_bug("PROMPT-004", "PROMPT", "info", name, "llm", span.get("name", "llm"),
                    f"System prompt is very large — {inp_tokens} input tokens",
                    {"inputTokens": inp_tokens, "estimatedSystemLines": sys_content_len},
                    "Large system prompt leaves little space for context and question.",
                    "Compress system prompt. Move static rules to a prefix cache. "
                    "Target system prompt under 500 tokens."))
            break

    return bugs


# ─── BUG TYPE 5: TOOLS ───────────────────────────────────────────────────────

def _check_tools(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    tools_called   = tc.get("toolsCalled") or []
    expected_tools = tc.get("expectedTools") or []

    for span in _spans_by_type(trace, "tool"):
        sname = span.get("name", "tool")
        if (span.get("status") or "").upper() == "ERRORED":
            bugs.append(_bug("TOOL-001", "TOOL", "critical", name, "tool", sname,
                f"Tool call failed with exception: {sname}",
                {"status": "ERRORED", "error": span.get("error"), "input": span.get("input")},
                f"Tool '{sname}' threw an exception. Could be bad arguments, API failure, or timeout.",
                "Add try/except in tool function. Validate tool inputs. Add retry with exponential backoff."))

        span_args = span.get("input")
        if span_args and span.get("description"):
            pass  # arg validation would need schema — leave as info

    if expected_tools and not tools_called:
        expected_names = [t.get("name") if isinstance(t, dict) else str(t) for t in expected_tools]
        bugs.append(_bug("TOOL-005", "TOOL", "warning", name, "tool", "",
            "Missing tool call — expected tools were not used",
            {"expectedTools": expected_names, "toolsCalled": []},
            "Agent did not call any tools, but test expects specific tool use.",
            "Add tool descriptions to agent system prompt. Add few-shot examples of tool use. "
            "Check tool availability in agent config."))

    if tools_called and not expected_tools:
        called_names = [t.get("name") if isinstance(t, dict) else str(t) for t in tools_called]
        bugs.append(_bug("TOOL-004", "TOOL", "info", name, "tool", "",
            "Unnecessary tool call — tools used when not expected",
            {"toolsCalled": called_names, "expectedTools": []},
            "Agent called tools for a query that should be answerable without external data.",
            "Add guard condition: 'Call tools only when question requires external/real-time data.' "
            "Improve agent's tool-vs-no-tool decision logic."))

    if tools_called and expected_tools:
        called_names   = {t.get("name") if isinstance(t, dict) else str(t) for t in tools_called}
        expected_names = {t.get("name") if isinstance(t, dict) else str(t) for t in expected_tools}
        if called_names != expected_names:
            bugs.append(_bug("TOOL-002", "TOOL", "warning", name, "tool", "",
                "Wrong tool called — actual ≠ expected",
                {"called": list(called_names), "expected": list(expected_names)},
                f"Agent called {called_names} but expected {expected_names}.",
                "Improve tool descriptions and selection prompt. Add tool routing examples to system prompt."))

    return bugs


# ─── BUG TYPE 6: AGENT ───────────────────────────────────────────────────────

def _check_agent(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")

    agent_spans = _spans_by_type(trace, "agent")
    if not agent_spans:
        return bugs

    # Detect loops: same agent span name appearing > 3 times
    name_counts = defaultdict(int)
    for span in agent_spans:
        name_counts[span.get("name", "")] += 1
    for aname, count in name_counts.items():
        if count > 3:
            bugs.append(_bug("AGENT-001", "AGENT", "critical", name, "agent", aname,
                f"Agent loop detected — '{aname}' called {count} times",
                {"agentName": aname, "callCount": count},
                "Agents are handing off to each other in a circle. No termination condition.",
                "Add max_iterations guard. Add explicit termination condition. "
                "Track visited agents to prevent circular handoffs."))

    for span in agent_spans:
        sname = span.get("name", "agent")
        handoffs = span.get("agentHandoffs") or []
        avail    = span.get("availableTools") or []

        if len(handoffs) > 5:
            bugs.append(_bug("AGENT-004", "AGENT", "warning", name, "agent", sname,
                f"Excessive sub-agent calls — {len(handoffs)} handoffs in single trace",
                {"agentHandoffs": handoffs, "count": len(handoffs)},
                f"Agent made {len(handoffs)} handoffs, over-decomposing a simple task.",
                "Consolidate agent responsibilities. Use single agent for simple queries. "
                "Add complexity threshold before routing to sub-agents."))

        if avail and not _spans_by_type(trace, "tool"):
            bugs.append(_bug("AGENT-003", "AGENT", "info", name, "agent", sname,
                "Agent not using available tools despite having them configured",
                {"availableTools": avail, "toolSpansCount": 0},
                "Agent has tools configured but made no tool calls.",
                "Include tool descriptions explicitly in agent system prompt. "
                "Add few-shot tool-use examples to the agent prompt."))

    return bugs


# ─── BUG TYPE 7: REGRESSION ──────────────────────────────────────────────────

def _check_regressions(run: dict, prev_runs: List[dict]) -> list:
    from backend.services.run_loader import get_all_test_cases
    bugs = []
    hist_pass:   Dict[str, list] = defaultdict(list)
    hist_scores: Dict[tuple, list] = defaultdict(list)

    for prev in prev_runs[:3]:
        for tc in get_all_test_cases(prev):
            n = tc.get("name", "")
            hist_pass[n].append(tc.get("success"))
            for m in (tc.get("metricsData") or []):
                if m.get("score") is not None:
                    hist_scores[(n, m["name"])].append(m["score"])

    for tc in get_all_test_cases(run):
        n = tc.get("name", "")
        prev_p = hist_pass.get(n, [])
        if prev_p and all(p is True for p in prev_p) and tc.get("success") is False:
            bugs.append(_bug("REGRESSION-002", "REGRESSION", "critical", n, "", "",
                "Test case flipped from PASS to FAIL",
                {"prevRuns": len(prev_p), "prevAllPass": True, "currentSuccess": False},
                f"Test case '{n}' passed in all {len(prev_p)} previous runs but now fails. "
                "Likely caused by a code/prompt/model change.",
                "Re-run 3 times to rule out non-determinism. If consistently failing, "
                "run git diff on prompt files and check model version."))

        for m in (tc.get("metricsData") or []):
            prev_s = hist_scores.get((n, m["name"]), [])
            if prev_s and m.get("score") is not None:
                avg = sum(prev_s) / len(prev_s)
                drop = avg - m["score"]
                if drop > 0.15:
                    bugs.append(_bug("REGRESSION-001", "REGRESSION", "warning", n, "", "",
                        f"Score dropped {drop:.2f} for metric '{m['name']}'",
                        {"metric": m["name"], "prevAvg": round(avg, 3), "current": round(m["score"], 3), "drop": round(drop, 3)},
                        f"'{m['name']}' dropped from avg {avg:.2f} to {m['score']:.2f} (Δ {drop:.2f}).",
                        "Check recent prompt changes, model version changes, or dataset changes. "
                        "Compare test case I/O in Compare Runs page."))
    return bugs


# ─── BUG TYPE 8: LATENCY ─────────────────────────────────────────────────────

LATENCY_THRESHOLDS = {"llm": 8000, "retriever": 3000, "tool": 5000, "agent": 15000, "base": 5000}

def _check_latency(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    for span in _all_spans(trace):
        dur = _span_dur_ms(span)
        if dur is None:
            continue
        stype   = span.get("type", "base")
        sname   = span.get("name", stype)
        thresh  = LATENCY_THRESHOLDS.get(stype, 5000)
        if dur > thresh * 2:
            bugs.append(_bug("LATENCY-001", "LATENCY", "warning", name, stype, sname,
                f"Span too slow — {dur:.0f}ms (threshold {thresh}ms for {stype})",
                {"durationMs": dur, "threshold": thresh, "spanType": stype},
                f"'{sname}' took {dur:.0f}ms, over 2x the expected {thresh}ms for a {stype} span.",
                f"Add timeout handling. Consider caching results. "
                f"{'Use faster model or enable streaming.' if stype == 'llm' else 'Optimize DB query or add index.'}"))

    all_spans = _all_spans(trace)
    retriever_spans = [s for s in all_spans if s.get("type") == "retriever"]
    for rspan in retriever_spans:
        dur = _span_dur_ms(rspan)
        if dur and dur > 3000:
            bugs.append(_bug("LATENCY-003", "LATENCY", "warning", name, "retriever", rspan.get("name", "retriever"),
                f"Slow retrieval — {dur:.0f}ms",
                {"durationMs": dur},
                "Vector DB retrieval is taking over 3 seconds. Could be cold start, missing index, or large corpus.",
                "Add vector DB warm-up. Verify index is built. Add retrieval result cache for repeated queries."))
    return bugs


# ─── BUG TYPE 9: COST ────────────────────────────────────────────────────────

def _check_cost(tc: dict, trace: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    for span in _spans_by_type(trace, "llm"):
        cpi = span.get("costPerInputToken") or 0.0
        cpo = span.get("costPerOutputToken") or 0.0
        inp = span.get("inputTokenCount") or 0
        out = span.get("outputTokenCount") or 0
        cost = cpi * inp + cpo * out

        if cost > 0.10:
            bugs.append(_bug("COST-002", "COST", "warning", name, "llm", span.get("name", "llm"),
                f"Single LLM call is expensive — ${cost:.4f}",
                {"cost": round(cost, 6), "inputTokens": inp, "outputTokens": out,
                 "model": span.get("model")},
                f"One LLM call costs ${cost:.4f}. Likely due to large prompt or expensive model.",
                "Reduce prompt size. Use cheaper model for this task. Enable prompt caching."))

        if inp and out and inp > out * 5 and inp > 2000:
            bugs.append(_bug("COST-003", "COST", "info", name, "llm", span.get("name", "llm"),
                f"Token waste — input ({inp}) >> output ({out}) ratio",
                {"inputTokens": inp, "outputTokens": out, "ratio": round(inp/out, 1) if out else "∞"},
                f"Sending {inp} input tokens to get {out} output tokens is inefficient.",
                "Compress system prompt. Use RAG to reduce context size. Enable prefix caching."))
    return bugs


# ─── BUG TYPE 10: CONSISTENCY ────────────────────────────────────────────────

def _check_consistency(tc: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    metrics_data = tc.get("metricsData") or []

    scores = {m["name"].lower(): m.get("score") for m in metrics_data if m.get("score") is not None}
    errors = [m for m in metrics_data if m.get("error")]

    f   = scores.get("faithfulness")
    cr  = scores.get("contextual recall")
    ar  = scores.get("answer relevancy")

    if f is not None and cr is not None and f > 0.8 and cr < 0.3:
        bugs.append(_bug("CONSISTENCY-001", "CONSISTENCY", "warning", name, "", "",
            "Faithfulness high but Context Recall low — unusual combination",
            {"faithfulness": f, "contextualRecall": cr},
            "High faithfulness with very low context recall is unusual. "
            "May indicate evaluator misconfiguration or test case data issue.",
            "Verify retrieval context is properly set. Check metric configurations. "
            "Ensure expected_output and retrieval_context are populated."))

    if ar is not None and f is not None and ar > 0.8 and f < 0.3:
        bugs.append(_bug("CONSISTENCY-002", "CONSISTENCY", "critical", name, "", "",
            "Relevant but hallucinated answer — dangerous production pattern",
            {"answerRelevancy": ar, "faithfulness": f},
            f"Model is giving relevant (relevancy={ar:.2f}) but hallucinated (faithfulness={f:.2f}) answers. "
            "Appears helpful but fabricates facts.",
            "Prioritize faithfulness fix. Add strict grounding instruction to prompt. "
            "This is a high-risk pattern for production systems."))

    if errors and len(errors) == len(metrics_data) and metrics_data:
        bug_detail = errors[0].get("error", "") if errors else ""
        bugs.append(_bug("CONSISTENCY-003", "CONSISTENCY", "critical", name, "", "",
            "All metrics errored — evaluator completely failed",
            {"errorCount": len(errors), "firstError": bug_detail[:200]},
            "Every metric threw an error. Evaluator LLM API may have failed or metric config is broken.",
            "Check evaluator API key and network. Verify metric imports. "
            "Try running evaluate() manually to see the full error trace."))

    return bugs


# ─── BUG TYPE 11: DATA QUALITY ───────────────────────────────────────────────

def _check_data_quality(tc: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    inp  = tc.get("input", "")

    if not inp or not inp.strip():
        bugs.append(_bug("DATA-001", "DATA_QUALITY", "critical", name, "", "",
            "Empty input — test case has no input text",
            {"input": inp},
            "Empty input produces meaningless evaluation results. Test data generation bug.",
            "Add input validation in test setup. Filter empty test cases before evaluate()."))

    for m in (tc.get("metricsData") or []):
        needs_expected = m.get("name", "").lower() in (
            "faithfulness", "hallucination", "correctness", "exact match"
        )
        if needs_expected and not tc.get("expectedOutput"):
            bugs.append(_bug("DATA-002", "DATA_QUALITY", "warning", name, "", "",
                f"Missing expected_output for metric '{m['name']}'",
                {"metric": m["name"], "expectedOutput": None},
                f"Metric '{m['name']}' requires expected_output to compute correctly.",
                "Add expected_output to all test cases used with faithfulness/correctness metrics."))
            break

    return bugs


# ─── BUG TYPE 12: CONFIGURATION ──────────────────────────────────────────────

def _check_config(tc: dict) -> list:
    bugs = []
    name = tc.get("name", "")
    metrics_data = tc.get("metricsData") or []

    if not metrics_data:
        bugs.append(_bug("CONFIG-003", "CONFIG", "warning", name, "", "",
            "No metrics configured for this test case",
            {"metricsCount": 0},
            "No metrics were evaluated. Test case runs but produces no quality signal.",
            "Attach at least FaithfulnessMetric + AnswerRelevancyMetric to every test case."))
        return bugs

    for m in metrics_data:
        threshold = m.get("threshold", 0.5)
        eval_model = m.get("evaluationModel", "")

        if threshold < 0.3:
            bugs.append(_bug("CONFIG-001", "CONFIG", "info", name, "", "",
                f"Metric threshold too lenient — {m['name']} threshold is {threshold}",
                {"metric": m["name"], "threshold": threshold},
                f"Threshold {threshold} is very low. Test passes even with poor quality output.",
                "Recommended thresholds: faithfulness ≥ 0.7, answer_relevancy ≥ 0.7, "
                "contextual_recall ≥ 0.5."))

        if threshold > 0.99:
            bugs.append(_bug("CONFIG-002", "CONFIG", "info", name, "", "",
                f"Metric threshold too strict — {m['name']} threshold is {threshold}",
                {"metric": m["name"], "threshold": threshold},
                "Threshold near 1.0 is practically impossible to achieve for LLM metrics.",
                "Use practical thresholds based on baseline measurements (typically 0.6-0.85)."))

    return bugs
