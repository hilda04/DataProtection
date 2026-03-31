import unittest
from decimal import Decimal

from services.assessment_engine import (
    calculate_assessment_score,
    calculate_weighted_score,
    generate_findings,
)


class AssessmentEngineTests(unittest.TestCase):
    def test_calculate_weighted_score_returns_percentage_and_sections(self) -> None:
        responses = [
            {
                "sectionId": "governance",
                "controlId": "CTRL-1",
                "score": 4,
                "weight": 2,
                "priority": "high",
                "findingTemplate": "",
                "recommendation": "",
            },
            {
                "sectionId": "governance",
                "controlId": "CTRL-2",
                "score": 2,
                "weight": 2,
                "priority": "medium",
                "findingTemplate": "",
                "recommendation": "",
            },
        ]

        result = calculate_weighted_score(responses)

        self.assertEqual(result["overallScore"], 75)
        self.assertEqual(result["sectionScores"], [{"sectionId": "governance", "score": 75}])

    def test_generate_findings_flags_low_maturity_controls(self) -> None:
        responses = [
            {
                "sectionId": "security",
                "controlId": "CTRL-3",
                "score": 1,
                "weight": 5,
                "priority": "high",
                "findingTemplate": "Gap",
                "recommendation": "Fix gap",
            },
            {
                "sectionId": "security",
                "controlId": "CTRL-4",
                "score": 3,
                "weight": 1,
                "priority": "low",
                "findingTemplate": "Skip",
                "recommendation": "Skip",
            },
        ]

        findings = generate_findings(responses)

        self.assertEqual(
            findings,
            [
                {
                    "controlId": "CTRL-3",
                    "riskLevel": "High",
                    "summary": "Gap",
                    "recommendedAction": "Fix gap",
                }
            ],
        )

    def test_calculate_assessment_score_supports_decimal_values(self) -> None:
        result = calculate_assessment_score(
            {
                "governance": [
                    {"questionId": "q1", "value": Decimal("4")},
                    {"questionId": "q2", "value": Decimal("2")},
                ]
            }
        )

        self.assertEqual(result["score"], 75.0)
        self.assertEqual(result["sectionScores"], [{"sectionId": "governance", "score": 75.0}])


if __name__ == "__main__":
    unittest.main()
