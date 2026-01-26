import os
from typing import List, Dict, Any, AsyncGenerator
from openai import AsyncOpenAI
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
    
    # Configure Gemini Client if key is available
    gemini_key = os.getenv("GEMINI_API_KEY")
    chat_client = client
    
    if gemini_key:
        chat_client = AsyncOpenAI(
            api_key=gemini_key,
            base_url=os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        )
    
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
    system_prompt = (
        "You are MediNotes Pro, an expert Clinical Co-pilot and user support assistant. "
        "You have two main roles:\n"
        "1. **Clinical Assistant:** Help the doctor with the current case. You have access to the consultation summary and patient history. "
        "Answer medical questions, draft referrals, or suggest next steps.\n"
        "2. **App Guide:** Help the user utilize this application. You know the following features:\n"
        "   - **Inputs:** Users can type notes, upload Audio (MP3/WAV) for transcription, or upload Images (PNG/JPG) of handwritten prescriptions.\n"
        "   - **Generation:** The 'Generate Summary' button creates a structured note (SOAP, Discharge, etc.) and extracts Action Items.\n"
        "   - **Memory:** The system automatically remembers past visits for the same patient name.\n"
        "   - **Email:** Users can send patient-ready emails via the 'Send Email' tab, with optional language translation.\n\n"
        "Refuse to answer non-medical or off-topic questions not related to clinical practice or this application. "
        "Be concise, professional, and helpful."
    )

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
