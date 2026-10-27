"""
Tests — the optional Meetings feature (transcription, summary, structured extraction).

Offline: Whisper, yt-dlp, ffmpeg and Groq are all faked, so none of the optional
dependencies needs to be installed for these to run.
"""

import json
import os
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from Services import agent
from Services.meeting import audio_processor, extractor, summarizer, transcriber


def _reply(content):
    return MagicMock(content=content)


class SharedModelSettingsTests(SimpleTestCase):
    """The feature broke silently once when its own default model was retired."""

    def test_meetings_use_the_same_live_model_as_the_rag_agent(self):
        self.assertEqual(extractor.GROQ_MODEL, agent.GROQ_MODEL)
        self.assertEqual(summarizer.GROQ_MODEL, agent.GROQ_MODEL)
        self.assertNotIn("llama-3.3", extractor.GROQ_MODEL)

    def test_meeting_clients_time_out_and_retry(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-not-used"}):
            for module in (extractor, summarizer):
                module._llm = None
                client = module._get_llm()
                self.assertEqual(client.request_timeout, agent.LLM_TIMEOUT_SECONDS)
                self.assertEqual(client.max_retries, agent.LLM_MAX_RETRIES)
                module._llm = None


class ExtractorTests(SimpleTestCase):

    def setUp(self):
        self.llm = MagicMock()
        p = patch.object(extractor, "_get_llm", return_value=self.llm)
        p.start()
        self.addCleanup(p.stop)

    def test_parses_the_three_lists(self):
        self.llm.invoke.return_value = _reply(json.dumps({
            "action_items": ["Ship v2 (Assignee: Ana, Due: Friday)"],
            "key_decisions": ["Move launch to May"],
            "open_questions": ["Who owns billing?"],
        }))
        out = extractor.extract_structured_meeting_data("Ana will ship v2 by Friday.")
        self.assertEqual(out["action_items"], ["Ship v2 (Assignee: Ana, Due: Friday)"])
        self.assertEqual(out["key_decisions"], ["Move launch to May"])
        self.assertEqual(out["open_questions"], ["Who owns billing?"])

    def test_empty_transcript_makes_no_llm_call(self):
        out = extractor.extract_structured_meeting_data("   ")
        self.assertEqual(out, {"action_items": [], "key_decisions": [], "open_questions": []})
        self.llm.invoke.assert_not_called()

    def test_malformed_model_output_degrades_to_empty_lists(self):
        self.llm.invoke.return_value = _reply("not json at all")
        out = extractor.extract_structured_meeting_data("Some meeting.")
        self.assertEqual(out, {"action_items": [], "key_decisions": [], "open_questions": []})

    def test_missing_keys_default_to_empty(self):
        self.llm.invoke.return_value = _reply(json.dumps({"action_items": ["One task"]}))
        out = extractor.extract_structured_meeting_data("Some meeting.")
        self.assertEqual(out["key_decisions"], [])
        self.assertEqual(out["open_questions"], [])

    def test_long_transcripts_are_capped_before_sending(self):
        self.llm.invoke.return_value = _reply("{}")
        extractor.extract_structured_meeting_data("x" * 50_000)
        sent = self.llm.invoke.call_args.args[0][1].content
        self.assertLess(len(sent), 12_100)

    def test_convenience_wrappers(self):
        self.llm.invoke.return_value = _reply(json.dumps(
            {"action_items": ["a"], "key_decisions": ["d"], "open_questions": ["q"]}))
        self.assertEqual(extractor.extract_action_items("m"), ["a"])
        self.assertEqual(extractor.extract_key_decisions("m"), ["d"])
        self.assertEqual(extractor.extract_open_questions("m"), ["q"])


class SummarizerTests(SimpleTestCase):

    def setUp(self):
        self.llm = MagicMock()
        p = patch.object(summarizer, "_get_llm", return_value=self.llm)
        p.start()
        self.addCleanup(p.stop)

    def test_title_strips_quotes(self):
        self.llm.invoke.return_value = _reply('"Q3 Planning Review"')
        self.assertEqual(summarizer.generate_title("We reviewed Q3."), "Q3 Planning Review")

    def test_title_for_empty_transcript_needs_no_llm(self):
        self.assertEqual(summarizer.generate_title(""), "Untitled Meeting")
        self.llm.invoke.assert_not_called()

    def test_title_falls_back_when_the_llm_fails(self):
        self.llm.invoke.side_effect = RuntimeError("groq down")
        self.assertEqual(summarizer.generate_title("Something."), "Meeting Transcript")

    def test_short_transcript_is_summarised_in_one_call(self):
        self.llm.invoke.return_value = _reply("A short summary.")
        self.assertEqual(summarizer.summarize("Brief meeting."), "A short summary.")
        self.assertEqual(self.llm.invoke.call_count, 1)

    def test_long_transcript_uses_map_reduce(self):
        """One call per chunk, then one to combine them."""
        self.llm.invoke.return_value = _reply("partial")
        transcript = ("We discussed the roadmap in detail. " * 400).strip()  # ~14k chars
        summarizer.summarize(transcript)
        self.assertGreaterEqual(self.llm.invoke.call_count, 3)
        reduce_input = self.llm.invoke.call_args.args[0][1].content
        self.assertIn("Partial Summaries", reduce_input)

    def test_empty_transcript(self):
        self.assertIn("No transcript", summarizer.summarize(""))
        self.llm.invoke.assert_not_called()


class TranscriberTests(SimpleTestCase):

    def setUp(self):
        transcriber._model = None
        self.addCleanup(setattr, transcriber, "_model", None)
        self.tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.tmp.write(b"RIFF")
        self.tmp.close()
        self.addCleanup(os.remove, self.tmp.name)

    def _fake_whisper(self, segments, error=None):
        model = MagicMock()
        if error:
            model.transcribe.side_effect = error
        else:
            info = MagicMock(language="en", language_probability=0.98)
            model.transcribe.return_value = ([MagicMock(text=s) for s in segments], info)
        module = types.ModuleType("faster_whisper")
        module.WhisperModel = MagicMock(return_value=model)
        return patch.dict(sys.modules, {"faster_whisper": module}), module

    def test_joins_segments_into_one_transcript(self):
        ctx, _ = self._fake_whisper(["  Hello team. ", "Let's begin.  "])
        with ctx:
            self.assertEqual(transcriber.transcribe_file(self.tmp.name), "Hello team. Let's begin.")

    def test_the_model_is_loaded_once(self):
        ctx, module = self._fake_whisper(["a"])
        with ctx:
            transcriber.transcribe_file(self.tmp.name)
            transcriber.transcribe_file(self.tmp.name)
        module.WhisperModel.assert_called_once()

    def test_missing_file_is_rejected_before_loading_whisper(self):
        ctx, module = self._fake_whisper(["a"])
        with ctx, self.assertRaises(FileNotFoundError):
            transcriber.transcribe_file("/no/such/file.wav")
        module.WhisperModel.assert_not_called()

    def test_a_whisper_failure_surfaces_as_runtime_error(self):
        ctx, _ = self._fake_whisper([], error=ValueError("corrupt audio"))
        with ctx, self.assertRaises(RuntimeError):
            transcriber.transcribe_file(self.tmp.name)


class AudioProcessorTests(SimpleTestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = os.path.join(self.dir, "meeting.mp4")
        with open(self.src, "wb") as fh:
            fh.write(b"\x00")

    def test_convert_builds_the_16khz_mono_ffmpeg_command(self):
        def fake_run(cmd, **kwargs):
            open(cmd[-1], "wb").close()  # ffmpeg would write the output file
            return MagicMock(returncode=0, stderr="")

        with patch.object(audio_processor.subprocess, "run", side_effect=fake_run) as run:
            out = audio_processor.convert_to_wav(self.src)
        cmd = run.call_args.args[0]
        self.assertTrue(out.endswith("meeting.wav"))
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("16000", cmd)
        self.assertEqual(cmd[cmd.index("-ac") + 1], "1")

    def test_convert_skips_work_when_the_wav_already_exists(self):
        open(os.path.join(self.dir, "meeting.wav"), "wb").close()
        with patch.object(audio_processor.subprocess, "run") as run:
            audio_processor.convert_to_wav(self.src)
        run.assert_not_called()

    def test_convert_rejects_a_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            audio_processor.convert_to_wav(os.path.join(self.dir, "nope.mp4"))

    def test_download_without_yt_dlp_explains_what_to_install(self):
        with patch.dict(sys.modules, {"yt_dlp": None}), self.assertRaises(RuntimeError) as ctx:
            audio_processor.download_youtube("https://youtu.be/abc", output_dir=self.dir)
        self.assertIn("requirements-optional", str(ctx.exception))

    def test_download_returns_the_mp3_path(self):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.side_effect = lambda url, download: (
            open(os.path.join(self.dir, "abc.mp3"), "wb").close() or {"id": "abc"})
        module = types.ModuleType("yt_dlp")
        module.YoutubeDL = MagicMock(return_value=ydl)
        with patch.dict(sys.modules, {"yt_dlp": module}):
            path = audio_processor.download_youtube("https://youtu.be/abc", output_dir=self.dir)
        self.assertTrue(path.endswith("abc.mp3"))

    def test_cleanup_ignores_paths_that_are_already_gone(self):
        audio_processor.cleanup_temp_files(self.src, os.path.join(self.dir, "missing.wav"))
        self.assertFalse(os.path.exists(self.src))
