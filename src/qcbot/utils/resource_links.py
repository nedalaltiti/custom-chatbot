"""
Resource links registry and matching utilities for QC bot.

This module holds curated SharePoint links and provides helper functions to
detect when a user is asking for a specific resource so we can respond with
detailed information about the resource and its link.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import re


@dataclass(frozen=True)
class ResourceLink:
    """Represents a named resource link with description."""

    title: str
    url: str
    description: str


# Curated QC resource links
RESOURCES: List[ResourceLink] = [
    ResourceLink(
        title="Coaching Request Form (CRF)",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "New%20Coaching%20Request%20Form%20%20CRF/AllItems.aspx"
        ),
        description="A SharePoint to collect requests raised by agents."
    ),
    ResourceLink(
        title="Inbound Client - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Inbound%20Client%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for clients inbound calls."
    ),
    ResourceLink(
        title="Inbound Business - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Inbound%20Business%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for clients’ outbound calls."
    ),
    ResourceLink(
        title="Outbound Client - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Outbound%20Client%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="Specialized center for outbound client operations quality control. Tracks audit results, coaching sessions, and performance metrics for outbound client-facing teams."
    ),
    ResourceLink(
        title="Outbound Business - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Outbound%20Business%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for business outbound calls."
    ),
    ResourceLink(
        title="Sales - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Sales%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for Sales Department."
    ),
    ResourceLink(
        title="Legal Sales - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Legal%20Sales%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for Legal Sales."
    ),
    ResourceLink(
        title="Affiliates - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Affiliates%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for Affiliates."
    ),
    ResourceLink(
        title="Payments Processing - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Settlement%20Processing%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for Payments Processing."
    ),
    ResourceLink(
        title="Payments (Settlement at Risk) - Audit & Coaching Center",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "NEW%20Settlement%20At%20Risk%20%20Audit%20%20Coaching%20Center/AllItems.aspx"
        ),
        description="A SharePoint List that contains all the audit data for Payments (Settlement at Risk) division."
    ),
    ResourceLink(
        title="Organizational Head count",
        url=(
            "https://usclarity-my.sharepoint.com/:x:/p/mustafa_a/"
            "EazsNsW4RBRFssKHJqckHh8BhA6mp3DorMpAW8G9LaVqDg?e=pmRADP"
        ),
        description="An up to date excel sheet that outlines the agents in each department."
    ),
    ResourceLink(
        title="Audit Dispute Form (ADF)",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Audit%20Dispute%20Form%20ADF/AllItems.aspx"
        ),
        description="A SharePoint that stores all the disputes raised by team leads/manager across all operational departments."
    ),
    ResourceLink(
        title="Audit Dispute Tracker (Team Leads version)",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Audit%20Dispute%20Tracker%20ADT/AllItems.aspx"
        ),
        description="A SharePoint that stores all the disputes raised by team leads/manager across all operational departments, available for other departments."
    ),
    ResourceLink(
        title="Calls Scorecard",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FQualityAssuranceTeam%2FShared%20Documents%2FQC%20Scorecards%2FCalls%20Scorecards&viewid=84f4a51e%2D7be8%2D450f%2D8adb%2D02e27c61be42"
        ),
        description="Calls Scorecard template. "
    ),
    ResourceLink(
        title="QUALITY Attendance Record",
        url=(
            "https://usclarity-my.sharepoint.com/:x:/p/hamza_m/ERtEFF6pCpJIpNQxABrjfyYBA6fDsYzSlw3y0cNZ5wAvvA?e=tdrLzl&nav=MTVfezAwMDAwMDAwLTAwMDEtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMH0"
        ),
        description="An excel sheet that tracks the absenteeism for QUALITY team."
    ),
    ResourceLink(
        title="Non-Calls Scorecard",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FQualityAssuranceTeam%2FShared%20Documents%2FQC%20Scorecards%2FNon%2DCalls%20Scorecards&viewid=84f4a51e%2D7be8%2D450f%2D8adb%2D02e27c61be42"
        ),
        description="Non-calls Scorecard template. "
    ),
    ResourceLink(
        title="All Departments Docs",
        url=(
            "https://usclarity-my.sharepoint.com/:f:/p/qualitycontrol/"
            "EjqyWBxY61JHiyYlzLkdgXYBJ815n4poIVY-ap2cCuTTuw?e=3lOvS5"
        ),
        description="A folder combining all documents we have in the department."
    ),
    ResourceLink(
        title="Declined Settlements",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Declined%20Settlements/AllItems.aspx"
        ),
        description="A record that shows all the declined settlements by Payments due to a submission error by Negotiations."
    ),
    ResourceLink(
        title="Quality Leaves Tracker",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Quality%20Leaves%20Tracker/AllItems.aspx"
        ),
        description="A SharePoint List that tracks the absenteeism for QUALITY team."
    ),
    ResourceLink(
        title="Additional Assignments/Projects",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Additional%20Assignments%20Tracker/AllItems.aspx"
        ),
        description="A SharePoint List that tracks the side project hours for QUALITY team."
    ),
    ResourceLink(
        title="Quality Coaching Hub",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Coaching%20Hub/AllItems.aspx"
        ),
        description="A SharePoint List that stores the coaching sessions done by the Quality team with agents."
    ),
    ResourceLink(
        title="Coaching By Quality Survey",
        url=(
            "https://usclarity.sharepoint.com/sites/QualityAssuranceTeam/Lists/"
            "Coaching%20By%20Quality%20Survey1/AllItems.aspx"
        ),
        description="A SharePoint List that stores the evaluations done by agents that have been coached by the Quality Team."
    ),
]


_STOP_WORDS = {
    "the",
    "and",
    "of",
    "for",
    "to",
    "by",
    "in",
    "on",
    "at",
    "&",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _tokenize(text: str) -> List[str]:
    norm = _normalize(text)
    tokens = [t for t in norm.split(" ") if t and t not in _STOP_WORDS]
    return tokens


def _match_score(query: str, resource: ResourceLink) -> int:
    """Return a match score using only the resource title (no manual keywords)."""
    q_norm = _normalize(query)
    t_norm = _normalize(resource.title)

    # Strong signals
    score = 0
    if q_norm and (q_norm in t_norm or t_norm in q_norm):
        score += 3

    # Token overlap
    q_tokens = set(_tokenize(query))
    t_tokens = set(_tokenize(resource.title))
    score += len(q_tokens & t_tokens)

    # If title has acronym-like tokens in parentheses, ensure they are captured by tokens
    return score


def find_resource_links(user_query: str, max_items: int | None = None) -> List[ResourceLink]:
    """
    Find best-matching resource links for the given user query.
    
    Only returns matches if the query explicitly asks for links/resources,
    not just mentions resource names in passing.
    """
    q = (user_query or "").strip().lower()
    if not q:
        return []

    # Check if this looks like a request for links/resources
    link_request_keywords = {
        "link", "links", "resource", "resources", "form", "forms", 
        "where", "find", "access", "get", "sharepoint", "list", "lists",
        "url", "website", "page", "portal", "hub", "center"
    }
    
    # Check if query contains link request keywords
    has_link_keywords = any(keyword in q for keyword in link_request_keywords)
    
    # If no link keywords, only match if there's a very strong direct match
    if not has_link_keywords:
        # Only match exact acronyms or very specific resource names
        for res in RESOURCES:
            q_norm = _normalize(q)
            t_norm = _normalize(res.title)
            
            # Check for exact acronym match (e.g., "CRF", "ADF")
            if len(q_norm) <= 5 and q_norm in t_norm:
                # Make sure it's not just a partial word match
                if q_norm in ["crf", "adf", "adt"] or q_norm in t_norm.split():
                    return [res]
        
        # No strong matches found, return empty
        return []

    # If it has link keywords, proceed with normal matching
    scored = [(res, _match_score(q, res)) for res in RESOURCES]

    # Require a stronger signal than a single generic word unless there's a direct substring hit
    matches = []
    for res, sc in scored:
        if sc >= 2:
            matches.append(res)
        else:
            # Allow single-token strong match like acronyms (e.g., CRF) via substring
            q_norm = _normalize(q)
            t_norm = _normalize(res.title)
            if q_norm and (q_norm in t_norm or t_norm in q_norm):
                matches.append(res)

    # Sort by score descending, keep stable order on ties
    matches.sort(key=lambda r: _match_score(q, r), reverse=True)

    if max_items is not None:
        matches = matches[:max_items]

    return matches


def format_links_response(links: List[ResourceLink]) -> str:
    """Format a detailed response with resource information and links."""
    if not links:
        return ""

    if len(links) == 1:
        # Single resource - provide detailed information
        res = links[0]
        lines = [
            f"Here is the information about the {res.title}:",
            "",
            f"• **DOCUMENTATIONS AND RECORDS** \n",
            f"Record: {res.title} \n",
            f"Purpose: {res.description} \n",
            f"Link: {res.url} \n",
            "",
            "Is there anything else I can help you with?"
        ]
        return "\n".join(lines)
    else:
        # Multiple resources - provide summary with links
        lines = ["Here are the requested resources:"]
        lines.append("")
        for res in links:
            lines.append(f"• **{res.title}**: {res.description}")
            lines.append(f"  Link: {res.url}")
            lines.append("")
        lines.append("Is there anything else I can help you with?")
        return "\n".join(lines)


