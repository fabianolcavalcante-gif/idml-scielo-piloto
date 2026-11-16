"""Recognize explicit unavailable upstream checks, never infer from severity/title alone."""

PREFIX = "external-verification-unavailable-"


def unavailable_dependency(item):
    rule = item.get("data") if "status" in item and isinstance(item.get("data"), dict) else item
    if not isinstance(rule, dict):
        return None
    title = str(rule.get("title", "")).casefold()
    kind = rule.get("validation_type")
    data = rule.get("data") if isinstance(rule.get("data"), dict) else {}
    response = str(rule.get("response", item.get("status", ""))).casefold()
    if response not in {"warning", "error", "critical"}:
        return None
    if (
        title == "registered orcid"
        and kind == "registered"
        and rule.get("item") == "contrib-id"
        and rule.get("got_value") == "unknown"
        and data.get("status") == "unknown"
    ):
        return "orcid-registry"
    if (
        title == "registered doi"
        and kind == "registered"
        and rule.get("item") == "article-id"
        and not data.get("registered")
        and data.get("valid") is not True
    ):
        exception = str(data.get("exception_type", ""))
        if exception == "<class 'tenacity.RetryError'>" or any(
            token in exception for token in ("ConnectionError", "Timeout", "URLError")
        ):
            return "doi-registry"
    if (
        title == "registered issue"
        and kind == "value in list"
        and rule.get("item") == "volume, number, supplement"
        and rule.get("advice") == "Unable to check if issue is registered"
    ):
        return "journal-issues"
    if (
        title == "table of contents section"
        and kind == "value in list"
        and rule.get("item") == "subj-group"
        and rule.get("got_value")
        and str(rule.get("expected_value")) in {"{}", "[]", "one of {}", "one of []"}
        and str(rule.get("advice", "")).startswith("Unable to check")
    ):
        return "journal-sections"
    return None
