# Changelog

## 1.5.0

- Distinguish transient source failures from real missing-paper results for arXiv, Crossref, OpenAlex, Semantic Scholar, DBLP, and CITATION.cff.
- Switch arXiv API calls to HTTPS and use a more conservative arXiv request interval.
- Avoid caching failed network lookups as empty results.
- Treat arXiv URLs on published entries as auxiliary copies instead of replacing the published venue.
- Improve author and venue matching for long author lists, `others`/`et al.` entries, team authors, NeurIPS/NIPS, ICML, COMPSTAT, and JRSS-B variants.
- Skip online DOI lookups when the DOI is syntactically invalid.
- Avoid treating nested GitHub file URLs as software repository roots for CITATION.cff checks.
- Remove generated report and cache artifacts from release-tracked content.
