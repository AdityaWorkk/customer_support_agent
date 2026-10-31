from datetime import date
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[2] / "prompts"),
                   autoescape=select_autoescape(enabled_extensions=()), trim_blocks=True, lstrip_blocks=True)


def system_prompt(persona: str, user_name: str | None) -> str:
    return _env.get_template("system_prompts.j2").render(
        persona=persona, user_name=(user_name or "").split(" ")[0], today=date.today().strftime("%A, %d %B %Y"))
