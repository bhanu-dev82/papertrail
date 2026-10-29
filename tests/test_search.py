from app.schemas import Source
from app.search import _is_blocked, _order_sources


def _source(url, title="Source"):
    return Source(title=title, url=url, snippet="", mock=False)


def test_official_domains_rank_first_and_social_is_removed():
    sources = [
        _source("https://www.facebook.com/some-post", "Facebook post"),
        _source("https://hotfrog.biz/bescom", "BESCOM on Hotfrog"),
        _source("https://icici.bank.in/bescom", "BESCOM bill pay"),
        _source("https://bescom.karnataka.gov.in/en", "BESCOM official"),
        _source("https://bescom.co.in", "BESCOM"),
        _source("https://www.youtube.com/watch?v=1", "Video"),
    ]

    ordered = _order_sources(sources)
    urls = [source.url for source in ordered]

    assert urls[0] == "https://bescom.karnataka.gov.in/en"
    assert urls[1] == "https://bescom.co.in"
    assert len(urls) == 2
    assert all("facebook" not in url for url in urls)
    assert all("youtube" not in url for url in urls)
    assert all("hotfrog" not in url for url in urls)


def test_order_sources_falls_back_when_no_trusted_source_exists():
    sources = [
        _source("https://icici.bank.in/bescom", "BESCOM bill pay"),
        _source("https://www.defend.ink/bescom", "BESCOM complaint"),
    ]
    assert len(_order_sources(sources)) == 2


def test_blocked_domain_matching_includes_subdomains():
    assert _is_blocked("m.facebook.com")
    assert _is_blocked("hotfrog.biz")
    assert not _is_blocked("bescom.karnataka.gov.in")


def test_issuer_filter_drops_irrelevant_official_sources():
    sources = [
        _source("https://psc.ga.gov/consumer-info", "Payment assistance"),
        _source("https://karnatakaone.gov.in/bescom", "BESCOM bill payment"),
        _source("https://bescom.co.in", "BESCOM"),
    ]

    ordered = _order_sources(
        sources, "BANGALORE ELECTRICITY SUPPLY CO. (BESCOM)"
    )
    urls = [source.url for source in ordered]

    assert all("psc.ga.gov" not in url for url in urls)
    assert all(("karnatakaone.gov.in" in url) or ("bescom.co.in" in url) for url in urls)


def test_issuer_filter_returns_nothing_when_no_source_mentions_issuer():
    sources = [_source("https://psc.ga.gov/consumer-info", "Payment assistance")]
    assert _order_sources(sources, "BESCOM") == []


def test_order_sources_returns_empty_when_everything_is_blocked():
    sources = [
        _source("https://facebook.com/a"),
        _source("https://youtube.com/b"),
    ]
    assert _order_sources(sources) == []
