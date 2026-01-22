# IdeaGen Feature Summary

**IdeaGen** is a specialized business idea generator designed for the "AI Agent economy." It empowers users to discover, customize, and compare innovative business opportunities by leveraging multiple advanced AI models simultaneously.

## Core Value Proposition
Generate, customize, and compare business ideas tailored for the AI agent economy using multiple state-of-the-art AI models.

## Key Features

### 1. Multi-Model AI Generation
Users can generate business ideas using up to four distinct AI models to get diverse perspectives:
*   **OpenAI** (labeled as *GPT-5 Nano*)
*   **Google** (labeled as *Gemini 3 Pro Preview*)
*   **DeepSeek** (labeled as *DeepSeek Chat*)
*   **Grok** (labeled as *Grok 4.1 Fast Reasoning*)
*   *Note: Results are displayed in a tabbed interface for easy side-by-side comparison.*

### 2. Advanced Customization
Users can tailor the idea generation process through specific configurations:
*   **Target Industry:** Selection from 15+ sectors including FinTech, HealthTech, EdTech, AgriTech, and CleanTech.
*   **Constraints:** Filters to refine the idea, such as "Low Startup Cost (<$5k)", "No-Code Solution", "B2B SaaS", or "Enterprise Scale".
*   **AI Persona:** Options to adjust the generation tone:
    *   *Neutral / Professional*
    *   *Critical VC Investor* (Risk-focused analysis)
    *   *Optimistic Visionary* (Growth-focused analysis)

### 3. Freemium vs. Premium Tiering
The app differentiates features based on user status (controlled via Clerk authentication roles):
*   **Free / Basic Access:**
    *   Limited to the **OpenAI** model only.
    *   Restricted to the **Neutral** persona.
    *   Limited constraint options.
*   **Premium Access:**
    *   **Unlocks all 4 AI models** for simultaneous generation.
    *   **Unlocks all Personas** (VC Investor & Visionary).
    *   **Unlocks all Constraints** (Budget, Business Model).
    *   **Enables Export Tools** (PDF & Email).

### 4. Export & Sharing Tools (Premium)
*   **PDF Report:** Generates a professional, formatted PDF containing the user's configuration and the full text of ideas from all selected models.
*   **Email Integration:** Allows users to send the generated PDF report directly to any email address via the **Resend** API.

### 5. Technical & Security Features
*   **Authentication:** Secure sign-up and sign-in powered by **Clerk**.
*   **Responsive UI:** A modern, dark-mode compatible interface built with **Next.js** and **Tailwind CSS**.
*   **Backend Processing:** A robust **FastAPI (Python)** backend handles the orchestration of AI requests and PDF generation (`xhtml2pdf`).
