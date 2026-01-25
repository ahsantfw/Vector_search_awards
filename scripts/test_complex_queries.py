"""
Test Complex Queries with Ground Truth
5 complex conceptual queries to test semantic search performance
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.pgvector import get_pgvector_manager
from src.core.search.semantic import semantic_search

logger = get_logger(__name__)


# 5 Complex Queries with Ground Truth
COMPLEX_TEST_QUERIES = [
    {
        "query": "What methodologies can be employed to enhance the efficiency of photocatalytic processes through optimization of thermal gradients and plasmonic nanoparticle interactions?",
        "ground_truth_award_id": "DE-SC0025804",
        "description": "Complex query about photocatalysis, thermal gradients, and plasmonic nanoparticles",
        "domain": "SETO (Solar Energy)"
    },
    {
        "query": "How do quantum entanglement properties and entropy growth characteristics relate to computational optimization algorithms in many-body systems?",
        "ground_truth_award_id": "DE-SC0024163",
        "description": "Complex query about quantum entanglement, entropy, and optimization",
        "domain": "Cross-cutting (Quantum Computing)"
    },
    {
        "query": "What strategies can be implemented to foster interdisciplinary collaboration and innovation culture in academic research environments?",
        "ground_truth_award_id": "DE-SC0025722",
        "description": "Complex query about innovation culture and academic collaboration",
        "domain": "Cross-cutting (Education/Research)"
    },
    {
        "query": "How do microstructural characteristics and defect chemistry influence the performance of electrochemical ion separation systems in disordered materials?",
        "ground_truth_award_id": "DE-SC0025701",
        "description": "Complex query about electrochemical systems and material microstructure",
        "domain": "HFTO (Hydrogen/Electrochemistry)"
    },
    {
        "query": "What role do nanostructured metal clusters and supporting substrate interactions play in determining the stability and activity of electrocatalytic systems?",
        "ground_truth_award_id": "DE-SC0024716",
        "description": "Complex query about electrocatalysis and nanostructured materials",
        "domain": "HFTO (Hydrogen/Electrochemistry)"
    }
]


def test_complex_queries(top_k: int = 20):
    """Test complex queries and check if ground truth appears in results"""
    print("=" * 80)
    print("COMPLEX QUERY VALIDATION TEST")
    print("=" * 80)
    print(f"Model: {settings.EMBEDDING_MODEL}")
    print(f"Chunk Size: {settings.CHUNK_SIZE} tokens")
    print(f"Chunk Overlap: {settings.CHUNK_OVERLAP} tokens")
    print(f"Checking top {top_k} results for each query")
    print()
    
    pgvector_manager = get_pgvector_manager()
    
    results_summary = {
        "total_queries": len(COMPLEX_TEST_QUERIES),
        "found_in_top_5": 0,
        "found_in_top_10": 0,
        "found_in_top_20": 0,
        "not_found": 0,
        "results": []
    }
    
    for idx, test_case in enumerate(COMPLEX_TEST_QUERIES, 1):
        query = test_case["query"]
        ground_truth_id = test_case["ground_truth_award_id"]
        description = test_case["description"]
        domain = test_case["domain"]
        
        print(f"{'='*80}")
        print(f"QUERY {idx}/5: {domain}")
        print(f"{'='*80}")
        print(f"Query: {query}")
        print(f"Ground Truth: {ground_truth_id}")
        print(f"Description: {description}")
        print()
        
        try:
            # Run semantic search
            search_results = semantic_search(
                query=query,
                vector_store_client=pgvector_manager,
                top_k=top_k
            )
            
            # Deduplicate by award_id (keep best score)
            seen_awards = {}
            for result in search_results:
                award_id = result["award_id"]
                if award_id not in seen_awards or result["semantic_score"] > seen_awards[award_id]["semantic_score"]:
                    seen_awards[award_id] = result
            
            deduplicated_results = list(seen_awards.values())[:top_k]
            award_ids = [r["award_id"] for r in deduplicated_results]
            
            # Check if ground truth is in results
            rank = None
            if ground_truth_id in award_ids:
                rank = award_ids.index(ground_truth_id) + 1  # 1-indexed
            
            # Status
            if rank and rank <= 5:
                status = "✅ FOUND (Top 5)"
                results_summary["found_in_top_5"] += 1
                results_summary["found_in_top_10"] += 1
                results_summary["found_in_top_20"] += 1
            elif rank and rank <= 10:
                status = "🟡 FOUND (Top 10)"
                results_summary["found_in_top_10"] += 1
                results_summary["found_in_top_20"] += 1
            elif rank and rank <= 20:
                status = "🟠 FOUND (Top 20)"
                results_summary["found_in_top_20"] += 1
            else:
                status = "❌ NOT FOUND"
                results_summary["not_found"] += 1
            
            print(f"Status: {status}")
            if rank:
                print(f"Rank: {rank}")
                print(f"Score: {deduplicated_results[rank-1]['semantic_score']:.4f}")
            else:
                print("Rank: Not found in top 20")
            
            print(f"\nTop 5 Results:")
            for i, result in enumerate(deduplicated_results[:5], 1):
                marker = " 👈 GROUND TRUTH" if result["award_id"] == ground_truth_id else ""
                print(f"  {i}. {result['award_id']}: {result.get('title', '')[:60]}... (Score: {result['semantic_score']:.4f}){marker}")
            
            results_summary["results"].append({
                "query": query,
                "ground_truth": ground_truth_id,
                "domain": domain,
                "rank": rank,
                "found": rank is not None,
                "top_score": deduplicated_results[0]["semantic_score"] if deduplicated_results else None,
                "ground_truth_score": deduplicated_results[rank-1]["semantic_score"] if rank else None
            })
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results_summary["results"].append({
                "query": query,
                "ground_truth": ground_truth_id,
                "error": str(e)
            })
        
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Queries: {results_summary['total_queries']}")
    print(f"✅ Found in Top 5: {results_summary['found_in_top_5']}/{results_summary['total_queries']} ({results_summary['found_in_top_5']/results_summary['total_queries']*100:.1f}%)")
    print(f"🟡 Found in Top 10: {results_summary['found_in_top_10']}/{results_summary['total_queries']} ({results_summary['found_in_top_10']/results_summary['total_queries']*100:.1f}%)")
    print(f"🟠 Found in Top 20: {results_summary['found_in_top_20']}/{results_summary['total_queries']} ({results_summary['found_in_top_20']/results_summary['total_queries']*100:.1f}%)")
    print(f"❌ Not Found: {results_summary['not_found']}/{results_summary['total_queries']} ({results_summary['not_found']/results_summary['total_queries']*100:.1f}%)")
    print()
    
    # Recall@5 calculation
    recall_at_5 = results_summary['found_in_top_5'] / results_summary['total_queries']
    print(f"Recall@5: {recall_at_5:.2%}")
    if recall_at_5 >= 0.70:
        print("✅ PASS: Recall@5 >= 70%")
    else:
        print("❌ FAIL: Recall@5 < 70%")
    
    return results_summary


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test complex queries with ground truth")
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of results to retrieve (default: 20)"
    )
    
    args = parser.parse_args()
    
    test_complex_queries(top_k=args.top_k)

