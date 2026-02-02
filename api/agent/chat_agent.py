from typing import List, Dict, Any, AsyncGenerator
from openai import AsyncOpenAI

from .utils.provider_clients import get_gemini_client
from .utils import generate_stream_with_fallback, get_logger
from . import memory_agent
from .app_guide import APP_GUIDE

logger = get_logger(__name__)

async def run_chat_agent(
    history: List[Dict[str, str]], 
    patient_name: str, 
    current_summary: str,
    client: AsyncOpenAI
) -> AsyncGenerator[str, None]:
    """
    Interactive Clinical Co-pilot.
    Allows the doctor to ask questions about the current summary or past history.
    """
    
    # Configure Gemini Client if key is available (cached)
    chat_client = get_gemini_client() or client
    
    # 1. Retrieve relevant memory based on the user's last message
    last_user_msg = history[-1]["content"] if history else ""

    memory_context = ""
    
    if patient_name and last_user_msg:
        try:
            # Memory Agent still uses the default client (OpenAI embeddings)
            memory_context = await memory_agent.recall_patient_history(
                patient_name=patient_name,
                query=last_user_msg,
                client=client 
            )
        except Exception as e:
            logger.warning(f"Chat memory recall failed: {e}")

    # 2. Build System Prompt
    system_prompt = f"""You are MediNotes Pro, a clinical co-pilot and MediNotes application support assistant.

        ALL RESPONSES MUST BE IN MARKDOWN FORMAT.
        This rule overrides all others.

        Your scope is STRICTLY LIMITED to:
        A) Patient-specific clinical questions grounded in the provided context
        B) MediNotes application usage and features

        You must NOT answer general knowledge, math, geography, philosophy, or any topic outside this scope.

        ====================
        SCOPE & PRIORITY
        ====================
        1) First classify the user message as exactly one:
        - patient_specific_clinical
        - medinotes_app_usage_or_features
        - out_of_scope

        2) Patient-Specific Clinical Questions
        - You may answer ONLY using:
            • Current Consultation Summary
            • Relevant Patient History
        - If the requested clinical information is NOT explicitly present, respond EXACTLY (in Markdown):
            **Based on the available records, I do not have that information.**

        3) MediNotes App Usage / Features
        - You may answer questions about how the app works, supported features, workflows, and limitations.
        - Do NOT infer features that are not explicitly part of the app.

        4) Out-of-Scope Requests
        - For ANY request that is:
            • Not patient-specific clinical care
            • AND not related to MediNotes app usage or features
        - Respond EXACTLY (in Markdown):
            **I am limited to patient-specific clinical questions and MediNotes app features.**

====================
STRICT OUTPUT RULES
====================
- Output MUST be valid Markdown.
- Do NOT return plain text.
- Do NOT wrap the entire response in a code block.
- Default format:
  - Use bullet points for lists, steps, meds, timelines, and recommendations.
  - Keep paragraphs short (1-3 lines) with proper spacing between paragraphs.
- If the user asks to summarize history/visit, format as:
  - `### Patient History Summary`
  - `- Patient`
  - `- Key timeline`
  - `- Current/last treatment`
  - `- Latest status`
- Refusal messages MUST still be Markdown.
- Do NOT add explanations to refusal messages.
- Do NOT fabricate or infer patient facts.
- Be direct and concise.

        App guide reference:
        {APP_GUIDE}
        """


    messages = [{"role": "system", "content": system_prompt}]
    
    # Context Injection
    if current_summary:
        messages.append({"role": "system", "content": f"Current Consultation Summary:\n{current_summary}"})
    if memory_context:
        messages.append({"role": "system", "content": f"Relevant Patient History:\n{memory_context}"})
        
    # Append conversation history
    # Filter only user/assistant roles to avoid confusion
    for msg in history:
        if msg["role"] in ["user", "assistant"]:
            messages.append(msg)

    # 3. Stream Response
    try:
        response_stream = await generate_stream_with_fallback(
            client=chat_client,
            messages=messages,
            models=["gemini-2.5-flash", "gemini-2.5-flash-lite"]
        )
        
        chunk_count = 0
        async for chunk in response_stream:
            content = chunk.choices[0].delta.content
            if content:
                lines = content.split("\n")
                for line in lines:
                    yield f"data: {line}\n"
                yield "\n"
            chunk_count += 1
        
        logger.info(f"Chat stream finished. Received {chunk_count} chunks.")

    except Exception as e:
        logger.error(f"Chat generation failed: {e}")
        yield "data: I apologize, but I encountered an error processing your request.\n\n"
