"""Document Classifier Tool - Classify documents by type using LLM or rules.

Supports classification of documents into categories like invoice, contract,
report, resume, letter, etc.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


DOCUMENT_TYPES = [
    "invoice",
    "contract",
    "report",
    "resume",
    "letter",
    "memo",
    "proposal",
    "specification",
    "manual",
    "receipt",
    "form",
    "certificate",
    "agreement",
    "presentation",
    "spreadsheet",
    "other",
]

RULE_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "invoice": [
        (r"(?i)\b(invoice|发票|bill\s+to|amount\s+due|total\s+amount)\b", 0.8),
        (r"(?i)\b(qty|quantity|unit\s+price|subtotal)\b", 0.5),
        (r"(?i)\b(payment\s+terms|due\s+date|invoice\s+(no|number|#))\b", 0.7),
    ],
    "contract": [
        (r"(?i)\b(contract|agreement|合同|hereby\s+agree|terms\s+and\s+conditions)\b", 0.8),
        (r"(?i)\b(party|whereas|witnesseth|甲方|乙方)\b", 0.6),
        (r"(?i)\b(effective\s+date|termination|breach|indemnify)\b", 0.5),
    ],
    "report": [
        (r"(?i)\b(report|报告|analysis|findings|executive\s+summary)\b", 0.7),
        (r"(?i)\b(conclusion|recommendation|methodology|abstract)\b", 0.5),
        (r"(?i)\b(figure\s+\d|table\s+\d|appendix)\b", 0.4),
    ],
    "resume": [
        (r"(?i)\b(resume|curriculum\s+vitae|cv|简历)\b", 0.9),
        (r"(?i)\b(education|experience|skills|objective)\b", 0.6),
        (r"(?i)\b(work\s+history|references|certifications)\b", 0.5),
    ],
    "letter": [
        (r"(?i)\b(dear\s+\w+|sincerely|regards|尊敬的|此致)\b", 0.7),
        (r"(?i)^(to|from|date|subject):\s*", 0.5),
    ],
    "memo": [
        (r"(?i)\b(memo|memorandum|备忘录)\b", 0.9),
        (r"(?i)^(to|from|date|subject|re):\s*", 0.6),
    ],
    "proposal": [
        (r"(?i)\b(proposal|提案|proposed|we\s+propose)\b", 0.8),
        (r"(?i)\b(scope\s+of\s+work|deliverables|timeline|budget)\b", 0.6),
    ],
    "specification": [
        (r"(?i)\b(specification|spec|规格|requirements)\b", 0.8),
        (r"(?i)\b(version|revision|dimensions|tolerance)\b", 0.5),
    ],
    "manual": [
        (r"(?i)\b(manual|guide|handbook|手册|instructions)\b", 0.8),
        (r"(?i)\b(step\s+\d|warning|caution|note:)\b", 0.5),
    ],
    "receipt": [
        (r"(?i)\b(receipt|收据|transaction|paid|thank\s+you)\b", 0.8),
        (r"(?i)\b(cash|card|change|subtotal)\b", 0.5),
    ],
    "form": [
        (r"(?i)\b(form|表格|please\s+fill|signature|checkbox)\b", 0.7),
        (r"(?i)_{3,}|\.{3,}", 0.4),
    ],
    "certificate": [
        (r"(?i)\b(certificate|certify|证书|awarded|completed)\b", 0.8),
        (r"(?i)\b(hereby|授予|valid\s+until|expiry)\b", 0.5),
    ],
    "agreement": [
        (r"(?i)\b(agreement|协议|mutual|parties\s+agree)\b", 0.8),
        (r"(?i)\b(terms|conditions|obligations|rights)\b", 0.5),
    ],
}

LLM_CLASSIFICATION_PROMPT = """Classify the following document into one of these categories:
{categories}

Document text (first 2000 characters):
---
{text}
---

Respond with ONLY the category name in lowercase, nothing else.
If unsure, respond with "other".

Category:"""


class DocClassifierTool(BaseTool):
    """Classify documents by type using LLM or rule-based classification.

    Features:
    - Rule-based classification using keyword patterns
    - LLM-based classification for more accurate results
    - Confidence scoring
    - Support for Chinese and English documents
    """

    name = "doc_classifier"
    description = (
        "Classify documents into categories (invoice, contract, report, resume, etc.) "
        "using rule-based patterns or LLM analysis."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["classify", "categorize", "doc_type"]
    search_hint = "classify document type invoice contract report resume category"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000
    path_params = ("file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The document text to classify.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to a text file to classify (alternative to text parameter).",
                },
                "method": {
                    "type": "string",
                    "enum": ["rules", "llm", "hybrid"],
                    "description": (
                        "Classification method: 'rules' (pattern matching), 'llm' (AI-based), "
                        "'hybrid' (rules first, LLM if uncertain). Defaults to 'hybrid'."
                    ),
                    "default": "hybrid",
                },
                "confidence_threshold": {
                    "type": "number",
                    "description": "Minimum confidence for rule-based classification. Defaults to 0.6.",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.6,
                },
                "custom_categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Custom category list to use instead of defaults (for LLM method).",
                },
            },
            "oneOf": [
                {"required": ["text"]},
                {"required": ["file_path"]},
            ],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Classifying document"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Classify a document by type.

        Args:
            params: Tool parameters including text or file_path and classification options.
            context: Execution context.

        Returns:
            Dictionary containing classification result and confidence.

        Raises:
            ValueError: If neither text nor file_path is provided.
            FileNotFoundError: If the specified file doesn't exist.
        """
        text = params.get("text")
        file_path = params.get("file_path")
        method = params.get("method", "hybrid")
        confidence_threshold = params.get("confidence_threshold", 0.6)
        custom_categories = params.get("custom_categories")

        if not text and not file_path:
            raise ValueError("Either 'text' or 'file_path' must be provided.")

        if file_path:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            text = path.read_text(encoding="utf-8", errors="ignore")

        if not text or not text.strip():
            return {
                "category": "other",
                "confidence": 0.0,
                "method_used": method,
                "warning": "Empty or unreadable document.",
            }

        categories = custom_categories or DOCUMENT_TYPES

        logger.info(
            "Classifying document",
            method=method,
            text_length=len(text),
        )

        if method == "rules":
            return self._classify_with_rules(text, confidence_threshold)

        elif method == "llm":
            return await self._classify_with_llm(text, categories, context)

        else:
            rules_result = self._classify_with_rules(text, confidence_threshold)

            if rules_result["confidence"] >= confidence_threshold:
                rules_result["method_used"] = "rules"
                return rules_result

            if context.llm is None:
                rules_result["warning"] = (
                    "Rule-based confidence below threshold and no LLM available. "
                    "Using best rule-based guess."
                )
                rules_result["method_used"] = "rules (fallback)"
                return rules_result

            llm_result = await self._classify_with_llm(text, categories, context)
            llm_result["rules_suggestion"] = rules_result["category"]
            llm_result["rules_confidence"] = rules_result["confidence"]
            return llm_result

    def _classify_with_rules(self, text: str, threshold: float) -> dict[str, Any]:
        """Classify document using rule-based pattern matching.

        Args:
            text: Document text to classify.
            threshold: Minimum confidence threshold.

        Returns:
            Classification result with category and confidence.
        """
        scores: dict[str, float] = {cat: 0.0 for cat in RULE_PATTERNS}
        matches: dict[str, list[str]] = {cat: [] for cat in RULE_PATTERNS}

        for category, patterns in RULE_PATTERNS.items():
            for pattern, weight in patterns:
                found = re.findall(pattern, text[:5000])
                if found:
                    scores[category] += weight * min(len(found), 3) / 3
                    matches[category].extend(found[:3])

        if not any(scores.values()):
            return {
                "category": "other",
                "confidence": 0.0,
                "method_used": "rules",
                "scores": scores,
            }

        max_score = max(scores.values())
        if max_score > 0:
            scores = {k: v / (max_score * 1.2) for k, v in scores.items()}

        best_category = max(scores, key=lambda k: scores[k])
        confidence = min(scores[best_category], 1.0)

        top_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]

        result: dict[str, Any] = {
            "category": best_category,
            "confidence": round(confidence, 3),
            "method_used": "rules",
            "top_matches": [{"category": cat, "score": round(score, 3)} for cat, score in top_categories],
        }

        if matches.get(best_category):
            result["matched_keywords"] = list(set(matches[best_category]))[:5]

        logger.info(
            "Rule-based classification complete",
            category=best_category,
            confidence=confidence,
        )

        return result

    async def _classify_with_llm(
        self,
        text: str,
        categories: list[str],
        context: ToolContext,
    ) -> dict[str, Any]:
        """Classify document using LLM.

        Args:
            text: Document text to classify.
            categories: List of possible categories.
            context: Execution context with LLM client.

        Returns:
            Classification result with category and confidence.
        """
        if context.llm is None:
            raise RuntimeError("LLM client not available for classification.")

        truncated_text = text[:2000]

        prompt = LLM_CLASSIFICATION_PROMPT.format(
            categories=", ".join(categories),
            text=truncated_text,
        )

        try:
            response = await context.llm.complete(prompt, max_tokens=50)
            predicted_category = response.strip().lower()

            if predicted_category not in categories:
                for cat in categories:
                    if cat in predicted_category:
                        predicted_category = cat
                        break
                else:
                    predicted_category = "other"

            result: dict[str, Any] = {
                "category": predicted_category,
                "confidence": 0.85,
                "method_used": "llm",
            }

            logger.info(
                "LLM classification complete",
                category=predicted_category,
            )

            return result

        except Exception as e:
            logger.error("LLM classification failed", error=str(e))
            return {
                "category": "other",
                "confidence": 0.0,
                "method_used": "llm (failed)",
                "error": str(e),
            }
