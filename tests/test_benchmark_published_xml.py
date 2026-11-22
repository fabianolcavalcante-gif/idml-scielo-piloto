from ops.benchmark_published_xml import score, summarize

KEY = (
    b'<article xmlns:xlink="http://www.w3.org/1999/xlink" xml:lang="en"><front>'
    b'<article-meta><article-id pub-id-type="doi">10.1590/x</article-id><title-group>'
    b"<article-title>Nitrogen removal</article-title></title-group><contrib-group>"
    b"<contrib><name><surname>Lopes</surname><given-names>Mariana</given-names></name>"
    b'</contrib></contrib-group><aff id="a1"><country country="BR">Brazil</country></aff>'
    b'<history><date date-type="received"><day>12</day><month>03</month><year>2024</year>'
    b"</date></history><abstract><p>Short abstract.</p></abstract>"
    b'<kwd-group xml:lang="en"><kwd>wetlands</kwd></kwd-group></article-meta></front>'
    b'<body><sec><title>Introduction</title><p>Text <xref ref-type="bibr" rid="B1">'
    b"1</xref>.</p><table-wrap><label>Table 1</label><table><thead><tr><th>A</th></tr>"
    b"</thead><tbody><tr><td>1</td></tr></tbody></table></table-wrap></sec></body><back>"
    b'<ref-list><ref id="B1"><mixed-citation>Silva A. Title. Src. 2020.</mixed-citation>'
    b"<element-citation><person-group><name><surname>Silva</surname></name></person-group>"
    b"<article-title>Title</article-title><source>Src</source><year>2020</year>"
    b"</element-citation></ref></ref-list></back>"
    b'<sub-article article-type="translation" xml:lang="pt"><front-stub><title-group>'
    b"<article-title>Remocao</article-title></title-group></front-stub></sub-article>"
    b"</article>"
)


def test_identical_xml_scores_one_everywhere() -> None:
    scores = score(KEY, KEY)
    assert all(value in (None, 1.0) for value in scores.values()), scores
    assert summarize(scores) == 1.0


def test_published_key_detects_missing_table_country_and_translation() -> None:
    candidate = (
        KEY.replace(b' country="BR"', b"")
        .replace(b"<thead><tr><th>A</th></tr></thead>", b"")
        .split(b"<sub-article")[0]
        + b"</article>"
    )
    scores = score(candidate, KEY)
    assert scores["aff_countries"] == 0.0
    assert scores["table_thead"] == 0.0
    assert scores["sub_articles"] == 0.0
    assert scores["title"] == 1.0 and scores["ref_surname"] == 1.0
    assert summarize(scores) < 1.0


def test_sub_article_content_does_not_leak_into_main_article_fields() -> None:
    scores = score(KEY, KEY.replace(b"<article-title>Remocao", b"<article-title>Outro"))
    assert scores["title"] == 1.0
