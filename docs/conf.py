# noqa: D100, INP001
import re

from sphinx.application import Sphinx
from sphinx.ext.autodoc import Options

from positionpolling import __version__

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'papermc-position-polling-tools'
author = "Seth 'Violet' Gibbs"
release = __version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'myst_parser',
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

myst_enable_extensions = [
    'alert',
]

autodoc_member_order = 'bysource'
autodoc_default_options = {
    'exclude-members': '__weakref__',
}

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']

rst_prolog = f"""
.. |project| replace:: {project}
"""

# Subclasses of pydantic's BaseModel seem to make autodoc include a bunch of stuff that doesn't need to be documented
# and isn't documented for other classes, so they have to be explicitly ignored with a hook
autodoc_skip_regex: list[str | re.Pattern[str]] = [
    r'__pydantic.*',
    '_abc_impl',
    '__abstractmethods__',
    '__annotations__',
    '__class_vars__',
    '__dict__',
    '__doc__',
    '__module__',
    '__private_attributes__',
    '__signature__',
    # This is already in autodoc_default_options.exclude-members but BaseModel subclasses don't care
    '__weakref__',
]

def autodoc_skip_member(  # noqa: D103
        _app: Sphinx,
        _obj_type: str,
        name: str,
        _obj: object,
        _skip: bool,  # noqa: FBT001
        _options: Options,
    ) -> bool:
    return any(re.match(p, name) for p in autodoc_skip_regex)

def setup(app: Sphinx) -> None:  # noqa: D103
    app.connect('autodoc-skip-member', autodoc_skip_member)
