"""Skills management tools for LLM to discover and use project skills."""

import json
from pathlib import Path


def get_skills_root() -> Path:
    """Get the .agents/skills directory path relative to project root."""
    project_root = Path(__file__).parent.parent.parent
    skills_dir = project_root / ".agents" / "skills"
    return skills_dir


def list_skills() -> dict:
    """List all available skills in the .agents/skills directory.
    
    Returns a dict with skill names and their metadata (description from skill file if available).
    """
    skills_dir = get_skills_root()
    
    if not skills_dir.exists():
        return {"skills": [], "message": "No skills directory found"}
    
    if not skills_dir.is_dir():
        return {"skills": [], "error": "Skills path is not a directory"}
    
    skills = []
    
    # Iterate through skill directories
    for skill_item in skills_dir.iterdir():
        if not skill_item.is_dir():
            continue
            
        skill_name = skill_item.name
        
        # Look for a markdown file with same name as the directory
        skill_file = skill_item / f"{skill_name}.md"
        description = None
        
        if skill_file.exists():
            try:
                content = skill_file.read_text(encoding="utf-8")
                # Extract description from the file (first few lines)
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("description:"):
                        # Extract the description value
                        desc = line.split(":", 1)[1].strip()
                        description = desc
                        break
            except Exception:
                pass
        
        skills.append({
            "name": skill_name,
            "path": str(skill_item),
            "has_content": skill_file.exists() if skill_file else False,
            "description": description or "No description available"
        })
    
    return {
        "skills_directory": str(skills_dir),
        "skills": sorted(skills, key=lambda x: x["name"]),
        "total": len(skills)
    }


def read_skill(skill_name: str) -> dict:
    """Read the full content of a specific skill.
    
    Args:
        skill_name: The name of the skill (directory name under .agents/skills)
    
    Returns:
        Dict containing the skill content
    """
    skills_dir = get_skills_root()
    skill_dir = skills_dir / skill_name
    
    if not skill_dir.exists():
        raise ValueError(f"Skill '{skill_name}' not found")
    
    if not skill_dir.is_dir():
        raise ValueError(f"Skill '{skill_name}' is not a directory")
    
    # Look for markdown file
    skill_file = skill_dir / f"{skill_name}.md"
    
    if not skill_file.exists():
        # Try to find any markdown file in the directory
        md_files = list(skill_dir.glob("*.md"))
        if md_files:
            skill_file = md_files[0]
        else:
            raise ValueError(f"No markdown file found for skill '{skill_name}'")
    
    try:
        content = skill_file.read_text(encoding="utf-8")
        return {
            "skill_name": skill_name,
            "file_path": str(skill_file),
            "content": content
        }
    except Exception as e:
        raise RuntimeError(f"Failed to read skill '{skill_name}': {str(e)}") from e


def tool_specs() -> list[dict]:
    """Return OpenAI-compatible tool specifications."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_skills",
                "description": "List all available skills in the project. Use this to discover what skills are available and determine if a user's request requires a specific skill.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_skill",
                "description": "Read the full content of a specific skill to understand its rules, format, and examples. Call this after determining which skill to use.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "The name of the skill to read (directory name under .agents/skills, e.g., 'notice')"
                        },
                    },
                    "required": ["skill_name"],
                },
            },
        }
    ]


def tool_dispatch() -> dict:
    """Return the mapping of tool names to their handler functions."""
    return {
        "list_skills": list_skills,
        "read_skill": read_skill
    }


def format_tool_result(result: dict) -> str:
    """Format tool result as JSON string."""
    return json.dumps(result, ensure_ascii=False, indent=2)
