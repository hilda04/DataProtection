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
            'sections': [{'name': 'Governance', 'score': 80}],
            'recommendations': [{'recommendation': 'Improve incident response controls.'}],
        }
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b'%PDF')
    assert len(pdf_bytes) > 500
