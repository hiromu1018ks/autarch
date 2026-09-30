from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / ".claude" / "skills" / "autarch" / "SKILL.md"


def _read():
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter(text):
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    return text[4:end]


class TestSkillMarkdown:
    def test_skill_exists_through_symlink(self):
        assert SKILL_MD.is_file()

    def test_frontmatter_disables_model_invocation(self):
        frontmatter = _frontmatter(_read())
        assert "name: autarch" in frontmatter
        assert "description: Resolve a decision by generating alternatives and evaluating them with Jev." in frontmatter
        assert "disable-model-invocation: true" in frontmatter

    def test_contains_all_thirteen_steps(self):
        text = _read()
        for step in range(1, 14):
            assert f"### Step {step}" in text

    def test_neutral_generation_instruction(self):
        text = _read()
        assert "Generate alternatives neutrally." in text
        assert "comparable level of detail." in text

    def test_secret_exclusion_instruction(self):
        assert "Do not read or include .env files, credential files," in _read()

    def test_probability_is_not_a_score(self):
        assert "NOT scores" in _read()

    def test_ask_user_does_not_repeat_question(self):
        assert "Do NOT repeat the original technical question" in _read()

    def test_decide_py_invocation_documented(self):
        text = _read()
        assert "decide.py" in text
        assert "--state-file" in text
        assert "TYPESAFE_API_KEY" in text
        assert "SELECT_OPTION_WITH_CAUTION" in text
        assert "PROVIDER_UNAVAILABLE" in text
        assert "INSUFFICIENT_OPTIONS" in text
