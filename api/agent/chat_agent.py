import os
from typing import List, Dict, Any, AsyncGenerator
from openai import AsyncOpenAI

from .utils.provider_clients import get_gemini_client
from .utils import generate_stream_with_fallback, get_logger
from . import memory_agent

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
    system_prompt = """You are MediNotes Pro, an expert Clinical Co-pilot and user support assistant.
        Your primary function is to provide **definitive answers** based *only* on the provided context.

        # RULES:
        1.  **BE DIRECT:** Answer the user's question concisely. Do not add conversational filler.
        2.  **USE ONLY PROVIDED CONTEXT:** Your knowledge is strictly limited to the 'Current Consultation Summary' and 'Relevant Patient History' provided. Do not use outside knowledge.
        3.  **DO NOT SUMMARIZE:** The user does not want a summary of the documents. They want a specific answer to their question.
        4.  **IF YOU DON'T KNOW, SAY SO:** If the answer is not in the provided context, you MUST respond with: 'Based on the available records, I do not have that information.'
        5.  **APP GUIDE (Secondary Role):** If the user asks about the app's features (e.g., 'how to upload'), you may answer from your general knowledge about the app.

        # OUTPUT (Markdown only)
        Return EXACTLY this Markdown template. No extra text.

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
