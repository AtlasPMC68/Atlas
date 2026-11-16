from app.utils.text_extraction import process_candidate_text, should_ignore


def test_should_ignore_numeric_and_scale_annotations():
    assert should_ignore("1783")
    assert should_ignore("600 Km")
    assert should_ignore("600km")
    assert should_ignore("Échelle 1:50000")
    assert should_ignore("Miles")


def test_process_candidate_text_keeps_numbers_but_strips_years():
    quad = [[0, 0], [10, 0], [10, 10], [0, 10]]

    assert process_candidate_text("Route 600", quad)["text"] == "Route 600"
    assert process_candidate_text("Québec 1783", quad)["text"] == "Québec"
    assert process_candidate_text("Boston (1630)", quad)["text"] == "Boston"
    assert process_candidate_text("600 Km", quad) is None
