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

    def test_decision_material_written_in_english(self):
        text = _read()
        assert "Write all decision material in English" in text
        assert "user's conversation language" in text

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

    def test_step7_documents_new_threshold_flags(self):
        text = _read()
        assert "--sufficiency" in text
        assert "--blocker-confidence" in text

    def test_step8_documents_new_resolution_fields(self):
        text = _read()
        assert "evidence_sufficiency" in text
        assert "blocker_class" in text
        assert "blocker_confidence" in text

    def test_ask_user_dispatches_on_blocker_class(self):
        text = _read()
        assert "evidence_insufficient" in text
        assert "investigation_exhausted" in text
        assert "material_bias" in text

    def test_investigation_loop_instructions(self):
        text = _read()
        assert "investigate once" in text
        assert '"revision"' in text
        assert "exactly one more time" in text
        assert "external documentation" in text
        assert "Never invent facts" in text
        assert "material_fix" in text

    def test_hard_constraint_flow(self):
        text = _read()
        for term in (
            "hard_constraints", "evidence_records", "verified", "inference",
            "constraint_unverified", "constraint_candidates_insufficient",
            "constraint_check", "eligible_option_ids", "excluded_options",
            "unknown_assessments",
        ):
            assert term in text
        for instruction in (
            "every original alternative ID",
            "inference alone must remain `unknown`",
            "Recheck changing facts at decision time",
            "one shared revision round",
            "If `revision` already exists",
            "Never relax a hard constraint without the user's instruction",
            "Do not automatically repeat candidate generation",
            "legacy path has no evidence-backed exclusion guarantee",
        ):
            assert instruction in text

    def test_step4_requires_investigation_before_state(self):
        text = _read()
        assert "Investigate before writing the state" in text
        assert "do not defer them to a" in text
        assert "never investigate those" in text

    def test_step6_shows_assessments_object_example(self):
        text = _read()
        assert '"assessments"' in text
        assert "must be an object keyed by option id" in text

    def test_step11_routes_intent_blockers_to_deciding_question(self):
        text = _read()
        assert "(typically blocker `user_preference_unknown` or `balanced_tie`)" in text
        assert "one deciding question" in text

    def test_step11_dispatches_on_rule_first_with_low_confidence_fallback(self):
        text = _read()
        assert "Dispatch on the `rule` first" in text
        assert "below 0.50 confidence" in text
        assert "**Rule `evidence_insufficient`, no `revision`**" in text
        assert "**Rule `human_preference`**" in text
