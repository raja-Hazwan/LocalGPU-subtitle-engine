from subtitle_engine.vocabulary import (
    BASE_PROMPT, Vocabulary, apply_corrections, build_prompt, parse_corrections, parse_words,
)


def test_build_prompt_keeps_base_and_appends_custom_words():
    prompt = build_prompt(["dahsyat", "Dr Rozaimi"])
    assert prompt.startswith(BASE_PROMPT)       # dropping the base wording lost greetings in tests
    assert "ta'zir" in prompt and "amanah" in prompt
    assert prompt.rstrip(".").endswith("dahsyat, Dr Rozaimi")


def test_build_prompt_without_custom_words():
    assert "Istilah:" in build_prompt([])


def test_parse_words_accepts_commas_and_lines():
    assert parse_words("dahsyat, ta'zir\n  Dr Rozaimi \n\n") == ["dahsyat", "ta'zir", "Dr Rozaimi"]


def test_parse_corrections():
    text = "rasyak = dahsyat\ntakzi=ta'zir\nnot a rule\n = empty\n"
    assert parse_corrections(text) == {"rasyak": "dahsyat", "takzi": "ta'zir"}


def test_apply_corrections_whole_words_case_insensitive_keeps_capital():
    rules = {"takzi": "ta'zir", "rasyak": "dahsyat", "pecah amanah": "pecah amanah"}
    assert apply_corrections("Jadi takzi ni, Takzi.", rules) == "Jadi ta'zir ni, Ta'zir."
    assert apply_corrections("soalan rasyak ni", rules) == "soalan dahsyat ni"
    assert apply_corrections("takzimnya", rules) == "takzimnya"  # not inside other words


def test_vocabulary_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    vocab = Vocabulary(custom_words=["dahsyat"], corrections={"takzi": "ta'zir"})
    vocab.save(path)
    assert Vocabulary.load(path) == vocab


def test_vocabulary_load_defaults_when_missing_or_broken(tmp_path):
    assert Vocabulary.load(tmp_path / "nope.json").corrections  # ships with default corrections
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert isinstance(Vocabulary.load(bad), Vocabulary)
