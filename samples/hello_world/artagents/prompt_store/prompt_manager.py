"""
prompt_manager.py

This module provides the PromptManager class for managing and rendering Jinja2 templates
used to generate prompts for the backend of the browser_RTAgent application.
It supports loading templates from a specified directory and rendering them with
dynamic context, such as patient information.

"""

import os

from jinja2 import Environment, FileSystemLoader

from utils.ml_logging import get_logger

logger = get_logger()


class PromptManager:
    def __init__(self, template_dir: str = "templates"):
        """
        Initialize the PromptManager with the given template directory.

        Args:
            template_dir (str): The directory containing the Jinja2 templates.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(current_dir, template_dir)

        self.env = Environment(
            loader=FileSystemLoader(searchpath=template_path), autoescape=True
        )

        templates = self.env.list_templates()
        print(f"Templates found: {templates}")

    def get_prompt(self, template_name: str, **kwargs) -> str:
        """
        Render a template with the given context.

        Args:
            template_name (str): The name of the template file.
            **kwargs: The context variables to render the template with.

        Returns:
            str: The rendered template as a string.
        """
        try:
            template = self.env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            raise ValueError(f"Error rendering template '{template_name}': {e}")
