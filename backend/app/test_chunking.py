"""
Tests — split_pages chunks text the same way whatever its line endings.

The underlying splitter is sensitive to them. No current loader passes it CRLF
(TextLoader reads in text mode, which converts), so these pin split_pages'
contract rather than reproduce a bug seen in production.
"""

from django.test import SimpleTestCase
from langchain_core.documents import Document
from Services.Extractor import CHUNK_SIZE, normalise_newlines, split_pages

# Shaped like the real policy documents: sections separated by blank lines, each
# section's text hard-wrapped with single newlines. That shape is what exposes the
# bug. With "\n\n" available the splitter keeps each section whole; with CRLF it
# cannot find "\n\n", falls back to "\n", and packs lines across section boundaries.
# (A fixture with no line breaks inside paragraphs chunks identically either way,
# and so would pass with or without the fix.)
_LINE = "Records of this type are retained for the period set out below."
SECTIONS = [f"Section {i}: retention rules\n" + "\n".join([_LINE] * 9) for i in range(6)]
TEXT_LF = "\n\n".join(SECTIONS)


def _chunks(text):
    return [c.page_content for c in split_pages([Document(page_content=text, metadata={"source": "x"})])]


class ChunkingTests(SimpleTestCase):

    def test_fixture_actually_needs_splitting(self):
        self.assertGreater(len(TEXT_LF), CHUNK_SIZE * 2)

    def test_fixture_exposes_the_bug_without_normalisation(self):
        """Guards the guard: without normalisation this fixture must chunk differently."""
        from Services.Extractor import _splitter

        def raw(text):
            return [c.page_content.replace("\r", "")
                    for c in _splitter.split_documents([Document(page_content=text)])]

        self.assertNotEqual(raw(TEXT_LF.replace("\n", "\r\n")), raw(TEXT_LF))

    def test_each_section_stays_whole(self):
        for chunk in _chunks(TEXT_LF):
            self.assertEqual(chunk.count("Section "), 1, chunk[:60])

    def test_windows_line_endings_chunk_exactly_like_unix(self):
        """'\\n\\n' never occurs inside '\\r\\n\\r\\n'; split_pages must not care."""
        self.assertEqual(_chunks(TEXT_LF.replace("\n", "\r\n")), _chunks(TEXT_LF))

    def test_old_mac_line_endings_chunk_exactly_like_unix(self):
        self.assertEqual(_chunks(TEXT_LF.replace("\n", "\r")), _chunks(TEXT_LF))

    def test_no_carriage_return_survives_into_a_chunk(self):
        for chunk in _chunks(TEXT_LF.replace("\n", "\r\n")):
            self.assertNotIn("\r", chunk)

    def test_normalise_newlines(self):
        self.assertEqual(normalise_newlines("a\r\nb\rc\nd"), "a\nb\nc\nd")
