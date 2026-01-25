# IdeaGen Feature Summary

**IdeaGen** is a specialized business idea generator designed for the "AI Agent economy." It empowers users to discover, customize, and compare innovative business opportunities by leveraging multiple advanced AI models simultaneously.

## Core Value Proposition
Generate, customize, and compare business ideas tailored for the AI agent economy using multiple state-of-the-art AI models.

## Key Features

### 1. Multi-Model AI Generation
Users can generate business ideas using up to four distinct AI model providers to get diverse perspectives:
*   **OpenAI**
*   **Google Gemini**
*   **DeepSeek**
*   **Grok**
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

### 4. Saved Results & Run Management
*   **Auto-save:** Generated runs are saved automatically for easy retrieval.
*   **Saved Results:** Users can load, compare, or delete past runs from a dedicated Saved Results panel.

### 5. Model Ranking (Per Run)
*   **Automatic ranking:** A separate analysis agent ranks model outputs for the same configuration using clarity, feasibility, differentiation, actionability, risk awareness, and stakeholder-readiness.
*   **Rank highlights:** Summarizes why a model performed best and lists key decision-ready highlights.

### 6. Compare Results (Across Runs)
*   **Diff Insight:** Compares the top-ranked outputs of two runs with the same configuration.
*   **Winner + rationale:** Highlights key changes, risks, and a winner to support quick decisions.

### 7. Decision Summary Report (Across Runs)
*   **Rank Reports:** Ranks multiple saved runs and summarizes insights, risks, and next steps.
*   **Stakeholder-ready:** Produces a single decision-ready summary across runs.

### 8. Export & Sharing Tools (Premium)
*   **PDF Reports:** Generates professional PDFs for generated results, compare results, and decision summaries.
*   **Email Integration:** Sends PDFs directly via the **Resend** API.

### 9. Technical & Security Features
*   **Authentication:** Secure sign-up and sign-in powered by **Clerk**.
*   **Responsive UI:** A modern, dark-mode compatible interface built with **Next.js** and **Tailwind CSS**.
*   **Backend Processing:** A robust **FastAPI (Python)** backend handles the orchestration of AI requests and PDF generation (`xhtml2pdf`).
