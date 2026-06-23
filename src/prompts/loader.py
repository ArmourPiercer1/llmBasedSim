from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class PromptLoader:
    def __init__(self, prompts_dir: str = "prompts"):
        self._env = Environment(
            loader=FileSystemLoader(prompts_dir),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, context: dict) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context)
