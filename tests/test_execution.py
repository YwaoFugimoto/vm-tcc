"""
Live execution tests against the 1.6M formula Elasticsearch database.

Requires all services to be running (bash start.sh).
Run with: pytest tests/test_execution.py -v -m live
"""

import pytest
import requests

pytestmark = pytest.mark.live

BASE_URL = "http://localhost:3000"


def search(session, mode, formula):
    resp = session.post(
        f"{BASE_URL}/search-formula",
        json={"mode": mode, "search_formula": formula},
        timeout=30,
    )
    return resp.status_code, resp.json() if resp.ok else resp.text


def search_both(session, formula):
    """Search with both modes, return (direct_results, tokenized_results)."""
    _, direct = search(session, "DIRECT", formula)
    _, tokenized = search(session, "TOKENIZED", formula)
    return direct, tokenized


def overlap(direct, tokenized, top_n=10):
    """Count how many formulas appear in both result sets (top N)."""
    direct_formulas = {r["formula"] for r in direct[:top_n]}
    tokenized_formulas = {r["formula"] for r in tokenized[:top_n]}
    return direct_formulas & tokenized_formulas


# ── Category 1: Response structure ──────────────────────────────────────

class TestResponseStructure:

    def test_response_is_list_of_score_formula_dicts(self, live_session):
        status, data = search(live_session, "DIRECT", r"(-1)^n x^n")
        assert status == 200
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "score" in item
            assert "formula" in item
            assert isinstance(item["score"], (int, float))
            assert isinstance(item["formula"], str)

    def test_returns_up_to_30_results(self, live_session):
        status, data = search(live_session, "DIRECT", r"x^2")
        assert status == 200
        assert 0 < len(data) <= 30

    def test_scores_between_zero_and_one(self, live_session):
        status, data = search(live_session, "DIRECT", r"\mathbb{Z}")
        assert status == 200
        for item in data:
            assert 0.0 <= item["score"] <= 1.0


# ── Category 2: Exact match / high score ────────────────────────────────

class TestExactMatch:

    def test_exact_match_direct_simple(self, live_session):
        formula = r"! \colon \mathrm{Singletons} → \mathrm{Set}"
        status, data = search(live_session, "DIRECT", formula)
        assert status == 200
        assert len(data) > 0
        assert data[0]["score"] >= 0.95

    def test_exact_match_tokenized_simple(self, live_session):
        formula = r"! \colon \mathrm{Singletons} → \mathrm{Set}"
        status, data = search(live_session, "TOKENIZED", formula)
        assert status == 200
        assert len(data) > 0
        assert data[0]["score"] >= 0.95

    def test_exact_match_medium_formula(self, live_session):
        formula = r"(K/m)^\ast(BG) \to \prod_F (K/m)^\ast(BF)"
        status, data = search(live_session, "DIRECT", formula)
        assert status == 200
        assert len(data) > 0
        assert data[0]["score"] >= 0.95


# ── Category 3: Both modes return results ───────────────────────────────

class TestBothModes:

    def test_both_modes_simple_formula(self, live_session):
        formula = r"(-1)^n x^n"
        _, direct = search(live_session, "DIRECT", formula)
        _, tokenized = search(live_session, "TOKENIZED", formula)
        assert len(direct) > 0
        assert len(tokenized) > 0
        assert direct[0]["score"] > 0
        assert tokenized[0]["score"] > 0

    def test_both_modes_complex_formula(self, live_session):
        formula = r"(K\odot X) = ((K_0 \cdot X_a) \cup_{(K_0 \cdot X_b)} (\pi_0 K \cdot X_b) \leftarrow (\pi_0 K \cdot X_b))"
        _, direct = search(live_session, "DIRECT", formula)
        _, tokenized = search(live_session, "TOKENIZED", formula)
        assert len(direct) > 0
        assert len(tokenized) > 0


# ── Category 4: Semantic relevance ──────────────────────────────────────

class TestSemanticRelevance:

    def test_similar_formula_returns_related(self, live_session):
        _, data = search(live_session, "DIRECT", r"x^n")
        assert len(data) > 0
        top_formulas = [r["formula"] for r in data[:10]]
        assert any("x^n" in f or "x^{n" in f for f in top_formulas)

    def test_variation_of_indexed_formula(self, live_session):
        formula = r"(K/m)^*(BG) \to \prod (K/m)^*(BF)"
        _, data = search(live_session, "DIRECT", formula)
        assert len(data) > 0
        assert data[0]["score"] > 0.8

    def test_subexpression_match(self, live_session):
        _, data = search(live_session, "DIRECT", r"\mathbb{Z}/n\mathbb{Z}")
        assert len(data) > 0
        top_formulas = [r["formula"] for r in data]
        assert any(r"\mathbb{Z}" in f for f in top_formulas)


# ── Category 5: Complexity ranges ───────────────────────────────────────

class TestComplexityRanges:

    def test_very_short_formula(self, live_session):
        status, data = search(live_session, "DIRECT", "!")
        assert status == 200
        assert len(data) > 0

    def test_short_with_commands(self, live_session):
        status, data = search(live_session, "TOKENIZED", r"! \colon A \to 1")
        assert status == 200
        assert len(data) > 0

    def test_long_complex_formula(self, live_session):
        formula = (
            r"$\begin{align*} R&=Sym(V^*(-2)), & R^{\vee}&=Sym(V\langle 2\rangle). "
            r"\\ \Lambda&=Sym(V^*(-2)[1]), & \Lambda^{\vee}&=Sym(V^*\langle-2\rangle[1]). "
            r"\end{align*}$"
        )
        status, data = search(live_session, "DIRECT", formula)
        assert status == 200
        assert len(data) > 0
        assert data[0]["score"] >= 0.95


# ── Category 6: Unicode and special LaTeX ───────────────────────────────

class TestSpecialNotation:

    def test_unicode_arrow(self, live_session):
        formula = r"! \colon \mathrm{Singletons} → \mathrm{Set}"
        status, data = search(live_session, "DIRECT", formula)
        assert status == 200
        assert len(data) > 0

    def test_mathbb(self, live_session):
        status, data = search(live_session, "DIRECT", r"\mathbb{Z}/m\mathbb{Z}")
        assert status == 200
        assert len(data) > 0

    def test_mathcal(self, live_session):
        status, data = search(live_session, "TOKENIZED", r"\mathcal{M}(X,Y)")
        assert status == 200
        assert len(data) > 0

    def test_overset_longrightarrow(self, live_session):
        status, data = search(live_session, "DIRECT", r"\overset{f}{\longrightarrow}")
        assert status == 200
        assert len(data) > 0


# ── Category 7: Edge cases ──────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_formula(self, live_session):
        resp = live_session.post(
            f"{BASE_URL}/search-formula",
            json={"mode": "DIRECT", "search_formula": ""},
            timeout=30,
        )
        if resp.ok:
            assert isinstance(resp.json(), list)
        else:
            assert resp.status_code >= 400

    def test_invalid_mode(self, live_session):
        resp = live_session.post(
            f"{BASE_URL}/search-formula",
            json={"mode": "INVALID", "search_formula": "x^2"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_backslash_heavy_formula(self, live_session):
        formula = r"(K-\lambda I)^{-1} = \left( \begin{array}{ccc} (A-\lambda I)^{-1} & 0 \end{array} \right)"
        status, data = search(live_session, "DIRECT", formula)
        assert status == 200
        assert len(data) > 0


# ── Category 8: Score ordering ──────────────────────────────────────────

class TestScoreOrdering:

    def test_results_sorted_by_descending_score(self, live_session):
        _, data = search(live_session, "DIRECT", r"(K\odot X)")
        assert len(data) > 1
        scores = [r["score"] for r in data]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]


# ── Category 9: DIRECT vs TOKENIZED mode comparison ────────────────────

class TestModeComparison:
    """Compare DIRECT and TOKENIZED results for the same queries.
    Checks: same top result, score comparison, and overlap in top results."""

    FORMULAS = {
        "simple": r"! \colon A \to 1",
        "medium": r"(K/m)^\ast(BG) \to \prod_F (K/m)^\ast(BF)",
        "complex": (
            r"(K\odot X) = ((K_0 \cdot X_a) \cup_{(K_0 \cdot X_b)} "
            r"(\pi_0 K \cdot X_b) \leftarrow (\pi_0 K \cdot X_b))"
        ),
        "exact_indexed": r"! \colon \mathrm{Singletons} → \mathrm{Set}",
        "mathbb": r"\mathbb{Z}/m\mathbb{Z}",
        "polynomial": r"(-1)^n x^n",
        "lambda": r"(K-\lambda I)^{-1}",
        "mapping": (
            r"!^\ast: \Map(1, \mathcal{M} (X,Y)) = \mathcal{M} (X,Y) "
            r"\overset{(!\otimes\id_X)^\ast}{\longrightarrow} "
            r"\mathcal{M} (S^1\otimes X,Y) = \Map(S^1, \mathcal{M} (X,Y))"
        ),
    }

    @pytest.mark.parametrize("label,formula", FORMULAS.items(), ids=FORMULAS.keys())
    def test_both_modes_return_results(self, live_session, label, formula):
        """Both modes must return non-empty results for every test formula."""
        direct, tokenized = search_both(live_session, formula)
        assert len(direct) > 0, f"DIRECT returned no results for '{label}'"
        assert len(tokenized) > 0, f"TOKENIZED returned no results for '{label}'"

    @pytest.mark.parametrize("label,formula", FORMULAS.items(), ids=FORMULAS.keys())
    def test_top_result_comparison(self, live_session, label, formula):
        """Compare the #1 result between modes. Log which mode scores higher."""
        direct, tokenized = search_both(live_session, formula)
        assert len(direct) > 0 and len(tokenized) > 0

        d_top = direct[0]
        t_top = tokenized[0]

        # Both should have reasonable scores
        assert d_top["score"] > 0
        assert t_top["score"] > 0

        # Log comparison (visible with pytest -v -s)
        winner = "DIRECT" if d_top["score"] >= t_top["score"] else "TOKENIZED"
        same_top = d_top["formula"] == t_top["formula"]
        print(f"\n  [{label}]")
        print(f"    DIRECT    top: {d_top['score']:.4f} | {d_top['formula'][:80]}")
        print(f"    TOKENIZED top: {t_top['score']:.4f} | {t_top['formula'][:80]}")
        print(f"    Winner: {winner} | Same #1: {same_top}")

    @pytest.mark.parametrize("label,formula", FORMULAS.items(), ids=FORMULAS.keys())
    def test_top10_overlap(self, live_session, label, formula):
        """At least 1 formula should appear in both modes' top 10."""
        direct, tokenized = search_both(live_session, formula)
        shared = overlap(direct, tokenized, top_n=10)

        # Log overlap details (visible with pytest -v -s)
        print(f"\n  [{label}] Top-10 overlap: {len(shared)} formula(s)")
        for f in list(shared)[:3]:
            print(f"    shared: {f[:80]}")

        # At least some overlap is expected — the same formulas exist in both indices
        assert len(shared) >= 1, (
            f"No overlap in top 10 between DIRECT and TOKENIZED for '{label}'"
        )

    @pytest.mark.parametrize("label,formula", FORMULAS.items(), ids=FORMULAS.keys())
    def test_score_distribution(self, live_session, label, formula):
        """Compare score ranges between modes."""
        direct, tokenized = search_both(live_session, formula)

        d_scores = [r["score"] for r in direct]
        t_scores = [r["score"] for r in tokenized]

        d_avg = sum(d_scores) / len(d_scores) if d_scores else 0
        t_avg = sum(t_scores) / len(t_scores) if t_scores else 0

        print(f"\n  [{label}]")
        print(f"    DIRECT    — count: {len(d_scores)}, top: {d_scores[0]:.4f}, avg: {d_avg:.4f}, min: {d_scores[-1]:.4f}")
        print(f"    TOKENIZED — count: {len(t_scores)}, top: {t_scores[0]:.4f}, avg: {t_avg:.4f}, min: {t_scores[-1]:.4f}")

        # Both should return meaningful scores
        assert d_avg > 0
        assert t_avg > 0
