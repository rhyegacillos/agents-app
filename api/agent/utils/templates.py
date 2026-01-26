from typing import Dict, Any

from ..models import Visit

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "generic": {
        "label": "Generic Summary",
        "headings": ["Visit Summary", "Key Findings", "Assessment"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Visit Summary</h4>\n"
            "<p>...</p>\n"
            "<h4>Key Findings</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Assessment</h4>\n"
            "<p>...</p>"
        ),
    },
    "soap": {
        "label": "SOAP",
        "headings": ["Subjective", "Objective", "Assessment", "Plan"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Subjective</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Objective</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Assessment</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Plan</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "discharge": {
        "label": "Discharge Summary",
        "headings": [
            "Primary Diagnosis",
            "Treatment Provided",
            "Medications",
            "Discharge Instructions",
            "Follow-up & Red Flags",
        ],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Primary Diagnosis</h4>\n"
            "<p>...</p>\n"
            "<h4>Treatment Provided</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Medications</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Discharge Instructions</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Follow-up & Red Flags</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "referral": {
        "label": "Referral Letter",
        "headings": [
            "Reason for Referral",
            "Key Findings",
            "Tests/Imaging",
            "Assessment",
            "Requested Action",
        ],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Reason for Referral</h4>\n"
            "<p>...</p>\n"
            "<h4>Key Findings</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Tests/Imaging</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Assessment</h4>\n"
            "<p>...</p>\n"
            "<h4>Requested Action</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "follow_up": {
        "label": "Follow-Up Visit",
        "headings": [
            "Progress Since Last Visit",
            "Current Symptoms",
            "Medications/Changes",
            "Updated Plan",
            "Next Visit",
        ],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Progress Since Last Visit</h4>\n"
            "<p>...</p>\n"
            "<h4>Current Symptoms</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Medications/Changes</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Updated Plan</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Next Visit</h4>\n"
            "<p>...</p>"
        ),
    },
    "surgery": {
        "label": "Surgery Note",
        "headings": ["Procedure", "Findings", "Complications", "Post-Op Plan"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Procedure</h4>\n"
            "<p>...</p>\n"
            "<h4>Findings</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Complications</h4>\n"
            "<p>...</p>\n"
            "<h4>Post-Op Plan</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
    "med_review": {
        "label": "Medication Review",
        "headings": ["Current Medications", "Changes Made", "Issues/Side Effects", "Recommendations"],
        "summary_html": (
            "Use this HTML inside the Summary section:\n"
            "<h4>Current Medications</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Changes Made</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Issues/Side Effects</h4>\n"
            "<ul><li>...</li></ul>\n"
            "<h4>Recommendations</h4>\n"
            "<ul><li>...</li></ul>"
        ),
    },
}


def get_template(visit: Visit) -> Dict[str, Any]:
    template_id = (visit.template_id or "generic").strip()
    return TEMPLATES.get(template_id, TEMPLATES["generic"])
