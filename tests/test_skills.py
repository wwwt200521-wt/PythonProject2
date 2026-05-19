"""Tests for the skills management tools."""

from aiagent.tools.skills import list_skills, read_skill


def test_list_skills() -> None:
    """Test that list_skills returns the available skills."""
    result = list_skills()
    assert "skills" in result
    assert isinstance(result["skills"], list)
    assert "total" in result
    assert result["total"] == len(result["skills"])
    # Should find at least the 'notice' skill we created
    skill_names = [s["name"] for s in result["skills"]]
    assert "notice" in skill_names


def test_read_skill() -> None:
    """Test that read_skill can read a specific skill."""
    result = read_skill("notice")
    assert "skill_name" in result
    assert result["skill_name"] == "notice"
    assert "content" in result
    assert "file_path" in result
    # The content should contain key sections
    assert "description" in result["content"]
    assert "name" in result["content"]


def test_read_skill_not_found() -> None:
    """Test that read_skill raises error for non-existent skill."""
    try:
        read_skill("nonexistent_skill")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not found" in str(e).lower()
