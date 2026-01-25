#!/usr/bin/env python3
"""
DOE SBIR Test Suite
Comprehensive test suite for DOE technical domains: SETO, BETO, HFTO
"""
import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

@dataclass
class DOEQuery:
    """Represents a DOE-specific test query"""
    query: str
    office: str  # SETO, BETO, HFTO, Cross-cutting
    category: str
    expected_domains: List[str]  # Expected relevant domains
    min_score_threshold: float = 0.6  # Minimum acceptable semantic score
    description: str = ""

class DOETestSuite:
    """Comprehensive DOE SBIR test suite"""

    def __init__(self):
        self.queries = self._load_test_queries()

    def _load_test_queries(self) -> List[DOEQuery]:
        """Load comprehensive DOE test queries"""

        return [
            # SETO (Solar Energy Technologies Office)
            DOEQuery(
                query="perovskite tandem solar cells",
                office="SETO",
                category="Photovoltaics",
                expected_domains=["solar", "photovoltaic", "perovskite", "tandem"],
                min_score_threshold=0.7,
                description="Tandem solar cells combining perovskite with traditional silicon"
            ),
            DOEQuery(
                query="quantum dot photovoltaics",
                office="SETO",
                category="Photovoltaics",
                expected_domains=["solar", "photovoltaic", "quantum", "nanoparticle"],
                min_score_threshold=0.7,
                description="Quantum dot enhanced solar cells"
            ),
            DOEQuery(
                query="transparent conducting oxides",
                office="SETO",
                category="Materials",
                expected_domains=["transparent", "conducting", "oxide", "TCO"],
                min_score_threshold=0.6,
                description="TCO materials for solar applications"
            ),
            DOEQuery(
                query="photovoltaic efficiency",
                office="SETO",
                category="Performance",
                expected_domains=["photovoltaic", "efficiency", "solar", "cell"],
                min_score_threshold=0.6,
                description="Solar cell efficiency improvements"
            ),

            # BETO (Bioenergy Technologies Office)
            DOEQuery(
                query="catalytic fast pyrolysis",
                office="BETO",
                category="Bioconversion",
                expected_domains=["biomass", "pyrolysis", "catalytic", "biofuel"],
                min_score_threshold=0.7,
                description="Catalytic conversion of biomass to biofuels"
            ),
            DOEQuery(
                query="hydrothermal liquefaction",
                office="BETO",
                category="Bioconversion",
                expected_domains=["biomass", "hydrothermal", "liquefaction", "biofuel"],
                min_score_threshold=0.7,
                description="Hydrothermal processing of biomass"
            ),
            DOEQuery(
                query="biochemical conversion enzymes",
                office="BETO",
                category="Bioconversion",
                expected_domains=["biochemical", "enzyme", "conversion", "biomass"],
                min_score_threshold=0.6,
                description="Enzymatic breakdown of biomass"
            ),
            DOEQuery(
                query="sustainable aviation fuels",
                office="BETO",
                category="Biofuels",
                expected_domains=["aviation", "fuel", "sustainable", "biofuel"],
                min_score_threshold=0.7,
                description="Drop-in biofuels for aviation"
            ),

            # HFTO (Hydrogen and Fuel Cell Technologies Office)
            DOEQuery(
                query="anion exchange membranes",
                office="HFTO",
                category="Fuel Cells",
                expected_domains=["anion", "exchange", "membrane", "fuel", "cell"],
                min_score_threshold=0.8,
                description="AEM for alkaline fuel cells"
            ),
            DOEQuery(
                query="proton exchange membranes",
                office="HFTO",
                category="Fuel Cells",
                expected_domains=["proton", "exchange", "membrane", "fuel", "cell"],
                min_score_threshold=0.8,
                description="PEM for hydrogen fuel cells"
            ),
            DOEQuery(
                query="hydrogen storage materials",
                office="HFTO",
                category="Storage",
                expected_domains=["hydrogen", "storage", "material", "metal", "hydride"],
                min_score_threshold=0.7,
                description="Materials for hydrogen storage"
            ),
            DOEQuery(
                query="electrolysis efficiency",
                office="HFTO",
                category="Electrolysis",
                expected_domains=["electrolysis", "hydrogen", "production", "efficiency"],
                min_score_threshold=0.6,
                description="Electrolyzer efficiency improvements"
            ),

            # Cross-cutting technologies
            DOEQuery(
                query="machine learning materials discovery",
                office="Cross-cutting",
                category="AI/ML",
                expected_domains=["machine", "learning", "material", "discovery", "AI"],
                min_score_threshold=0.6,
                description="AI for accelerated materials development"
            ),
            DOEQuery(
                query="computational fluid dynamics",
                office="Cross-cutting",
                category="Modeling",
                expected_domains=["computational", "fluid", "dynamics", "CFD", "modeling"],
                min_score_threshold=0.6,
                description="CFD simulations for energy systems"
            ),
            DOEQuery(
                query="technoeconomic analysis",
                office="Cross-cutting",
                category="Analysis",
                expected_domains=["technoeconomic", "analysis", "cost", "economic"],
                min_score_threshold=0.5,
                description="Economic analysis of energy technologies"
            ),

            # Challenging queries from client feedback
            DOEQuery(
                query="non-photochemical quenching",
                office="SETO",
                category="Biology",
                expected_domains=["photochemical", "quenching", "photosynthesis", "biology"],
                min_score_threshold=0.6,
                description="Biological energy conversion mechanism"
            )
        ]

    def run_semantic_tests(self) -> Dict[str, Any]:
        """Run semantic search tests and return results"""
        from src.core.search.semantic import semantic_search
        from src.database.pgvector import get_pgvector_manager

        try:
            pgvector_manager = get_pgvector_manager()
        except Exception as e:
            return {"error": f"Failed to initialize vector store: {e}"}

        results = {
            "total_queries": len(self.queries),
            "successful_queries": 0,
            "failed_queries": 0,
            "office_results": {},
            "detailed_results": []
        }

        for query_obj in self.queries:
            try:
                # Run semantic search
                search_results = semantic_search(
                    query_obj.query,
                    pgvector_manager,
                    top_k=5
                )

                if not search_results:
                    results["failed_queries"] += 1
                    result = {
                        "query": query_obj.query,
                        "office": query_obj.office,
                        "status": "failed",
                        "error": "No results returned",
                        "max_score": 0.0
                    }
                else:
                    max_score = max(r["semantic_score"] for r in search_results)
                    top_result = search_results[0]

                    # Check if result meets threshold
                    passed = max_score >= query_obj.min_score_threshold
                    if passed:
                        results["successful_queries"] += 1
                    else:
                        results["failed_queries"] += 1

                    result = {
                        "query": query_obj.query,
                        "office": query_obj.office,
                        "category": query_obj.category,
                        "status": "passed" if passed else "failed",
                        "max_score": max_score,
                        "threshold": query_obj.min_score_threshold,
                        "top_title": top_result["title"][:80],
                        "agency": top_result.get("agency", "Unknown"),
                        "expected_domains": query_obj.expected_domains
                    }

                results["detailed_results"].append(result)

                # Aggregate by office
                office = query_obj.office
                if office not in results["office_results"]:
                    results["office_results"][office] = {
                        "total": 0,
                        "passed": 0,
                        "failed": 0,
                        "avg_score": 0.0,
                        "scores": []
                    }

                results["office_results"][office]["total"] += 1
                results["office_results"][office]["scores"].append(result["max_score"])

                if result["status"] == "passed":
                    results["office_results"][office]["passed"] += 1
                else:
                    results["office_results"][office]["failed"] += 1

            except Exception as e:
                results["failed_queries"] += 1
                result = {
                    "query": query_obj.query,
                    "office": query_obj.office,
                    "status": "error",
                    "error": str(e),
                    "max_score": 0.0
                }
                results["detailed_results"].append(result)

        # Calculate office averages
        for office, office_data in results["office_results"].items():
            if office_data["scores"]:
                office_data["avg_score"] = sum(office_data["scores"]) / len(office_data["scores"])

        return results

    def run_lexical_tests(self) -> Dict[str, Any]:
        """Run lexical search tests to ensure they still work"""
        from src.core.search.lexical import lexical_search
        from src.database.pgvector import get_pgvector_manager

        try:
            pgvector_manager = get_pgvector_manager()
        except Exception as e:
            return {"error": f"Failed to initialize: {e}"}

        # Test lexical search with a few key terms
        test_terms = ["hydrogen", "solar", "biomass", "fuel cell"]

        results = {
            "lexical_tests": []
        }

        for term in test_terms:
            try:
                lexical_results = lexical_search(term, pgvector_manager, top_k=3)
                results["lexical_tests"].append({
                    "term": term,
                    "results_count": len(lexical_results),
                    "status": "passed" if lexical_results else "failed"
                })
            except Exception as e:
                results["lexical_tests"].append({
                    "term": term,
                    "status": "error",
                    "error": str(e)
                })

        return results

    def generate_report(self, semantic_results: Dict, lexical_results: Dict) -> str:
        """Generate comprehensive test report"""

        report = []
        report.append("🔬 DOE SBIR Semantic Search Test Report")
        report.append("=" * 60)
        report.append("")

        if "error" in semantic_results:
            report.append(f"❌ CRITICAL ERROR: {semantic_results['error']}")
            return "\n".join(report)

        # Overall results
        total = semantic_results["total_queries"]
        successful = semantic_results["successful_queries"]
        failed = semantic_results["failed_queries"]
        success_rate = (successful / total * 100) if total > 0 else 0

        report.append("📊 OVERALL RESULTS")
        report.append(f"   Total Queries: {total}")
        report.append(f"   Passed: {successful}")
        report.append(f"   Failed: {failed}")
        report.append(".1f")
        report.append("")

        # Office breakdown
        report.append("🏢 OFFICE BREAKDOWN")
        for office, data in semantic_results["office_results"].items():
            avg_score = data["avg_score"]
            passed = data["passed"]
            total_office = data["total"]
            office_rate = (passed / total_office * 100) if total_office > 0 else 0

            status = "✅" if office_rate >= 80 else "🟡" if office_rate >= 60 else "❌"
            report.append(".1f"
        report.append("")

        # Assessment
        report.append("🎯 ASSESSMENT")
        if success_rate >= 80:
            report.append("✅ EXCELLENT: Semantic search shows high precision for DOE domains")
        elif success_rate >= 60:
            report.append("🟡 GOOD: Acceptable performance, minor issues to address")
        else:
            report.append("❌ CRITICAL: Semantic search fails DOE domain requirements")
            report.append("   Recommendation: Switch to domain-specific embedding model")
        report.append("")

        # Failed queries
        failed_queries = [r for r in semantic_results["detailed_results"] if r["status"] in ["failed", "error"]]
        if failed_queries:
            report.append("❌ FAILED QUERIES")
            for query in failed_queries[:5]:  # Show first 5
                report.append(f"   '{query['query']}' ({query['office']})")
                report.append(".3f"                if "error" in query:
                    report.append(f"     Error: {query['error']}")
                report.append("")
        report.append("")

        # Lexical test results
        if lexical_results and "lexical_tests" in lexical_results:
            report.append("📝 LEXICAL SEARCH VALIDATION")
            for test in lexical_results["lexical_tests"]:
                status = "✅" if test["status"] == "passed" else "❌"
                report.append(f"   {status} '{test['term']}': {test['results_count']} results")
            report.append("")

        return "\n".join(report)

def main():
    """Run the complete DOE test suite"""
    print("Starting DOE SBIR Test Suite...")

    suite = DOETestSuite()

    # Run semantic tests
    print("Running semantic search tests...")
    semantic_results = suite.run_semantic_tests()

    # Run lexical tests
    print("Running lexical search validation...")
    lexical_results = suite.run_lexical_tests()

    # Generate and print report
    report = suite.generate_report(semantic_results, lexical_results)
    print("\n" + report)

    # Save detailed results
    output_file = Path(__file__).parent / "doe_test_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            "semantic_results": semantic_results,
            "lexical_results": lexical_results,
            "timestamp": str(Path(__file__).stat().st_mtime)
        }, f, indent=2)

    print(f"\nDetailed results saved to: {output_file}")

    return semantic_results, lexical_results

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
