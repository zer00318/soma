from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ask_home


def test_live_native_speech_rows_are_loaded_as_transcript(tmp_path):
    memory = tmp_path / "kf_memory.json"
    memory.write_text(
        json.dumps(
            [
                {
                    "t": 4.2,
                    "frame": "f_0",
                    "caption": (
                        'EVENT | nearby speech | transcript: "Okay, Joe, see you." '
                        "| GPS unavailable | likely"
                    ),
                    "ocr": [],
                    "source": "native_speech",
                },
                {
                    "t": 6.0,
                    "frame": "f_1",
                    "caption": "OBJECT | red sign | visible | center frame | likely",
                    "ocr": ["RED"],
                    "source": "native_vision",
                },
            ]
        )
    )

    transcript = ask_home.load_transcript(str(memory))

    assert transcript is not None
    assert transcript["usable_speech"] is True
    assert transcript["verdict"] == "live native speech transcript"
    assert "Okay, Joe, see you." in transcript["text"]
    assert transcript["segments"] == [{"start": 4.2, "end": 4.2, "text": "Okay, Joe, see you."}]
