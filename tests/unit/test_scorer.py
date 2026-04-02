"""Unit tests for alert event scoring."""
from __future__ import annotations

from unittest.mock import MagicMock

from packages.alerts.scorer import score_article
from packages.core.models import Article


def _make_article(
    title: str = "Test Article",
    text: str = "Some news content",
    credibility: float = 0.7,
) -> Article:
    art = MagicMock(spec=Article)
    art.title = title
    art.extracted_text = text
    art.source_credibility = credibility
    return art


class TestScoreArticle:
    def test_basic_score_in_range(self):
        article = _make_article()
        result = score_article(article)
        assert 0 <= result.score <= 100

    def test_high_credibility_boosts_score(self):
        low = score_article(_make_article(credibility=0.1))
        high = score_article(_make_article(credibility=1.0))
        assert high.score > low.score

    def test_magnitude_words_boost_score(self):
        no_mag = score_article(_make_article(text="Apple quarterly results"))
        with_mag = score_article(
            _make_article(text="Apple earnings miss guidance cut halted trading")
        )
        assert with_mag.score > no_mag.score

    def test_watchlist_match_boosts_score(self):
        no_match = score_article(
            _make_article(text="Generic market news"),
            watchlist_tickers=["AAPL"],
        )
        with_match = score_article(
            _make_article(text="AAPL reports earnings"),
            watchlist_tickers=["AAPL"],
        )
        assert with_match.score > no_match.score

    def test_breaking_title_boosts_score(self):
        normal = score_article(_make_article(title="Apple updates product line"))
        breaking = score_article(_make_article(title="BREAKING: Apple halts trading"))
        assert breaking.score > normal.score

    def test_score_capped_at_100(self):
        article = _make_article(
            title="BREAKING ALERT: Crisis halt sanctions",
            text="halt crisis bankruptcy sanctions earnings miss guidance cut recall fraud",
            credibility=1.0,
        )
        result = score_article(
            article,
            watchlist_tickers=["AAPL", "MSFT", "NVDA", "TSLA"],
            watchlist_entities=["Federal Reserve", "OPEC"],
        )
        assert result.score <= 100

    def test_reasons_not_empty(self):
        result = score_article(_make_article())
        assert len(result.reasons) > 0

    def test_entities_extracted(self):
        result = score_article(
            _make_article(text="AAPL and MSFT reported earnings"),
            watchlist_tickers=["AAPL", "MSFT"],
        )
        assert "AAPL" in result.entities.watchlist_matches
        assert "MSFT" in result.entities.watchlist_matches
