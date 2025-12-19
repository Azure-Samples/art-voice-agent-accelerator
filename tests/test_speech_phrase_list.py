import pytest
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes


class StubPhraseList:
    def __init__(self):
        self.added = []
        self.cleared = 0
        self.weight = None

    def addPhrase(self, phrase):
        self.added.append(phrase)

    def clear(self):
        self.cleared += 1
        self.added = []

    def setWeight(self, weight):
        self.weight = weight


@pytest.fixture
def recognizer_stub():
    recognizer = StreamingSpeechRecognizerFromBytes.__new__(StreamingSpeechRecognizerFromBytes)
    recognizer.speech_recognizer = object()
    recognizer._phrase_list_phrases = set()
    recognizer._phrase_list_weight = None
    recognizer._phrase_list_grammar = None
    return recognizer


@pytest.fixture
def phrase_list(monkeypatch):
    stub = StubPhraseList()

    import src.speech.speech_recognizer as speech_module

    monkeypatch.setattr(
        speech_module.speechsdk.PhraseListGrammar,
        "from_recognizer",
        lambda recognizer: stub,
    )

    return stub


def test_add_phrase_applies_when_active(recognizer_stub, phrase_list):
    recognizer_stub.add_phrase("Contoso")
    recognizer_stub._apply_phrase_list()

    assert phrase_list.cleared >= 1
    assert phrase_list.added == ["Contoso"]


def test_add_phrases_deduplicates(recognizer_stub, phrase_list):
    recognizer_stub.add_phrases(["Jessie", "Jessie", "Rehaan"])
    recognizer_stub._apply_phrase_list()

    assert phrase_list.added == ["Jessie", "Rehaan"]


def test_set_phrase_weight_applies(recognizer_stub, phrase_list):
    recognizer_stub.add_phrase("Contoso")
    recognizer_stub.set_phrase_list_weight(1.5)
    recognizer_stub._apply_phrase_list()

    assert phrase_list.weight == 1.5


def test_clear_phrase_list_removes_entries(recognizer_stub, phrase_list):
    recognizer_stub.add_phrases(["Alpha", "Beta"])
    recognizer_stub.clear_phrase_list()
    recognizer_stub._apply_phrase_list()

    assert phrase_list.added == []
    assert phrase_list.cleared >= 1


def test_set_phrase_weight_validation(recognizer_stub):
    with pytest.raises(ValueError):
        recognizer_stub.set_phrase_list_weight(0)


def test_env_default_phrase_list(monkeypatch):
    monkeypatch.setenv("SPEECH_RECOGNIZER_DEFAULT_PHRASES", "Alpha, Beta ,Gamma,,")
    monkeypatch.setattr(
        StreamingSpeechRecognizerFromBytes,
        "_create_speech_config",
        lambda self: object(),
    )

    recognizer = StreamingSpeechRecognizerFromBytes(key="test", region="test")

    assert recognizer._phrase_list_phrases == {"Alpha", "Beta", "Gamma"}


def test_initial_phrases_argument(monkeypatch):
    monkeypatch.setenv("SPEECH_RECOGNIZER_DEFAULT_PHRASES", "")
    monkeypatch.setattr(
        StreamingSpeechRecognizerFromBytes,
        "_create_speech_config",
        lambda self: object(),
    )

    recognizer = StreamingSpeechRecognizerFromBytes(
        key="test",
        region="test",
        initial_phrases=["Ada", "Grace", "Ada"],
    )

    assert recognizer._phrase_list_phrases == {"Ada", "Grace"}
