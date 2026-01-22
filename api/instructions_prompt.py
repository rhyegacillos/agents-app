

def system_instructions(tone: str) -> str:
    return f"""
        You are an expert product strategist and business model designer for AI agent products.
        Write in semantic HTML only (no Markdown, no plaintext outside HTML).
        Persona: {tone}

        Rules:
        - Do NOT invent facts (market sizes, regulation details, customer counts). You may estimate only if you label it clearly as an assumption.
        - Prefer concrete workflows, failure modes, constraints, and measurable outcomes.
        - Every claim must be tied to a specific customer job, trigger, or operational constraint.
        - Keep the idea defensible: clear wedge, clear ICP, clear why-now.
    """.strip()


def user_instruction(industry: str = None, constraint: str = None) -> str:

    return f"""
        Generate ONE high-conviction business idea for AI Agents in the industry: "{industry}".
        Constraints: "{constraint or 'None'}".

        Output MUST be valid semantic HTML and include these sections in this exact order:

        <section data-section="title">
        <h1>Business name (3–5 words)</h1>
        <p>Subtitle: who it’s for + outcome (one sentence)</p>
        </section>


        <section data-section="one_liner">
        <h2>One-liner</h2>
        <p>...</p>
        </section>

        <section data-section="icp">
        <h2>Ideal Customer Profile</h2>
        <ul>
            <li>Primary buyer: ...</li>
            <li>Primary user: ...</li>
            <li>Company size / context: ...</li>
            <li>Tooling they already use: ...</li>
        </ul>
        </section>

        <section data-section="pain_and_trigger">
        <h2>Pain + Trigger</h2>
        <ul>
            <li>Trigger event that causes urgency: ...</li>
            <li>What breaks today (specific failure mode): ...</li>
            <li>Cost of doing nothing (time, risk, revenue reminder): ...</li>
        </ul>
        </section>

        <section data-section="workflow">
        <h2>Current Workflow (Before)</h2>
        <ol>
            <li>Step 1...</li>
            <li>Step 2...</li>
            <li>Step 3...</li>
        </ol>
        </section>

        <section data-section="agent_solution">
        <h2>AI Agent Solution (After)</h2>
        <ol>
            <li>Agent inputs (systems, documents, signals): ...</li>
            <li>Agent actions (tools it uses): ...</li>
            <li>Human approval points: ...</li>
            <li>Outputs (artifacts): ...</li>
        </ol>
        </section>

        <section data-section="mvp_scope">
        <h2>MVP Scope (30 days)</h2>
        <ul>
            <li>Must-have features: ...</li>
            <li>Deliberately NOT building: ... (and why)</li>
            <li>Data needed on day 1: ...</li>
        </ul>
        </section>

        <section data-section="pricing">
        <h2>Pricing + Packaging</h2>
        <ul>
            <li>Pricing model: ...</li>
            <li>Price anchor logic (what it replaces/saves): ...</li>
            <li>Plan tiers (if any): ...</li>
        </ul>
        </section>

        <section data-section="moat">
        <h2>Differentiation + Moat</h2>
        <ul>
            <li>Why you win vs generic copilots: ...</li>
            <li>Data flywheel or integration advantage: ...</li>
            <li>Switching costs: ...</li>
        </ul>
        </section>

        <section data-section="risks">
        <h2>Key Risks + Mitigations</h2>
        <ul>
            <li>Risk: ... → Mitigation: ...</li>
            <li>Risk: ... → Mitigation: ...</li>
        </ul>
        </section>

        <section data-section="gtm">
        <h2>Go-to-Market Wedge</h2>
        <ul>
            <li>First channel: ...</li>
            <li>First 10 customers plan: ...</li>
            <li>Sales motion: PLG / founder-led / outbound: ...</li>
        </ul>
        </section>

        <section data-section="metrics">
        <h2>Success Metrics</h2>
        <ul>
            <li>Activation metric: ...</li>
            <li>Weekly value metric: ...</li>
            <li>Retention signal: ...</li>
            <li>Quality metric (agent reliability): ...</li>
        </ul>
        </section>

        Hard requirements:
        - Make it specific to "{industry}" and compatible with constraint "{constraint or 'None'}".
        - Avoid generic “AI agent that automates X” wording—name concrete systems, artifacts, approvals, and edge cases.
        - Include at least 2 failure modes and how the agent handles them safely (guardrails).
        - If constraint includes "No-Code", design for Zapier/Make/Airtable/Notion style integrations.
        - If constraint includes "Low Startup Cost", avoid deep integrations and propose a lightweight wedge.
    """.strip()