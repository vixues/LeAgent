"""Built-in workflow templates.

This module provides pre-defined workflow templates for common enterprise tasks
such as document processing, data extraction, and approval workflows.
"""

from typing import Any

DOCUMENT_EXTRACTION_WORKFLOW: dict[str, Any] = {
    "id": "document_extraction",
    "name": "Document Extraction Workflow",
    "description": "Extract structured data from documents (PDF, Word, Excel)",
    "version": "1.0.0",
    "inputs": [
        {"name": "file_path", "type": "string", "required": True, "description": "Path to the document"},
        {"name": "extraction_type", "type": "string", "default": "auto", "description": "Type of extraction"},
    ],
    "outputs": [
        {"name": "extracted_data", "value": "${outputs.extract.data}"},
        {"name": "summary", "value": "${outputs.summarize.content}"},
    ],
    "nodes": [
        {"id": "start", "type": "start", "next": "detect_type"},
        {
            "id": "detect_type",
            "type": "tool_call",
            "name": "Detect Document Type",
            "tool": "file_type_detector",
            "params": {"file_path": "${input.file_path}"},
            "output": "file_info",
            "next": "route_by_type",
        },
        {
            "id": "route_by_type",
            "type": "condition",
            "name": "Route by Document Type",
            "conditions": [
                {"if": {"left": "${var.file_info.type}", "operator": "eq", "right": "pdf"}, "then": "extract_pdf"},
                {"if": {"left": "${var.file_info.type}", "operator": "eq", "right": "docx"}, "then": "extract_word"},
                {"if": {"left": "${var.file_info.type}", "operator": "eq", "right": "xlsx"}, "then": "extract_excel"},
            ],
            "else": "unsupported_type",
        },
        {
            "id": "extract_pdf",
            "type": "tool_call",
            "name": "Extract PDF Content",
            "tool": "pdf_reader",
            "params": {"file_path": "${input.file_path}", "extract_tables": True},
            "output": "extract",
            "next": "summarize",
        },
        {
            "id": "extract_word",
            "type": "tool_call",
            "name": "Extract Word Content",
            "tool": "word_reader",
            "params": {"file_path": "${input.file_path}"},
            "output": "extract",
            "next": "summarize",
        },
        {
            "id": "extract_excel",
            "type": "tool_call",
            "name": "Extract Excel Content",
            "tool": "excel_reader",
            "params": {"file_path": "${input.file_path}"},
            "output": "extract",
            "next": "summarize",
        },
        {
            "id": "unsupported_type",
            "type": "error_handler",
            "name": "Handle Unsupported Type",
            "next": "end",
        },
        {
            "id": "summarize",
            "type": "llm_call",
            "name": "Summarize Extracted Content",
            "prompt": "Summarize the following extracted document content:\n\n${var.extract.data}",
            "output": "summarize",
            "next": "end",
        },
        {"id": "end", "type": "end"},
    ],
    "tags": ["document", "extraction"],
}


APPROVAL_WORKFLOW: dict[str, Any] = {
    "id": "approval_workflow",
    "name": "Multi-Level Approval Workflow",
    "description": "Generic approval workflow with configurable approval levels",
    "version": "1.0.0",
    "inputs": [
        {"name": "request_data", "type": "object", "required": True},
        {"name": "amount", "type": "number", "required": True},
        {"name": "requester", "type": "string", "required": True},
    ],
    "outputs": [
        {"name": "status", "value": "${var.approval_status}"},
        {"name": "approved_by", "value": "${var.approvers}"},
    ],
    "nodes": [
        {"id": "start", "type": "start", "next": "check_amount"},
        {
            "id": "check_amount",
            "type": "condition",
            "name": "Check Amount Threshold",
            "conditions": [
                {"if": {"left": "${input.amount}", "operator": "lt", "right": 1000}, "then": "auto_approve"},
                {"if": {"left": "${input.amount}", "operator": "lt", "right": 10000}, "then": "manager_review"},
            ],
            "else": "director_review",
        },
        {
            "id": "auto_approve",
            "type": "transform",
            "name": "Auto Approve Small Amount",
            "transform": {"approval_status": "approved", "approvers": ["system"]},
            "output": "approval_result",
            "next": "end",
        },
        {
            "id": "manager_review",
            "type": "human_review",
            "name": "Manager Approval",
            "reviewer": "manager",
            "review_prompt": "Please review this request for ${input.amount}:\n${input.request_data}",
            "timeout_sec": 86400,
            "output": "manager_approval",
            "next": "check_manager_result",
            "on_reject": "rejected",
        },
        {
            "id": "check_manager_result",
            "type": "condition",
            "conditions": [
                {"if": {"left": "${var.manager_approval.approved}", "operator": "eq", "right": True}, "then": "approved"},
            ],
            "else": "rejected",
        },
        {
            "id": "director_review",
            "type": "human_review",
            "name": "Director Approval",
            "reviewer": "director",
            "review_prompt": "High-value request (${input.amount}) requires director approval:\n${input.request_data}",
            "timeout_sec": 172800,
            "output": "director_approval",
            "next": "check_director_result",
            "on_reject": "rejected",
        },
        {
            "id": "check_director_result",
            "type": "condition",
            "conditions": [
                {"if": {"left": "${var.director_approval.approved}", "operator": "eq", "right": True}, "then": "approved"},
            ],
            "else": "rejected",
        },
        {
            "id": "approved",
            "type": "transform",
            "transform": {"approval_status": "approved"},
            "next": "end",
        },
        {
            "id": "rejected",
            "type": "transform",
            "transform": {"approval_status": "rejected"},
            "next": "end",
        },
        {"id": "end", "type": "end"},
    ],
    "tags": ["approval", "hr", "finance"],
}


BATCH_PROCESSING_WORKFLOW: dict[str, Any] = {
    "id": "batch_processing",
    "name": "Batch Processing Workflow",
    "description": "Process multiple items in parallel with aggregated results",
    "version": "1.0.0",
    "inputs": [
        {"name": "items", "type": "array", "required": True, "description": "List of items to process"},
        {"name": "processor", "type": "string", "default": "default_processor"},
    ],
    "outputs": [
        {"name": "results", "value": "${var.batch_results}"},
        {"name": "summary", "value": "${outputs.aggregate.summary}"},
    ],
    "nodes": [
        {"id": "start", "type": "start", "next": "validate_items"},
        {
            "id": "validate_items",
            "type": "condition",
            "conditions": [
                {"if": {"left": "${input.items}", "operator": "is_not_null"}, "then": "parallel_process"},
            ],
            "else": "empty_input",
        },
        {
            "id": "empty_input",
            "type": "transform",
            "transform": {"batch_results": [], "error": "No items provided"},
            "next": "end",
        },
        {
            "id": "parallel_process",
            "type": "parallel",
            "name": "Process Items in Parallel",
            "branches": [
                {
                    "id": "process_item",
                    "for_each": "${input.items}",
                    "nodes": ["process_single_item"],
                }
            ],
            "merge_strategy": "collect",
            "output": "batch_results",
            "next": "aggregate",
        },
        {
            "id": "process_single_item",
            "type": "tool_call",
            "tool": "${input.processor}",
            "params": {"item": "${var.item}"},
            "output": "item_result",
        },
        {
            "id": "aggregate",
            "type": "llm_call",
            "name": "Aggregate Results",
            "prompt": "Summarize the following batch processing results:\n${var.batch_results}",
            "output": "aggregate",
            "next": "end",
        },
        {"id": "end", "type": "end"},
    ],
    "tags": ["batch", "parallel"],
}


DATA_VALIDATION_WORKFLOW: dict[str, Any] = {
    "id": "data_validation",
    "name": "Data Validation Workflow",
    "description": "Validate data against configurable rules",
    "version": "1.0.0",
    "inputs": [
        {"name": "data", "type": "object", "required": True},
        {"name": "rule_set", "type": "string", "required": True},
    ],
    "outputs": [
        {"name": "is_valid", "value": "${var.validation_passed}"},
        {"name": "errors", "value": "${var.validation_errors}"},
        {"name": "report", "value": "${outputs.generate_report.report}"},
    ],
    "nodes": [
        {"id": "start", "type": "start", "next": "run_validation"},
        {
            "id": "run_validation",
            "type": "tool_call",
            "name": "Run Rule Validation",
            "tool": "rule_engine",
            "params": {"data": "${input.data}", "rule_set": "${input.rule_set}"},
            "output": "validation_result",
            "next": "check_result",
        },
        {
            "id": "check_result",
            "type": "condition",
            "conditions": [
                {"if": {"left": "${outputs.run_validation.passed}", "operator": "eq", "right": True}, "then": "validation_passed"},
            ],
            "else": "validation_failed",
        },
        {
            "id": "validation_passed",
            "type": "transform",
            "transform": {"validation_passed": True, "validation_errors": []},
            "next": "generate_report",
        },
        {
            "id": "validation_failed",
            "type": "transform",
            "transform": {
                "validation_passed": False,
                "validation_errors": "${outputs.run_validation.errors}",
            },
            "next": "generate_report",
        },
        {
            "id": "generate_report",
            "type": "llm_call",
            "name": "Generate Validation Report",
            "prompt": "Generate a validation report:\nPassed: ${var.validation_passed}\nErrors: ${var.validation_errors}",
            "output": "generate_report",
            "next": "end",
        },
        {"id": "end", "type": "end"},
    ],
    "tags": ["validation", "rules"],
}


SCRIPT_EXAMPLE_WORKFLOW: dict[str, Any] = {
    "id": "script_example",
    "name": "Script Node Example",
    "description": (
        "Demonstrates the in-process ScriptNode: normalize a list of "
        "numbers, compute summary stats, and round the results without "
        "spawning a subprocess."
    ),
    "version": "1.0.0",
    "inputs": [
        {
            "name": "values",
            "type": "array",
            "required": True,
            "description": "List of numeric values to summarize.",
        },
        {
            "name": "precision",
            "type": "integer",
            "default": 2,
            "description": "Decimal places for the rounded stats.",
        },
    ],
    "outputs": [
        {"name": "summary", "value": "${var.summary}"},
        {"name": "stdout", "value": "${outputs.compute.stdout}"},
    ],
    "nodes": [
        {"id": "start", "type": "start", "next": "compute"},
        {
            "id": "compute",
            "type": "script",
            "name": "Compute Summary Stats",
            "source": (
                "import statistics\n"
                "numbers = [float(v) for v in values]\n"
                "result = {\n"
                "    'count': len(numbers),\n"
                "    'sum': round(sum(numbers), precision),\n"
                "    'mean': round(statistics.fmean(numbers), precision)\n"
                "        if numbers else None,\n"
                "    'stdev': round(statistics.pstdev(numbers), precision)\n"
                "        if len(numbers) > 1 else 0.0,\n"
                "    'min': min(numbers) if numbers else None,\n"
                "    'max': max(numbers) if numbers else None,\n"
                "}\n"
                "print(f'computed summary for {len(numbers)} values')\n"
            ),
            "inputs": {
                "values": "${input.values}",
                "precision": "${input.precision}",
            },
            "timeout_sec": 2.0,
            "output": "summary",
            "next": "end",
        },
        {"id": "end", "type": "end"},
    ],
    "tags": ["script", "data", "example"],
}


# The four entries below are intentionally excluded from
# ``BUILTIN_TEMPLATES`` — they are superseded by the richer YAML
# templates under ``leagent/config/workflows/templates`` (``F-*.yaml``)
# and were contributing to template-gallery clutter. Their module-level
# dict definitions stay in place so any direct importers keep working;
# the template service simply stops publishing them to the UI.
_DEPRECATED_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "document_extraction": DOCUMENT_EXTRACTION_WORKFLOW,
    "approval_workflow": APPROVAL_WORKFLOW,
    "batch_processing": BATCH_PROCESSING_WORKFLOW,
    "data_validation": DATA_VALIDATION_WORKFLOW,
}

BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {}


def get_template(template_id: str) -> dict[str, Any] | None:
    """Get a built-in workflow template by ID.

    Args:
        template_id: The template identifier.

    Returns:
        The template definition dict, or None if not found.
    """
    return BUILTIN_TEMPLATES.get(template_id)


def list_templates() -> list[dict[str, str]]:
    """List all available built-in templates.

    Returns:
        List of template summaries with id, name, and description.
    """
    return [
        {
            "id": template["id"],
            "name": template["name"],
            "description": template.get("description", ""),
        }
        for template in BUILTIN_TEMPLATES.values()
    ]


__all__ = [
    "DOCUMENT_EXTRACTION_WORKFLOW",
    "APPROVAL_WORKFLOW",
    "BATCH_PROCESSING_WORKFLOW",
    "DATA_VALIDATION_WORKFLOW",
    "SCRIPT_EXAMPLE_WORKFLOW",
    "BUILTIN_TEMPLATES",
    "get_template",
    "list_templates",
]
