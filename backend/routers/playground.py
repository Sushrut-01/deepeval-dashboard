"""
Playground: renders the prompt template and calls the configured LLM provider.
Supports OpenAI, Anthropic, Azure OpenAI, Ollama (local), and any OpenAI-compatible endpoint.
Provider is auto-detected from deepeval's settings.
"""
import logging
import re
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/playground", tags=["playground"])


class PlaygroundRunIn(BaseModel):
    prompt:      str
    input:       str
    model:       Optional[str] = None
    temperature: float = 0.0
    max_tokens:  int   = 1500
    system:      Optional[str] = None


class PlaygroundRunOut(BaseModel):
    output:        str
    model:         str
    provider:      str
    input_tokens:  Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms:    int
    error:         Optional[str] = None


def _render_prompt(template: str, user_input: str) -> str:
    """Replace {{variable}} and {variable} placeholders with the input."""
    result = template
    # Replace {{question}}, {{input}}, {{query}} etc.
    result = re.sub(r"\{\{(question|input|query|user_input|text)\}\}", user_input, result, flags=re.IGNORECASE)
    # Replace {question} style too
    result = re.sub(r"\{(question|input|query|user_input|text)\}", user_input, result, flags=re.IGNORECASE)
    return result


def _detect_provider():
    """Read deepeval settings to find the active LLM provider."""
    try:
        from deepeval.config.settings import get_settings
        s = get_settings()
        return s
    except Exception:
        return None


@router.post("/run", response_model=PlaygroundRunOut)
def run_playground(body: PlaygroundRunIn):
    rendered = _render_prompt(body.prompt, body.input)
    start_ms = time.time()

    # Try each provider in priority order
    result = (_try_openai(body, rendered)
              or _try_anthropic(body, rendered)
              or _try_azure(body, rendered)
              or _try_ollama(body, rendered)
              or _try_local(body, rendered))

    if result is None:
        latency = int((time.time() - start_ms) * 1000)
        return PlaygroundRunOut(
            output="",
            model="none",
            provider="none",
            latency_ms=latency,
            error=(
                "No LLM provider configured.\n\n"
                "Configure one with:\n"
                "  deepeval set-openai --model gpt-4o-mini --prompt-api-key\n"
                "  deepeval set-anthropic --model claude-3-haiku-20240307 --prompt-api-key\n"
                "  deepeval set-ollama --model llama3\n\n"
                "Or set OPENAI_API_KEY / ANTHROPIC_API_KEY in .env"
            ),
        )

    result.latency_ms = int((time.time() - start_ms) * 1000)
    return result


def _try_openai(body: PlaygroundRunIn, rendered: str) -> Optional[PlaygroundRunOut]:
    import os
    api_key = None
    model   = body.model

    # 1. Try deepeval settings first
    try:
        from deepeval.config.settings import get_settings
        s = get_settings()
        if s.OPENAI_API_KEY:
            from pydantic import SecretStr
            v = s.OPENAI_API_KEY
            api_key = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        if not model and s.OPENAI_MODEL_NAME:
            model = s.OPENAI_MODEL_NAME
    except Exception:
        pass

    # 2. Fallback to env var
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return None

    model = model or "gpt-4o-mini"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        messages = []
        if body.system:
            messages.append({"role": "system", "content": body.system})
        messages.append({"role": "user", "content": rendered})

        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=body.temperature, max_tokens=body.max_tokens,
        )
        return PlaygroundRunOut(
            output        = resp.choices[0].message.content or "",
            model         = resp.model,
            provider      = "openai",
            input_tokens  = resp.usage.prompt_tokens if resp.usage else None,
            output_tokens = resp.usage.completion_tokens if resp.usage else None,
            latency_ms    = 0,
        )
    except Exception as e:
        logger.warning("playground openai error: %s", e)
        return PlaygroundRunOut(output="", model=model, provider="openai",
                                latency_ms=0, error=str(e))


def _try_anthropic(body: PlaygroundRunIn, rendered: str) -> Optional[PlaygroundRunOut]:
    import os
    api_key = None
    model   = body.model

    try:
        from deepeval.config.settings import get_settings
        from pydantic import SecretStr
        s = get_settings()
        if s.ANTHROPIC_API_KEY:
            v = s.ANTHROPIC_API_KEY
            api_key = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        if not model and s.ANTHROPIC_MODEL_NAME:
            model = s.ANTHROPIC_MODEL_NAME
    except Exception:
        pass

    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = model or "claude-3-haiku-20240307"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        kwargs = dict(
            model=model,
            max_tokens=body.max_tokens,
            messages=[{"role": "user", "content": rendered}],
        )
        if body.system:
            kwargs["system"] = body.system

        resp = client.messages.create(**kwargs)
        return PlaygroundRunOut(
            output        = resp.content[0].text if resp.content else "",
            model         = resp.model,
            provider      = "anthropic",
            input_tokens  = resp.usage.input_tokens if resp.usage else None,
            output_tokens = resp.usage.output_tokens if resp.usage else None,
            latency_ms    = 0,
        )
    except Exception as e:
        logger.warning("playground anthropic error: %s", e)
        return PlaygroundRunOut(output="", model=model, provider="anthropic",
                                latency_ms=0, error=str(e))


def _try_azure(body: PlaygroundRunIn, rendered: str) -> Optional[PlaygroundRunOut]:
    import os
    try:
        from deepeval.config.settings import get_settings
        from pydantic import SecretStr
        s = get_settings()
        endpoint = s.AZURE_OPENAI_ENDPOINT
        api_ver  = s.OPENAI_API_VERSION
        dep_name = s.AZURE_DEPLOYMENT_NAME
        api_key_obj = s.AZURE_OPENAI_API_KEY
        if not all([endpoint, api_ver, dep_name, api_key_obj]):
            return None
        api_key = api_key_obj.get_secret_value() if isinstance(api_key_obj, SecretStr) else str(api_key_obj)
        from openai import AzureOpenAI
        client = AzureOpenAI(api_key=api_key, azure_endpoint=str(endpoint), api_version=str(api_ver))
        messages = []
        if body.system:
            messages.append({"role": "system", "content": body.system})
        messages.append({"role": "user", "content": rendered})
        resp = client.chat.completions.create(
            model=str(dep_name), messages=messages,
            temperature=body.temperature, max_tokens=body.max_tokens,
        )
        return PlaygroundRunOut(
            output       = resp.choices[0].message.content or "",
            model        = str(dep_name),
            provider     = "azure",
            input_tokens = resp.usage.prompt_tokens if resp.usage else None,
            output_tokens= resp.usage.completion_tokens if resp.usage else None,
            latency_ms   = 0,
        )
    except Exception as e:
        if "AZURE" in str(e).upper() or "azure" in str(e).lower():
            logger.warning("playground azure error: %s", e)
        return None


def _try_ollama(body: PlaygroundRunIn, rendered: str) -> Optional[PlaygroundRunOut]:
    try:
        from deepeval.config.settings import get_settings
        s = get_settings()
        base_url = s.LOCAL_MODEL_BASE_URL or "http://localhost:11434"
        model    = body.model or s.OLLAMA_MODEL_NAME or s.LOCAL_MODEL_NAME
        if not model:
            return None
        if "11434" not in str(base_url) and "ollama" not in str(base_url).lower():
            return None  # not Ollama
    except Exception:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key  = "ollama",
            base_url = f"{str(base_url)}/v1",
        )
        messages = []
        if body.system:
            messages.append({"role": "system", "content": body.system})
        messages.append({"role": "user", "content": rendered})
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=body.temperature, max_tokens=body.max_tokens,
        )
        return PlaygroundRunOut(
            output    = resp.choices[0].message.content or "",
            model     = model,
            provider  = "ollama",
            latency_ms= 0,
        )
    except Exception as e:
        logger.warning("playground ollama error: %s", e)
        return None


def _try_local(body: PlaygroundRunIn, rendered: str) -> Optional[PlaygroundRunOut]:
    """Any OpenAI-compatible local endpoint (LM Studio, vLLM, etc.)."""
    try:
        from deepeval.config.settings import get_settings
        from pydantic import SecretStr
        s = get_settings()
        base_url = s.LOCAL_MODEL_BASE_URL
        model    = body.model or s.LOCAL_MODEL_NAME
        api_key_obj = s.LOCAL_MODEL_API_KEY
        if not base_url or not model:
            return None
        api_key = "none"
        if api_key_obj:
            api_key = api_key_obj.get_secret_value() if isinstance(api_key_obj, SecretStr) else str(api_key_obj)
    except Exception:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=f"{str(base_url)}/v1")
        messages = []
        if body.system:
            messages.append({"role": "system", "content": body.system})
        messages.append({"role": "user", "content": rendered})
        resp = client.chat.completions.create(
            model=model, messages=messages,
            temperature=body.temperature, max_tokens=body.max_tokens,
        )
        return PlaygroundRunOut(
            output    = resp.choices[0].message.content or "",
            model     = model,
            provider  = "local",
            latency_ms= 0,
        )
    except Exception as e:
        logger.warning("playground local error: %s", e)
        return None


@router.get("/providers")
def list_providers():
    """Tell the frontend which providers are currently configured."""
    import os
    providers = []
    try:
        from deepeval.config.settings import get_settings
        from pydantic import SecretStr
        s = get_settings()

        def _has(v):
            if not v: return False
            if isinstance(v, SecretStr): return bool(v.get_secret_value().strip())
            return bool(str(v).strip())

        if _has(s.OPENAI_API_KEY) or os.getenv("OPENAI_API_KEY"):
            providers.append({"id": "openai",    "name": "OpenAI",    "model": s.OPENAI_MODEL_NAME or "gpt-4o-mini"})
        if _has(s.ANTHROPIC_API_KEY) or os.getenv("ANTHROPIC_API_KEY"):
            providers.append({"id": "anthropic", "name": "Anthropic", "model": s.ANTHROPIC_MODEL_NAME or "claude-3-haiku"})
        if _has(s.AZURE_OPENAI_API_KEY) and s.AZURE_OPENAI_ENDPOINT:
            providers.append({"id": "azure",     "name": "Azure OpenAI", "model": s.AZURE_DEPLOYMENT_NAME or "gpt-4"})
        if s.LOCAL_MODEL_BASE_URL and s.OLLAMA_MODEL_NAME:
            providers.append({"id": "ollama",    "name": "Ollama",    "model": s.OLLAMA_MODEL_NAME})
        if s.LOCAL_MODEL_BASE_URL and s.LOCAL_MODEL_NAME:
            providers.append({"id": "local",     "name": "Local LLM", "model": s.LOCAL_MODEL_NAME})
    except Exception as e:
        logger.warning("playground /providers error: %s", e)
    return {"providers": providers, "configured": len(providers) > 0}


# ── Evaluate output with a deepeval metric ────────────────────────────────────

class PlaygroundEvalIn(BaseModel):
    input:             str
    output:            str
    metric:            str
    threshold:         float = 0.5
    context:           Optional[list] = None
    expected_output:   Optional[str]  = None


EVAL_METRIC_MAP = {
    "Faithfulness":          "deepeval.metrics.FaithfulnessMetric",
    "AnswerRelevancy":       "deepeval.metrics.AnswerRelevancyMetric",
    "ContextualRecall":      "deepeval.metrics.ContextualRecallMetric",
    "ContextualPrecision":   "deepeval.metrics.ContextualPrecisionMetric",
    "ContextualRelevancy":   "deepeval.metrics.ContextualRelevancyMetric",
    "Hallucination":         "deepeval.metrics.HallucinationMetric",
    "Bias":                  "deepeval.metrics.BiasMetric",
    "Toxicity":              "deepeval.metrics.ToxicityMetric",
    "Summarization":         "deepeval.metrics.SummarizationMetric",
    "JsonCorrectness":       "deepeval.metrics.JsonCorrectnessMetric",
    "PromptAlignment":       "deepeval.metrics.PromptAlignmentMetric",
    "TaskCompletion":        "deepeval.metrics.TaskCompletionMetric",
}

@router.post("/evaluate")
def evaluate_output(body: PlaygroundEvalIn):
    """Run a deepeval metric on the playground output."""
    import importlib
    dotted = EVAL_METRIC_MAP.get(body.metric)
    if not dotted:
        return {"error": f"Unknown metric '{body.metric}'. Available: {list(EVAL_METRIC_MAP.keys())}"}

    try:
        module_path, cls_name = dotted.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        MetricClass = getattr(mod, cls_name)
    except ImportError:
        return {
            "error": "deepeval not installed in dashboard environment.\n"
                     "Install it: pip install deepeval\n"
                     "(Run from the local-dashboard/ folder)"
        }
    except Exception as e:
        return {"error": f"Could not load metric: {e}"}

    try:
        from deepeval.test_case import LLMTestCase
        case = LLMTestCase(
            input           = body.input,
            actual_output   = body.output,
            expected_output = body.expected_output,
            retrieval_context = body.context or [],
        )
        metric = MetricClass(threshold=body.threshold)
        metric.measure(case)
        return {
            "metric":    body.metric,
            "score":     round(metric.score, 4) if metric.score is not None else None,
            "success":   metric.success,
            "reason":    metric.reason,
            "threshold": metric.threshold,
            "evalModel": getattr(metric, "model", None),
        }
    except Exception as e:
        return {"error": str(e)[:400]}


@router.get("/eval-metrics")
def list_eval_metrics():
    return list(EVAL_METRIC_MAP.keys())
