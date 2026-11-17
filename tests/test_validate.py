import json

import pytest

import validate
from conftest import write_lesson

TOPIC_MD = """---
name: demo
title: Demo
goal: Learn the demo
level: beginner
categories: [basics]
---

# Demo
"""


@pytest.fixture
def valid_topic(topic, monkeypatch):
    monkeypatch.setattr(validate, "REPO_ROOT", topic.parent.parent)
    (topic / "topic.md").write_text(TOPIC_MD, encoding="utf-8")
    write_lesson(topic, "one")
    (topic / "lessons" / "INDEX.md").write_text("- [One](basics/one.md): hook\n", encoding="utf-8")
    (topic / "lessons" / ".processed.json").write_text(json.dumps({"processed": []}), encoding="utf-8")
    return topic


def run(tdir):
    report = validate.Report()
    validate.check_topic(tdir, report)
    return report


def test_valid_topic_passes(valid_topic):
    report = run(valid_topic)
    assert report.errors == [] and report.warnings == []


def test_unlisted_lesson_and_bad_category_are_errors(valid_topic):
    write_lesson(valid_topic, "two", category="other")
    errors = run(valid_topic).errors
    assert any("`other` is not in topic.md categories" in e for e in errors)
    assert any("active lesson `two` is not listed" in e for e in errors)


def test_superseded_lesson_must_point_forward_and_leave_the_index(valid_topic):
    write_lesson(valid_topic, "one", status="superseded")
    errors = run(valid_topic).errors
    assert any("superseded_by" in e for e in errors)
    assert any("lists `one`, which is not an active lesson" in e for e in errors)


def test_supersession_must_be_recorded_on_both_lessons(valid_topic):
    new = write_lesson(valid_topic, "two")
    new.write_text(new.read_text(encoding="utf-8").replace("supersedes: null", "supersedes: one"), encoding="utf-8")
    (valid_topic / "lessons" / "INDEX.md").write_text(
        "- [One](basics/one.md): a\n- [Two](basics/two.md): b\n", encoding="utf-8"
    )
    assert any("that lesson isn't `status: superseded`" in e for e in run(valid_topic).errors)


def test_duplicate_ids_across_categories_are_errors(valid_topic):
    text = (valid_topic / "topic.md").read_text(encoding="utf-8")
    (valid_topic / "topic.md").write_text(text.replace("[basics]", "[basics, other]"), encoding="utf-8")
    dup = valid_topic / "lessons" / "other" / "one.md"
    dup.parent.mkdir()
    dup.write_text((valid_topic / "lessons" / "basics" / "one.md").read_text(encoding="utf-8").replace(
        "category: basics", "category: other"), encoding="utf-8")
    assert any("ids must be unique" in e for e in run(valid_topic).errors)


def test_lessons_with_empty_categories_are_an_error(valid_topic):
    text = (valid_topic / "topic.md").read_text(encoding="utf-8")
    (valid_topic / "topic.md").write_text(text.replace("[basics]", "[]"), encoding="utf-8")
    assert any("`categories` is empty" in e for e in run(valid_topic).errors)


def test_path_with_superseded_lesson_warns_and_duplicates_error(valid_topic):
    new = write_lesson(valid_topic, "two")
    new.write_text(new.read_text(encoding="utf-8").replace("supersedes: null", "supersedes: one"), encoding="utf-8")
    old = valid_topic / "lessons" / "basics" / "one.md"
    old.write_text(old.read_text(encoding="utf-8").replace("status: active", "status: superseded\nsuperseded_by: two"), encoding="utf-8")
    (valid_topic / "lessons" / "INDEX.md").write_text("- [Two](basics/two.md): b\n", encoding="utf-8")
    (valid_topic / "path.md").write_text("- [One](lessons/basics/one.md)\n- [Two](lessons/basics/two.md)\n", encoding="utf-8")
    report = run(valid_topic)
    assert report.errors == [] and any("no longer active" in w for w in report.warnings)

    (valid_topic / "path.md").write_text("- [Two](lessons/basics/two.md)\n- [Two](lessons/basics/two.md)\n", encoding="utf-8")
    assert any("lists `two` 2 times" in e for e in run(valid_topic).errors)


def test_stale_path_is_a_warning_not_an_error(valid_topic):
    write_lesson(valid_topic, "two")
    (valid_topic / "lessons" / "INDEX.md").write_text(
        "- [One](basics/one.md): a\n- [Two](basics/two.md): b\n", encoding="utf-8"
    )
    (valid_topic / "path.md").write_text("- [One](lessons/basics/one.md)\n", encoding="utf-8")
    report = run(valid_topic)
    assert report.errors == []
    assert any("not in the path yet" in w for w in report.warnings)


def stale_warnings(tdir):
    return [w for w in run(tdir).warnings if "sources/urls.txt" in w]


def set_sources(path, block):
    text = path.read_text(encoding="utf-8")
    head, rest = text.split("sources:\n", 1)
    tail = rest.split("---\n", 1)[1]
    path.write_text(f"{head}sources:\n{block}---\n{tail}", encoding="utf-8")


def write_urls(tdir, text):
    (tdir / "sources").mkdir(exist_ok=True)
    (tdir / "sources" / "urls.txt").write_text(text, encoding="utf-8")


def test_source_removed_from_urls_txt_warns(valid_topic):
    write_urls(valid_topic, "https://example.com/other\n")
    warnings = stale_warnings(valid_topic)
    assert len(warnings) == 1 and "https://example.com/article" in warnings[0] and "one.md" in warnings[0]


def test_commented_out_url_does_not_count_as_listed(valid_topic):
    write_urls(valid_topic, "# https://example.com/article\n")
    assert len(stale_warnings(valid_topic)) == 1


def test_listed_source_does_not_warn(valid_topic):
    write_urls(valid_topic, "https://example.com/article\n")
    assert stale_warnings(valid_topic) == []


def test_hand_made_source_with_a_local_file_does_not_warn(valid_topic):
    write_urls(valid_topic, "https://example.com/other\n")
    (valid_topic / "sources" / "digest.md").write_text("notes", encoding="utf-8")
    set_sources(
        valid_topic / "lessons" / "basics" / "one.md",
        "  - title: Digest\n    url: https://forum.example.com/r/demo\n    file: sources/digest.md\n",
    )
    assert stale_warnings(valid_topic) == []


def test_timestamped_youtube_url_matches_bare_urls_txt_line(valid_topic):
    write_urls(valid_topic, "https://www.youtube.com/watch?v=abc123XYZ_-\n")
    set_sources(
        valid_topic / "lessons" / "basics" / "one.md",
        "  - title: Video\n    url: https://www.youtube.com/watch?v=abc123XYZ_-&t=181s\n    file: sources/gone.md\n",
    )
    assert stale_warnings(valid_topic) == []


def test_superseded_lesson_is_skipped(valid_topic):
    write_urls(valid_topic, "https://example.com/other\n")
    write_lesson(valid_topic, "one", status="superseded")
    assert stale_warnings(valid_topic) == []


def test_topic_without_urls_txt_is_skipped(valid_topic):
    assert stale_warnings(valid_topic) == []


@pytest.mark.parametrize("a, b", [
    ("https://youtu.be/abc123?t=5", "https://www.youtube.com/watch?v=abc123"),
    ("https://example.com/a/#frag", "https://example.com/a"),
])
def test_source_key_treats_variants_as_one_source(a, b):
    assert validate.source_key(a) == validate.source_key(b)
