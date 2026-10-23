import logging
from typing import Literal, List, Any
from langchain_openai import ChatOpenAI
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from shopify_agent.settings import settings

logger = logging.getLogger("LLM-FACTORY")


def get_llm(purpose: Literal["agent", "judge"], temperature: float = 0.01, tools: List[Any] = None) -> Any:
    """
    Retorna la instancia de LLM configurada según settings.llm_provider.
    Asegura desacoplamiento de proveedores y facilidad de intercambio de inferencia.

    Proveedores soportados:
    - "openrouter": OpenRouter (API compatible de OpenAI, proveedor por defecto).
    - "huggingface": API de Inferencia de Hugging Face (retrocompatibilidad).
    - "openai": ChatOpenAI oficial de OpenAI utilizando gpt-4o (judge) o gpt-4o-mini (agent).
    - "github": GitHub Models (API compatible de OpenAI, ideal para desarrollo sin costo).
    """
    provider = settings.llm_provider.lower().strip()
    logger.info(
        f"Instanciando LLM para '{purpose}' usando proveedor: '{provider}'")

    if provider == "openrouter":
        # OpenRouter expone una API compatible con OpenAI; permite intercambiar
        # modelos sin cambiar de SDK ni de lógica de herramientas.
        model_name = (
            settings.openrouter_judge_model
            if purpose == "judge"
            else settings.openrouter_agent_model
        )
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=settings.open_router_api_key,
            base_url=settings.openrouter_base_url,
        )
        if tools and purpose == "agent":
            return llm.bind_tools(tools)
        return llm

    elif provider == "openai":
        # Usamos gpt-4o para tareas críticas de auditoría (judge) y gpt-4o-mini para el agente
        model_name = "gpt-4o" if purpose == "judge" else "gpt-4o-mini"
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=settings.openai_api_key
        )
        if tools and purpose == "agent":
            return llm.bind_tools(tools)
        return llm

    elif provider == "github":
        # GitHub Models utiliza la API de OpenAI pero apuntando a Azure AI
        model_name = "gpt-4o" if purpose == "judge" else "gpt-4o-mini"
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=settings.github_token,
            base_url="https://models.inference.ai.azure.com"
        )
        if tools and purpose == "agent":
            return llm.bind_tools(tools)
        return llm

    else:
        # Fallback por defecto: Hugging Face (preserva comportamiento original)
        repo_id = "Qwen/Qwen2.5-72B-Instruct"
        llm_hf = HuggingFaceEndpoint(
            repo_id=repo_id,
            task="chat-completion",
            huggingfacehub_api_token=settings.huggingface_api_token,
            temperature=temperature,
        )
        llm = ChatHuggingFace(llm=llm_hf)
        if tools and purpose == "agent":
            return llm.bind_tools(tools)
        return llm
