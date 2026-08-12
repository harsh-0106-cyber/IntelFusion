"""
app.py — IntelFusion OSINT Engine
Flask REST API with Server-Sent Events (SSE) streaming for real-time results delivery.
"""

import os
import json
import time
import logging
import threading
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from osint.query_parser import QueryParser
from osint.search_engine import SearchEngine
from osint.social_prober import SocialProber
from osint.image_harvester import ImageHarvester
from osint.entity_resolver import EntityResolver
from osint.people_rank import PeopleRanker
from osint.account_linker import AccountLinker
from osint.research_finder import ResearchFinder
from osint.comments_finder import CommentsFinder
from osint.visual_intel import VisualIntel

# ── Setup ────────────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Flask App ─────────────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Module instances ──────────────────────────────────────────────────────────
parser = QueryParser()
searcher = SearchEngine()
social_prober = SocialProber()
image_harvester = ImageHarvester()
entity_resolver = EntityResolver()
people_ranker = PeopleRanker()
account_linker = AccountLinker()
research_finder = ResearchFinder()
comments_finder = CommentsFinder()
visual_intel = VisualIntel()


# ── Helper: SSE event formatter ───────────────────────────────────────────────
def sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Events message."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the frontend SPA."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/search")
def search():
    """
    SSE streaming endpoint. Accepts:
      ?q=<name + optional keywords>

    Emits events:
      start      → query parsed, search begins
      progress   → each stage completion (search, social, images, resolve, rank)
      results    → web search results batch
      social     → social platform results batch
      images     → image urls batch
      tags       → tag cloud data
      rank       → PeopleRank score data
      stats      → summary statistics
      done       → search complete
      error      → fatal error
    """
    raw_query = request.args.get("q", "").strip()
    place_of_work = request.args.get("work", "").strip()
    institute = request.args.get("institute", "").strip()
    image_url = request.args.get("image", "").strip()
    if not raw_query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    def generate():
        try:
            # ── Parse query ──────────────────────────────────────────────────
            query = parser.parse(raw_query, place_of_work=place_of_work, institute=institute, image_url=image_url)
            full_name = query["full_name"] or raw_query

            yield sse_event("start", {
                "query": query,
                "message": f"Searching for '{full_name}'...",
                "timestamp": time.time(),
            })

            all_web_results = []
            all_social_results = []
            images = []

            # ── Stage 1: Web search (primary mashup) ─────────────────────────
            yield sse_event("progress", {"stage": "web_search", "message": "Querying web search engines...", "pct": 10})

            web_results = []
            try:
                web_results = searcher.multi_search(query["query_variants"], max_per_query=6)
                all_web_results.extend(web_results)
            except Exception as e:
                logger.error(f"Web search failed: {e}")

            yield sse_event("results", {
                "items": web_results,
                "count": len(web_results),
                "message": f"Found {len(web_results)} web results",
            })

            # ── Stage 2: Social probing ───────────────────────────────────────
            yield sse_event("progress", {"stage": "social_probe", "message": "Probing social platforms...", "pct": 35})

            social_results = []
            try:
                social_results = social_prober.probe_all(query)
                all_social_results.extend(social_results)
            except Exception as e:
                logger.error(f"Social probe failed: {e}")

            yield sse_event("social", {
                "items": social_results,
                "count": len(social_results),
                "message": f"Found {len(social_results)} social profiles/mentions",
            })

            # ── Stage 2.1: Advanced Account Linking ──────────────────────────────
            yield sse_event("progress", {"stage": "account_linker", "message": "Deriving usernames and linking accounts...", "pct": 40})
            
            accounts = []
            try:
                usernames = account_linker.derive_usernames(query["first_name"], query["last_name"], query.get("keywords", []))
                accounts = account_linker.probe_platforms(usernames)
                all_social_results.extend(accounts)
            except Exception as e:
                logger.error(f"Account linking failed: {e}")
                
            yield sse_event("accounts", {
                "items": accounts,
                "count": len(accounts),
                "message": f"Linked {len(accounts)} likely accounts"
            })
            
            # ── Stage 2.2: Research Discovery ────────────────────────────────────
            yield sse_event("progress", {"stage": "research_finder", "message": "Searching academic databases...", "pct": 45})
            
            research_data = {}
            try:
                research_data = research_finder.find_all(query)
            except Exception as e:
                logger.error(f"Research finding failed: {e}")
                
            yield sse_event("research", {
                "data": research_data,
                "message": f"Found {research_data.get('total_papers', 0)} research papers"
            })
            
            # ── Stage 2.3: Comments & Public Posts ────────────────────────────────
            yield sse_event("progress", {"stage": "comments_finder", "message": "Scraping public comments...", "pct": 50})
            
            comments_data = {}
            try:
                comments_data = comments_finder.find_all(query)
            except Exception as e:
                logger.error(f"Comments finding failed: {e}")
                
            yield sse_event("comments", {
                "data": comments_data,
                "message": f"Found {comments_data.get('total_comments', 0)} comments/discussions"
            })
            
            # ── Stage 2.4: Visual Intelligence ────────────────────────────────────
            if query.get("image_url"):
                yield sse_event("progress", {"stage": "visual_intel", "message": "Generating visual intelligence links...", "pct": 55})
                
                visual_links = []
                try:
                    visual_links = visual_intel.generate_links(query)
                except Exception as e:
                    logger.error(f"Visual intel failed: {e}")
                    
                yield sse_event("visual", {
                    "items": visual_links,
                    "message": "Generated reverse image search links"
                })


            # ── Stage 3: Image harvest ────────────────────────────────────────
            yield sse_event("progress", {"stage": "image_harvest", "message": "Harvesting images...", "pct": 60})

            try:
                images = image_harvester.harvest(full_name, max_images=12)
            except Exception as e:
                logger.error(f"Image harvest failed: {e}")

            yield sse_event("images", {
                "items": images,
                "count": len(images),
                "message": f"Found {len(images)} images",
            })

            # ── Stage 4: Entity resolution ────────────────────────────────────
            yield sse_event("progress", {"stage": "resolving", "message": "Resolving entities & building tag cloud...", "pct": 78})

            resolved = entity_resolver.resolve(all_web_results, all_social_results, query)
            resolved["stats"]["has_images"] = len(images) > 0

            yield sse_event("tags", {
                "items": resolved["tag_cloud"],
                "homonym_groups": len(resolved.get("homonym_groups", [])),
                "message": f"Generated {len(resolved['tag_cloud'])} topic tags",
            })

            # ── Stage 5: PeopleRank ────────────────────────────────────────────
            yield sse_event("progress", {"stage": "ranking", "message": "Computing PeopleRank score...", "pct": 90})

            rank_data = people_ranker.compute(resolved, images, query)

            yield sse_event("rank", {
                "score": rank_data["score"],
                "grade": rank_data["grade"],
                "label": rank_data["label"],
                "breakdown": rank_data["breakdown"],
                "interpretation": rank_data["interpretation"],
            })

            # ── Final stats ────────────────────────────────────────────────────
            yield sse_event("stats", {
                **resolved["stats"],
                "rank_score": rank_data["score"],
                "platforms": rank_data["breakdown"].get("social_presence", {}).get("platforms", []),
            })

            yield sse_event("progress", {"stage": "done", "message": "Search complete!", "pct": 100})
            yield sse_event("done", {"message": "IntelFusion search completed", "timestamp": time.time()})

        except Exception as e:
            logger.exception(f"Fatal error during search for '{raw_query}'")
            yield sse_event("error", {"message": str(e)})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.route("/api/suggest")
def suggest():
    """Simple auto-complete placeholder — returns query variants."""
    raw = request.args.get("q", "").strip()
    if len(raw) < 2:
        return jsonify([])
    query = parser.parse(raw)
    suggestions = query["query_variants"][:5]
    return jsonify(suggestions)


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "IntelFusion OSINT API",
        "version": "1.0.0",
        "google_cse_enabled": bool(os.getenv("GOOGLE_API_KEY")),
    })


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    logger.info(f"🚀 IntelFusion starting on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
