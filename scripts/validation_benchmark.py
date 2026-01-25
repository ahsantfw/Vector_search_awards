"""
Synthetic Query Generation and Retrieval Benchmarking
Implements Ground Truth methodology for vector database validation

This script:
1. Generates synthetic technical queries using LLM (5 per paragraph)
2. Runs semantic-only retrieval tests
3. Calculates Recall@5 and MRR metrics
4. Generates comprehensive validation report
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import statistics

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.database.pgvector import get_pgvector_manager
from src.core.search.semantic import semantic_search
from src.core.search.hybrid_search import hybrid_search
from src.core.search.lexical import lexical_search_supabase

logger = get_logger(__name__)


class ValidationBenchmark:
    """Comprehensive validation benchmark for vector database"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
        self.pgvector_manager = get_pgvector_manager()
        self.results = []
        self.ground_truth = []
        
    def generate_synthetic_queries(
        self, 
        awards: List[Dict], 
        num_awards: int = 20,
        queries_per_paragraph: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Generate synthetic technical queries using LLM analysis
        
        Args:
            awards: List of award dictionaries
            num_awards: Number of awards to sample for query generation
            queries_per_paragraph: Number of queries to generate per paragraph
            
        Returns:
            List of query dictionaries with ground truth award_id
        """
        logger.info(f"Generating synthetic queries from {num_awards} awards...")
        
        # Sample awards with good technical content
        sampled_awards = []
        for award in awards:
            abstract = award.get("public_abstract") or award.get("abstract", "")
            if abstract and len(abstract.strip()) > 200:  # Only awards with substantial content
                sampled_awards.append(award)
                if len(sampled_awards) >= num_awards:
                    break
        
        if not sampled_awards:
            logger.error("No awards with sufficient content found for query generation")
            return []
        
        synthetic_queries = []
        
        # Check if Groq API key is available
        if not settings.GROQ_API_KEY:
            logger.error("GROQ_API_KEY not configured. Please set GROQ_API_KEY in .env file")
            raise ValueError("GROQ_API_KEY is required for query generation")
        
        for award in sampled_awards:
            award_id = award.get("award_id", "")
            title = award.get("title", "")
            abstract = award.get("public_abstract") or award.get("abstract", "")
            
            if not abstract or len(abstract.strip()) < 200:
                continue
            
            # Split abstract into paragraphs
            paragraphs = [p.strip() for p in abstract.split("\n\n") if len(p.strip()) > 100]
            
            for para_idx, paragraph in enumerate(paragraphs[:3]):  # Max 3 paragraphs per award
                try:
                    queries = self._generate_queries_with_groq(paragraph, title)
                    
                    if not queries:
                        logger.warning(f"No queries generated for award {award_id}, paragraph {para_idx + 1}")
                        continue
                    
                    for query in queries[:queries_per_paragraph]:
                        synthetic_queries.append({
                            "query": query,
                            "ground_truth_award_id": award_id,
                            "ground_truth_title": title,
                            "source_paragraph": paragraph[:200] + "...",
                            "query_type": "synthetic_technical"
                        })
                except Exception as e:
                    logger.error(f"Failed to generate queries for award {award_id}, paragraph {para_idx + 1}: {e}")
                    # Skip this paragraph, continue with next
                    continue
        
        logger.info(f"Generated {len(synthetic_queries)} synthetic queries")
        return synthetic_queries
    
    def _generate_queries_with_groq(self, paragraph: str, title: str) -> List[str]:
        """Generate queries using Groq API (latest model) - NO FALLBACK"""
        from groq import Groq
        
        # Initialize Groq client
        client = Groq(api_key=settings.GROQ_API_KEY)
        
        prompt = f"""You are a technical expert analyzing DOE research abstracts. 
Given the following research paragraph, generate 5 highly technical, conceptual questions that:
1. Test semantic understanding (not keyword matching)
2. Use synonyms and related concepts (avoid exact words from the text)
3. Are specific to the technical domain (SETO, BETO, HFTO, etc.)
4. Require conceptual mapping to answer correctly

Research Title: {title}
Paragraph: {paragraph}

Generate exactly 5 questions, one per line, without numbering or bullets:"""
        
        # Generate content with Groq
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a technical query generation expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        queries_text = response.choices[0].message.content.strip()
        queries = [q.strip() for q in queries_text.split("\n") if q.strip() and len(q.strip()) > 20]
        
        # Clean up queries (remove numbering, bullets, etc.)
        cleaned_queries = []
        for q in queries:
            # Remove leading numbers, bullets, dashes
            q = q.lstrip("0123456789.-) ").strip()
            if q and len(q) > 20:
                cleaned_queries.append(q)
        
        return cleaned_queries[:5]
    
    async def run_retrieval_benchmark(
        self,
        queries: List[Dict[str, Any]],
        top_k: int = 5,
        semantic_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Run retrieval benchmark on synthetic queries
        
        Args:
            queries: List of query dictionaries
            top_k: Number of results to retrieve
            semantic_only: If True, use only semantic search (alpha=1.0, beta=0.0)
            
        Returns:
            List of benchmark results
        """
        logger.info(f"Running retrieval benchmark on {len(queries)} queries...")
        
        benchmark_results = []
        
        for idx, query_data in enumerate(queries):
            query = query_data["query"]
            ground_truth_id = query_data["ground_truth_award_id"]
            
            try:
                if semantic_only:
                    # Pure semantic search (alpha=1.0, beta=0.0)
                    semantic_results = semantic_search(
                        query=query,
                        vector_store_client=self.pgvector_manager,
                        top_k=top_k * 2  # Get more results for better recall
                    )
                    
                    # Deduplicate by award_id (keep best score)
                    seen_awards = {}
                    for result in semantic_results:
                        award_id = result["award_id"]
                        if award_id not in seen_awards or result["semantic_score"] > seen_awards[award_id]["semantic_score"]:
                            seen_awards[award_id] = result
                    
                    results = list(seen_awards.values())[:top_k]
                    
                else:
                    # Hybrid search
                    lexical_results = lexical_search_supabase(query, top_k=top_k * 2)
                    semantic_results = semantic_search(
                        query=query,
                        vector_store_client=self.pgvector_manager,
                        top_k=top_k * 2
                    )
                    
                    results = hybrid_search(
                        query=query,
                        lexical_results=lexical_results,
                        semantic_results=semantic_results,
                        alpha=1.0,
                        beta=0.0,  # Semantic only
                        top_k=top_k
                    )
                
                # Check if ground truth is in results
                result_award_ids = [r["award_id"] for r in results]
                ground_truth_rank = None
                if ground_truth_id in result_award_ids:
                    ground_truth_rank = result_award_ids.index(ground_truth_id) + 1  # 1-indexed
                
                benchmark_results.append({
                    "query": query,
                    "ground_truth_award_id": ground_truth_id,
                    "ground_truth_title": query_data.get("ground_truth_title", ""),
                    "results": results,
                    "ground_truth_rank": ground_truth_rank,
                    "recall_at_5": 1.0 if ground_truth_rank and ground_truth_rank <= 5 else 0.0,
                    "mrr": 1.0 / ground_truth_rank if ground_truth_rank else 0.0,
                    "num_results": len(results)
                })
                
                if (idx + 1) % 10 == 0:
                    logger.info(f"Processed {idx + 1}/{len(queries)} queries...")
                    
            except Exception as e:
                logger.error(f"Error processing query '{query}': {e}")
                benchmark_results.append({
                    "query": query,
                    "ground_truth_award_id": ground_truth_id,
                    "error": str(e),
                    "recall_at_5": 0.0,
                    "mrr": 0.0
                })
        
        self.results = benchmark_results
        return benchmark_results
    
    def calculate_metrics(self) -> Dict[str, float]:
        """Calculate overall performance metrics"""
        if not self.results:
            return {}
        
        recalls = [r["recall_at_5"] for r in self.results if "recall_at_5" in r]
        mrrs = [r["mrr"] for r in self.results if "mrr" in r and r["mrr"] > 0]
        
        metrics = {
            "total_queries": len(self.results),
            "recall_at_5": statistics.mean(recalls) if recalls else 0.0,
            "recall_at_5_std": statistics.stdev(recalls) if len(recalls) > 1 else 0.0,
            "mrr": statistics.mean(mrrs) if mrrs else 0.0,
            "mrr_std": statistics.stdev(mrrs) if len(mrrs) > 1 else 0.0,
            "queries_with_recall": sum(recalls),
            "queries_with_mrr": len(mrrs)
        }
        
        return metrics
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate comprehensive validation report"""
        metrics = self.calculate_metrics()
        
        report_lines = [
            "=" * 80,
            "VECTOR DATABASE VALIDATION REPORT",
            "Ground Truth Methodology - Synthetic Query Evaluation",
            "=" * 80,
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Model: {settings.EMBEDDING_MODEL} ({settings.EMBEDDING_PROVIDER})",
            f"Vector Store: {settings.VECTOR_STORE}",
            f"Chunk Size: {settings.CHUNK_SIZE} tokens",
            f"Chunk Overlap: {settings.CHUNK_OVERLAP} tokens",
            "",
            "=" * 80,
            "PERFORMANCE METRICS",
            "=" * 80,
            "",
            f"Total Queries: {metrics.get('total_queries', 0)}",
            f"Recall@5: {metrics.get('recall_at_5', 0.0):.3f} ± {metrics.get('recall_at_5_std', 0.0):.3f}",
            f"MRR (Mean Reciprocal Rank): {metrics.get('mrr', 0.0):.3f} ± {metrics.get('mrr_std', 0.0):.3f}",
            f"Queries with Recall@5: {metrics.get('queries_with_recall', 0)}/{metrics.get('total_queries', 0)}",
            f"Queries with MRR: {metrics.get('queries_with_mrr', 0)}/{metrics.get('total_queries', 0)}",
            "",
            "=" * 80,
            "VALIDATION THRESHOLD",
            "=" * 80,
            "",
        ]
        
        recall_threshold = 0.70
        recall_achieved = metrics.get('recall_at_5', 0.0)
        
        if recall_achieved >= recall_threshold:
            report_lines.append(f"✅ PASS: Recall@5 = {recall_achieved:.3f} >= {recall_threshold} (Threshold)")
        else:
            report_lines.append(f"❌ FAIL: Recall@5 = {recall_achieved:.3f} < {recall_threshold} (Threshold)")
        
        report_lines.extend([
            "",
            "=" * 80,
            "QUERY-BY-QUERY RESULTS",
            "=" * 80,
            "",
        ])
        
        # Add detailed results
        for idx, result in enumerate(self.results[:50], 1):  # Show first 50
            query = result.get("query", "")
            gt_id = result.get("ground_truth_award_id", "")
            rank = result.get("ground_truth_rank")
            recall = result.get("recall_at_5", 0.0)
            mrr = result.get("mrr", 0.0)
            
            status = "✅" if recall > 0 else "❌"
            report_lines.append(
                f"{idx}. {status} Query: {query[:80]}..."
            )
            report_lines.append(
                f"   Ground Truth: {gt_id} | Rank: {rank if rank else 'Not Found'} | "
                f"Recall@5: {recall:.2f} | MRR: {mrr:.3f}"
            )
            report_lines.append("")
        
        report = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, "w") as f:
                f.write(report)
            logger.info(f"Report saved to {output_file}")
        
        return report


async def main():
    """Main validation benchmark execution"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run synthetic query validation benchmark"
    )
    parser.add_argument(
        "--num-awards",
        type=int,
        default=20,
        help="Number of awards to sample for query generation (default: 20)"
    )
    parser.add_argument(
        "--queries-per-award",
        type=int,
        default=5,
        help="Number of queries per award paragraph (default: 5)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top K results to retrieve (default: 5)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="validation_report.txt",
        help="Output file for validation report (default: validation_report.txt)"
    )
    parser.add_argument(
        "--semantic-only",
        action="store_true",
        default=True,
        help="Use semantic-only search (default: True)"
    )
    
    args = parser.parse_args()
    
    logger.info("Starting validation benchmark...")
    
    # Initialize benchmark
    benchmark = ValidationBenchmark()
    
    # Fetch awards from Supabase
    logger.info("Fetching awards from Supabase...")
    supabase_raw = benchmark.supabase.get_client()
    awards_table = settings.AWARDS_TABLE_NAME
    
    try:
        response = supabase_raw.table(awards_table).select("*").limit(1000).execute()
        awards = response.data
        logger.info(f"Fetched {len(awards)} awards")
    except Exception as e:
        logger.error(f"Failed to fetch awards: {e}")
        sys.exit(1)
    
    # Generate synthetic queries
    queries = benchmark.generate_synthetic_queries(
        awards=awards,
        num_awards=args.num_awards,
        queries_per_paragraph=args.queries_per_award
    )
    
    if not queries:
        logger.error("No queries generated. Exiting.")
        sys.exit(1)
    
    # Run benchmark
    await benchmark.run_retrieval_benchmark(
        queries=queries,
        top_k=args.top_k,
        semantic_only=args.semantic_only
    )
    
    # Calculate metrics
    metrics = benchmark.calculate_metrics()
    logger.info(f"Metrics: {metrics}")
    
    # Generate report
    report = benchmark.generate_report(output_file=args.output)
    print("\n" + report)
    
    # Save JSON results
    json_output = args.output.replace(".txt", ".json")
    with open(json_output, "w") as f:
        json.dump({
            "metrics": metrics,
            "results": benchmark.results,
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)
    logger.info(f"JSON results saved to {json_output}")


if __name__ == "__main__":
    asyncio.run(main())

