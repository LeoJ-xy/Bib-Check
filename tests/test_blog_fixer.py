import responses
from bibcheck.auto.blog_fixer import plan_blog_fix
from bibcheck.auto.cache import HTTPCache


@responses.activate
def test_blog_canonical_and_title_applied():
    html = """
    <html><head>
    <link rel="canonical" href="https://example.com/post"/>
    <meta property="og:title" content="My Blog Post"/>
    <meta name="citation_author" content="Alice"/>
    </head><body>
    <pre><code>@misc{key, title={My Blog Post}, author={Alice}}</code></pre>
    </body></html>
    """
    responses.add(responses.GET, "https://example.com/post", body=html, status=200)
    entry = {"ID": "k1", "ENTRYTYPE": "misc", "title": "Old", "author": "Bob", "url": "https://example.com/post"}
    session = __import__("requests").Session()
    cache = HTTPCache(path=":memory:")
    suggested, applied = plan_blog_fix(entry, session, cache, "test-agent", min_conf=0.85, accessed_date="2026-01-04")
    assert any(p["field"] == "title" and p["applied"] for p in applied)
    assert entry["title"] == "My Blog Post"

