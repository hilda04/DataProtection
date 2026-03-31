from __future__ import annotations

import pytest

from services.report_builder import build_assessment_report_pdf


def test_build_assessment_report_pdf_returns_valid_pdf_bytes() -> None:
    pytest.importorskip('reportlab')
    pdf_bytes = build_assessment_report_pdf(
        {
            'organisation': {'name': 'Example Org'},
            'framework': {'name': 'Zimbabwe DPA', 'version': '2021'},
            'score': 72.5,
            'maturity_level': 'Defined',
            'summary': 'Summary text for executive review.',
            'sections': [{'name': 'Governance', 'score': 80}],
            'recommendations': [
                {
                    'title': 'Document incident response governance',
                    'risk': 'Delayed breach handling can increase legal exposure.',
                    'actions': [
                        'Formalise incident-response RACI and approvals.',
                        'Run at least one breach-notification exercise.',
                    ],
                    'evidence': [
                        'Approved incident-response procedure',
                        'Exercise report with lessons learned',
                    ],
                    'priority': 'HIGH',
                }
            ],
        }
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b'%PDF')
    assert len(pdf_bytes) > 500
    decoded = pdf_bytes.decode('latin-1', errors='ignore')
    assert 'Remediation Plan' in decoded
    assert 'Executive Summary' in decoded
    assert 'Section Performance' in decoded
    assert 'Remediation Plan' in decoded
    assert 'Gap 1' in decoded
    assert 'Compliance Relevance' in decoded
    assert 'Appendix A: Evidence Checklist for Audit Readiness' in decoded
    assert 'Approved incident-response procedure' in decoded
