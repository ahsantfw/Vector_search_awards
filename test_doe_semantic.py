#!/usr/bin/env python3
"""
DOE Semantic Search Validation Test
Tests semantic search with DOE-specific technical queries
"""
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import settings
from src.database.pgvector import get_pgvector_manager
from src.core.search.semantic import semantic_search_pgvector
from src.core.search.lexical import lexical_search_pgvector
from src.core.search.hybrid_search import hybrid_search

# DOE-specific test queries by office
DOE_TEST_QUERIES = {
    "SETO": [
        "perovskite photovoltaics",
        "quantum dot solar cells",
        "transparent conducting oxides",
        "tandem solar cells",
        "photovoltaic efficiency"
    ],
    "BETO": [
        "sustainable aviation fuels",
        "biomass conversion",
        "catalytic fast pyrolysis",
        "hydrothermal liquefaction",
        "biochemical conversion"
    ],
    "HFTO": [
        "anion exchange membranes",
        "proton exchange membranes",
        "hydrogen storage",
        "electrolysis",
        "fuel cells"
    ],
    "Cross-cutting": [
        "machine learning materials discovery",
        "computational fluid dynamics",
        "scale-up manufacturing",
        "technoeconomic analysis"
    ]
}

def test_semantic_search(query, top_k=5):
    """Test semantic search for a query"""
    try:
        pgvector_manager = get_pgvector_manager()
        results = semantic_search_pgvector(query, pgvector_manager, top_k=top_k)

        if not results:
            return {"query": query, "results": [], "error": "No results"}

        # Analyze results
        scores = [r["semantic_score"] for r in results]
        agencies = [r.get("agency", "Unknown") for r in results]

        return {
            "query": query,
            "results": results,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "agencies": agencies,
            "score_distribution": {
                "high": len([s for s in scores if s > 0.7]),
                "medium": len([s for s in scores if 0.4 <= s <= 0.7]),
                "low": len([s for s in scores if s < 0.4])
            }
        }
    except Exception as e:
        return {"query": query, "results": [], "error": str(e)}

def run_doe_validation():
    """Run comprehensive DOE semantic search validation"""
    print("🔬 DOE Semantic Search Validation Test")
    print("=" * 60)
    print(f"Embedding Model: {settings.EMBEDDING_MODEL}")
    print(f"Chunk Size: {settings.CHUNK_SIZE} tokens")
    print(f"Chunk Overlap: {settings.CHUNK_OVERLAP} tokens")
    print()

    results_summary = {
        "total_queries": 0,
        "successful_queries": 0,
        "failed_queries": 0,
        "avg_max_score": 0,
        "high_score_queries": 0,  # max score > 0.7
        "domain_accuracy": {},  # office -> accuracy score
        "results": []
    }

    all_max_scores = []

    for office, queries in DOE_TEST_QUERIES.items():
        print(f"🏢 Testing {office} ({len(queries)} queries)")
        print("-" * 40)

        office_results = []
        office_max_scores = []

        for query in queries:
            print(f"Query: '{query}'")
            result = test_semantic_search(query)

            if result.get("error"):
                print(f"  ❌ Error: {result['error']}")
                results_summary["failed_queries"] += 1
            else:
                max_score = result["max_score"]
                avg_score = result["avg_score"]
                office_max_scores.append(max_score)
                all_max_scores.append(max_score)

                # Show top result
                if result["results"]:
                    top_result = result["results"][0]
                    agency = top_result.get("agency", "Unknown")
                    title = top_result["title"][:60] + "..." if len(top_result["title"]) > 60 else top_result["title"]
                    print(f"  ✅ Max Score: {max_score:.3f}, Avg: {avg_score:.3f}")
                    print(f"     Agency: {agency}, Title: {title}")

                    if max_score > 0.7:
                        results_summary["high_score_queries"] += 1
                else:
                    print("  ⚠️  No results found"
            print()
            results_summary["total_queries"] += 1
            office_results.append(result)

        # Office summary
        if office_max_scores:
            office_avg = sum(office_max_scores) / len(office_max_scores)
            office_high = len([s for s in office_max_scores if s > 0.7])
            results_summary["domain_accuracy"][office] = {
                "avg_max_score": office_avg,
                "high_score_ratio": office_high / len(office_max_scores)
            }
            print(f"{office} Summary: Avg Max Score = {office_avg:.3f}, High Scores = {office_high}/{len(queries)}")
        print()

    # Overall summary
    print("📊 OVERALL RESULTS")
    print("=" * 60)

    if all_max_scores:
        overall_avg = sum(all_max_scores) / len(all_max_scores)
        high_score_ratio = results_summary["high_score_queries"] / results_summary["total_queries"]

        print(f"Total Queries: {results_summary['total_queries']}")
        print(f"Successful: {results_summary['total_queries'] - results_summary['failed_queries']}")
        print(f"Failed: {results_summary['failed_queries']}")
        print(".3f"        print(".1%")
        print()

        print("Domain Performance:")
        for office, metrics in results_summary["domain_accuracy"].items():
            print(".3f"                  ".1%")

        # Assessment
        print()
        print("🎯 ASSESSMENT:")
        if high_score_ratio > 0.8:
            print("✅ EXCELLENT: High semantic precision (>80% queries with good matches)")
        elif high_score_ratio > 0.6:
            print("🟡 GOOD: Acceptable semantic precision (60-80% queries with good matches)")
        elif high_score_ratio > 0.4:
            print("🟠 FAIR: Moderate semantic precision (40-60% queries with good matches)")
        else:
            print("❌ POOR: Low semantic precision (<40% queries with good matches)")
            print("   Recommendation: Switch to domain-specific embedding model")

    return results_summary

def compare_lexical_vs_semantic():
    """Compare lexical vs semantic search for DOE queries"""
    print("\n🔍 LEXICAL vs SEMANTIC COMPARISON")
    print("=" * 60)

    test_queries = [
        "perovskite photovoltaics",
        "anion exchange membranes",
        "sustainable aviation fuels"
    ]

    try:
        pgvector_manager = get_pgvector_manager()

        for query in test_queries:
            print(f"Query: '{query}'")
            print("-" * 30)

            # Lexical search
            lexical_results = lexical_search_pgvector(query, pgvector_manager, top_k=3)
            if lexical_results:
                print("📝 LEXICAL (exact matches):")
                for i, result in enumerate(lexical_results[:2], 1):
                    title = result["title"][:50] + "..." if len(result["title"]) > 50 else result["title"]
                    print(".3f")
            else:
                print("📝 LEXICAL: No results")

            # Semantic search
            semantic_results = semantic_search_pgvector(query, pgvector_manager, top_k=3)
            if semantic_results:
                print("🧠 SEMANTIC (conceptual matches):")
                for i, result in enumerate(semantic_results[:2], 1):
                    title = result["title"][:50] + "..." if len(result["title"]) > 50 else result["title"]
                    print(".3f")
            else:
                print("🧠 SEMANTIC: No results")

            print()
    except Exception as e:
        print(f"❌ Comparison failed: {e}")

if __name__ == "__main__":
    try:
        # Run validation
        results = run_doe_validation()

        # Run comparison
        compare_lexical_vs_semantic()

        print("\n✅ DOE Semantic Search Validation Complete")

    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
