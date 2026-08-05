import unittest
from extraction_helpers import extract_between, _read_app_source


class TestTranslations(unittest.TestCase):
    """The translation system fails open by design (missing key falls
    back to English, missing English falls back to the key itself),
    so a missing key never crashes anything -- but it silently shows
    English (or worse, a raw key like "nav.Owner Console") to someone
    who chose a different language. That happened for real once
    already (the Owner Console nav item was added after the
    translation dict was built, and nobody noticed until a screenshot
    showed the raw key on screen). This test exists specifically to
    catch that class of gap automatically instead of relying on
    someone happening to look at the right screen in the right
    language."""

    @classmethod
    def setUpClass(cls):
        src = _read_app_source()
        block = extract_between("TRANSLATIONS = {", "\n\n\ndef get_user_language", src)
        ns = {}
        exec(block, ns)
        cls.TRANSLATIONS = ns["TRANSLATIONS"]

    def test_all_six_languages_present(self):
        expected = {"en", "fr", "es", "pt", "zh", "hi"}
        self.assertEqual(set(self.TRANSLATIONS.keys()), expected)

    def test_every_language_has_exactly_the_same_keys_as_english(self):
        en_keys = set(self.TRANSLATIONS["en"].keys())
        for lang, entries in self.TRANSLATIONS.items():
            with self.subTest(lang=lang):
                missing = en_keys - set(entries.keys())
                extra = set(entries.keys()) - en_keys
                self.assertEqual(missing, set(), f"{lang} is missing keys: {missing}")
                self.assertEqual(extra, set(), f"{lang} has extra keys not in English: {extra}")

    def test_every_nav_option_has_a_translation_key(self):
        """The specific class of bug this project actually hit:
        nav_options gained an entry (Owner Console) that the
        translation dict didn't know about. This test derives the
        real, current nav options list from app.py directly, so if
        another one gets added later without a matching translation,
        this fails immediately instead of waiting for a screenshot."""
        src = _read_app_source()
        # The base nav_options list, plus the special owner-only insert
        base_start = src.index('nav_options = ["Task Dashboard"')
        base_end = src.index("]", base_start) + 1
        base_list_src = src[base_start:base_end]
        ns = {}
        exec(base_list_src, ns)
        nav_options = list(ns["nav_options"])
        if 'nav_options.insert(1, "Owner Console")' in src:
            nav_options.insert(1, "Owner Console")

        en_keys = set(self.TRANSLATIONS["en"].keys())
        for section in nav_options:
            with self.subTest(section=section):
                self.assertIn(f"nav.{section}", en_keys,
                    f"'{section}' is a real nav option with no matching translation key")

    def test_no_value_is_the_literal_untranslated_key(self):
        """A translation value that's literally identical to its own
        key (e.g. "nav.About": "nav.About") almost always means
        someone copy-pasted a key as a placeholder and forgot to
        actually translate it."""
        for lang, entries in self.TRANSLATIONS.items():
            for key, value in entries.items():
                with self.subTest(lang=lang, key=key):
                    self.assertNotEqual(value, key,
                        f"{lang}['{key}'] appears untranslated (value equals the key itself)")


if __name__ == "__main__":
    unittest.main()
