"""
Automatic Diagnostic Script for Validation Issues
Runs comprehensive checks to identify why Recall@5 is low
"""
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.pgvector import get_pgvector_manager
from src.database.supabase import get_supabase_client
from src.core.search.semantic import semantic_search
from src.indexing.embeddings import get_embedding_service

logger = get_logger(__name__)


class ValidationDiagnostics:
    """Comprehensive diagnostic checks for validation issues"""
    
    def __init__(self):
        self.results = {}
        self.pgvector_manager = None
        self.supabase = None
        
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all diagnostic checks"""
        print("=" * 80)
        print("VALIDATION DIAGNOSTIC CHECKS")
        print("=" * 80)
        print()
        
        checks = [
            ("Configuration", self.check_configuration),
            ("Database Connectivity", self.check_database_connectivity),
            ("Indexing Completeness", self.check_indexing_completeness),
            ("Embedding Service", self.check_embedding_service),
            ("Basic Semantic Search", self.check_basic_semantic_search),
            ("Sample Query Tests", self.check_sample_queries),
            ("Chunk Quality", self.check_chunk_quality),
            ("Ground Truth Verification", self.check_ground_truth_verification),
        ]
        
        for check_name, check_func in checks:
            print(f"\n{'='*80}")
            print(f"CHECK: {check_name}")
            print('='*80)
            try:
                result = check_func()
                self.results[check_name] = result
                self._print_result(check_name, result)
            except Exception as e:
                error_result = {"status": "ERROR", "error": str(e)}
                self.results[check_name] = error_result
                print(f"❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 80)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 80)
        self._print_summary()
        
        return self.results
    
    def check_configuration(self) -> Dict[str, Any]:
        """Check configuration settings"""
        config_info = {
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "vector_store": settings.VECTOR_STORE,
            "awards_table": settings.AWARDS_TABLE_NAME,
            "chunks_table": settings.AWARD_CHUNKS_TABLE_NAME,
        }
        
        issues = []
        if settings.EMBEDDING_MODEL == "allenai/scibert_scivocab_uncased":
            issues.append("Using SciBERT - may not be optimal for complex conceptual queries")
        if settings.CHUNK_SIZE < 400:
            issues.append(f"Chunk size ({settings.CHUNK_SIZE}) may be too small for context")
        if settings.CHUNK_OVERLAP < 50:
            issues.append(f"Chunk overlap ({settings.CHUNK_OVERLAP}) may be insufficient")
        
        return {
            "status": "OK" if not issues else "WARNING",
            "config": config_info,
            "issues": issues
        }
    
    def check_database_connectivity(self) -> Dict[str, Any]:
        """Check database connectivity"""
        try:
            self.pgvector_manager = get_pgvector_manager()
            conn = self.pgvector_manager._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            cursor.close()
            self.pgvector_manager._put_connection(conn)
            
            self.supabase = get_supabase_client()
            supabase_raw = self.supabase.get_client()
            
            return {
                "status": "OK",
                "postgres_connected": True,
                "postgres_version": version.split(",")[0],
                "supabase_connected": True
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def check_indexing_completeness(self) -> Dict[str, Any]:
        """Check if indexing is complete"""
        try:
            conn = self.pgvector_manager._get_connection()
            cursor = conn.cursor()
            
            # Check chunks table
            cursor.execute(f"SELECT COUNT(*) FROM {settings.AWARD_CHUNKS_TABLE_NAME}")
            total_chunks = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(DISTINCT award_id) FROM {settings.AWARD_CHUNKS_TABLE_NAME}")
            unique_awards = cursor.fetchone()[0]
            
            # Check awards table
            cursor.execute(f"SELECT COUNT(*) FROM {settings.AWARDS_TABLE_NAME}")
            total_awards = cursor.fetchone()[0]
            
            # Check for embeddings (pgvector uses vector type, not array)
            cursor.execute(f"""
                SELECT COUNT(*) 
                FROM {settings.AWARD_CHUNKS_TABLE_NAME} 
                WHERE embedding IS NOT NULL
            """)
            chunks_with_embeddings = cursor.fetchone()[0]
            
            # Check embedding dimension (sample one embedding)
            cursor.execute(f"""
                SELECT embedding::text
                FROM {settings.AWARD_CHUNKS_TABLE_NAME}
                WHERE embedding IS NOT NULL
                LIMIT 1
            """)
            sample_embedding = cursor.fetchone()
            dimensions = []
            if sample_embedding and sample_embedding[0]:
                # Parse vector dimension from text representation
                try:
                    import re
                    vector_text = sample_embedding[0]
                    # Extract dimension from vector text like "[0.1,0.2,...]"
                    dim_match = re.search(r'\[([^\]]+)\]', vector_text)
                    if dim_match:
                        dim = len(dim_match.group(1).split(','))
                        dimensions = [dim]
                except:
                    pass
            
            cursor.close()
            
            issues = []
            if total_chunks == 0:
                issues.append("CRITICAL: No chunks indexed!")
            if unique_awards == 0:
                issues.append("CRITICAL: No awards indexed!")
            if chunks_with_embeddings < total_chunks * 0.9:
                issues.append(f"WARNING: Only {chunks_with_embeddings}/{total_chunks} chunks have embeddings")
            if dimensions and dimensions[0] != settings.EMBEDDING_DIMENSION:
                issues.append(f"WARNING: Embedding dimension mismatch. Expected {settings.EMBEDDING_DIMENSION}, found {dimensions}")
            if unique_awards < total_awards * 0.9:
                issues.append(f"WARNING: Only {unique_awards}/{total_awards} awards have chunks")
            
            return {
                "status": "OK" if not issues else "WARNING",
                "total_chunks": total_chunks,
                "unique_awards_indexed": unique_awards,
                "total_awards": total_awards,
                "chunks_with_embeddings": chunks_with_embeddings,
                "embedding_dimensions_found": dimensions,
                "coverage": unique_awards / total_awards if total_awards > 0 else 0,
                "issues": issues
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def check_embedding_service(self) -> Dict[str, Any]:
        """Check embedding service functionality"""
        try:
            service = get_embedding_service()
            
            # Test embedding generation
            test_texts = [
                "photovoltaic solar cell efficiency",
                "quantum entanglement entropy",
                "hydrogen fuel cell catalyst"
            ]
            
            embeddings = []
            for text in test_texts:
                embedding = service.embed_text(text)
                embeddings.append({
                    "text": text,
                    "dimension": len(embedding),
                    "sample": embedding[:5] if len(embedding) > 5 else embedding
                })
            
            # Check dimension consistency
            dimensions = [e["dimension"] for e in embeddings]
            dimension_consistent = len(set(dimensions)) == 1
            
            issues = []
            if not dimension_consistent:
                issues.append("Embedding dimensions are inconsistent")
            if dimensions[0] != settings.EMBEDDING_DIMENSION:
                issues.append(f"Dimension mismatch: expected {settings.EMBEDDING_DIMENSION}, got {dimensions[0]}")
            
            return {
                "status": "OK" if not issues else "WARNING",
                "service_type": type(service).__name__,
                "test_embeddings": embeddings,
                "dimension_consistent": dimension_consistent,
                "issues": issues
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def check_basic_semantic_search(self) -> Dict[str, Any]:
        """Test basic semantic search functionality"""
        try:
            test_queries = [
                "photovoltaic solar energy",
                "quantum computing",
                "hydrogen fuel cells"
            ]
            
            results = []
            for query in test_queries:
                search_results = semantic_search(
                    query=query,
                    vector_store_client=self.pgvector_manager,
                    top_k=5
                )
                
                results.append({
                    "query": query,
                    "num_results": len(search_results),
                    "top_score": search_results[0]["semantic_score"] if search_results else None,
                    "top_award_id": search_results[0]["award_id"] if search_results else None
                })
            
            issues = []
            if any(r["num_results"] == 0 for r in results):
                issues.append("Some queries returned no results")
            if any(r["top_score"] and r["top_score"] < 0.3 for r in results):
                issues.append("Low similarity scores (< 0.3) - embeddings may not be working well")
            
            return {
                "status": "OK" if not issues else "WARNING",
                "test_results": results,
                "issues": issues
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def check_sample_queries(self) -> Dict[str, Any]:
        """Test with sample validation queries"""
        try:
            # Sample queries from validation report
            sample_queries = [
                {
                    "query": "What role do localized thermal gradients play in modulating the photocatalytic activity",
                    "expected_award": "DE-SC0025804"
                },
                {
                    "query": "How do the characteristics of entanglement entropy growth in quantum approximate optimization",
                    "expected_award": "DE-SC0024163"
                },
                {
                    "query": "What strategies can be implemented to foster a culture of innovation",
                    "expected_award": "DE-SC0025722"
                }
            ]
            
            results = []
            for test_case in sample_queries:
                query = test_case["query"]
                expected_award = test_case["expected_award"]
                
                search_results = semantic_search(
                    query=query,
                    vector_store_client=self.pgvector_manager,
                    top_k=20  # Check top 20 to see if it appears later
                )
                
                award_ids = [r["award_id"] for r in search_results]
                rank = award_ids.index(expected_award) + 1 if expected_award in award_ids else None
                
                results.append({
                    "query": query[:60] + "...",
                    "expected_award": expected_award,
                    "found": expected_award in award_ids,
                    "rank": rank,
                    "top_5_awards": award_ids[:5],
                    "top_score": search_results[0]["semantic_score"] if search_results else None
                })
            
            found_count = sum(1 for r in results if r["found"])
            issues = []
            if found_count == 0:
                issues.append("CRITICAL: None of the sample queries found expected awards even in top 20")
            elif found_count < len(results):
                issues.append(f"Only {found_count}/{len(results)} sample queries found expected awards")
            
            return {
                "status": "OK" if found_count == len(results) else "WARNING",
                "sample_results": results,
                "found_count": found_count,
                "total_samples": len(results),
                "issues": issues
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def check_chunk_quality(self) -> Dict[str, Any]:
        """Check chunk quality and content"""
        try:
            conn = self.pgvector_manager._get_connection()
            cursor = conn.cursor()
            
            # Sample chunks
            cursor.execute(f"""
                SELECT award_id, chunk_text, chunk_index, field_name
                FROM {settings.AWARD_CHUNKS_TABLE_NAME}
                WHERE chunk_text IS NOT NULL
                LIMIT 10
            """)
            
            sample_chunks = []
            for row in cursor.fetchall():
                award_id, chunk_text, chunk_index, field_name = row
                sample_chunks.append({
                    "award_id": award_id,
                    "chunk_length": len(chunk_text),
                    "chunk_index": chunk_index,
                    "field_name": field_name,
                    "preview": chunk_text[:100] + "..." if len(chunk_text) > 100 else chunk_text
                })
            
            # Check average chunk length
            cursor.execute(f"""
                SELECT AVG(LENGTH(chunk_text)) as avg_length,
                       MIN(LENGTH(chunk_text)) as min_length,
                       MAX(LENGTH(chunk_text)) as max_length
                FROM {settings.AWARD_CHUNKS_TABLE_NAME}
                WHERE chunk_text IS NOT NULL
            """)
            stats = cursor.fetchone()
            
            cursor.close()
            
            issues = []
            if stats[0] and stats[0] < 100:
                issues.append(f"Average chunk length ({stats[0]:.0f}) is very short")
            if stats[1] and stats[1] < 20:
                issues.append(f"Some chunks are very short (min: {stats[1]})")
            
            return {
                "status": "OK" if not issues else "WARNING",
                "sample_chunks": sample_chunks[:5],
                "statistics": {
                    "avg_length": stats[0],
                    "min_length": stats[1],
                    "max_length": stats[2]
                },
                "issues": issues
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def check_ground_truth_verification(self) -> Dict[str, Any]:
        """Verify ground truth awards exist and have content"""
        try:
            # Awards from validation report that failed
            test_awards = [
                "DE-SC0025804",
                "DE-SC0025742",
                "DE-SC0025727",
                "DE-SC0025722",
                "DE-SC0025701",
                "DE-SC0024163"
            ]
            
            supabase_raw = self.supabase.get_client()
            awards_table = settings.AWARDS_TABLE_NAME
            
            verification_results = []
            for award_id in test_awards:
                try:
                    response = supabase_raw.table(awards_table).select(
                        "award_id, title, public_abstract"
                    ).eq("award_id", award_id).execute()
                    
                    if response.data:
                        award = response.data[0]
                        abstract = award.get("public_abstract") or ""
                        has_chunks = False
                        
                        # Check if chunks exist
                        conn = self.pgvector_manager._get_connection()
                        cursor = conn.cursor()
                        cursor.execute(f"""
                            SELECT COUNT(*) 
                            FROM {settings.AWARD_CHUNKS_TABLE_NAME}
                            WHERE award_id = %s
                        """, (award_id,))
                        chunk_count = cursor.fetchone()[0]
                        cursor.close()
                        self.pgvector_manager._put_connection(conn)
                        
                        verification_results.append({
                            "award_id": award_id,
                            "exists": True,
                            "title": award.get("title", "")[:60],
                            "abstract_length": len(abstract),
                            "chunk_count": chunk_count,
                            "has_content": len(abstract) > 100,
                            "has_chunks": chunk_count > 0
                        })
                    else:
                        verification_results.append({
                            "award_id": award_id,
                            "exists": False
                        })
                except Exception as e:
                    verification_results.append({
                        "award_id": award_id,
                        "error": str(e)
                    })
            
            issues = []
            missing_awards = [r for r in verification_results if not r.get("exists")]
            awards_without_chunks = [r for r in verification_results if r.get("exists") and not r.get("has_chunks")]
            
            if missing_awards:
                issues.append(f"{len(missing_awards)} test awards not found in database")
            if awards_without_chunks:
                issues.append(f"{len(awards_without_chunks)} test awards have no chunks")
            
            return {
                "status": "OK" if not issues else "WARNING",
                "verification_results": verification_results,
                "issues": issues
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }
    
    def _print_result(self, check_name: str, result: Dict[str, Any]):
        """Print formatted result"""
        status = result.get("status", "UNKNOWN")
        status_icon = "✅" if status == "OK" else "⚠️" if status == "WARNING" else "❌"
        
        print(f"{status_icon} Status: {status}")
        
        if "issues" in result and result["issues"]:
            print("\nIssues Found:")
            for issue in result["issues"]:
                print(f"  • {issue}")
        
        # Print key metrics
        if "total_chunks" in result:
            print(f"\nMetrics:")
            print(f"  • Total chunks: {result['total_chunks']}")
            print(f"  • Unique awards indexed: {result['unique_awards_indexed']}")
            print(f"  • Coverage: {result.get('coverage', 0):.1%}")
        
        if "test_results" in result:
            print(f"\nTest Results:")
            for test in result["test_results"]:
                print(f"  • Query: '{test['query']}'")
                print(f"    Results: {test['num_results']}, Top Score: {test.get('top_score', 'N/A')}")
    
    def _print_summary(self):
        """Print diagnostic summary"""
        critical_issues = []
        warnings = []
        
        for check_name, result in self.results.items():
            status = result.get("status", "UNKNOWN")
            if status == "ERROR":
                critical_issues.append(f"{check_name}: {result.get('error', 'Unknown error')}")
            elif status == "WARNING":
                warnings.append(f"{check_name}: {len(result.get('issues', []))} issues")
        
        if critical_issues:
            print("\n❌ CRITICAL ISSUES:")
            for issue in critical_issues:
                print(f"  • {issue}")
        
        if warnings:
            print("\n⚠️  WARNINGS:")
            for warning in warnings:
                print(f"  • {warning}")
        
        if not critical_issues and not warnings:
            print("\n✅ All checks passed! System appears to be configured correctly.")
            print("\n💡 If Recall@5 is still low, consider:")
            print("  1. Switching to a different embedding model")
            print("  2. Increasing chunk size and overlap")
            print("  3. Re-indexing with --fresh flag")
            print("  4. Testing with simpler queries first")


def main():
    """Run diagnostic checks"""
    diagnostics = ValidationDiagnostics()
    results = diagnostics.run_all_checks()
    
    # Save results to JSON
    import json
    output_file = Path(__file__).parent / "diagnostic_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n📄 Full results saved to: {output_file}")


if __name__ == "__main__":
    main()

