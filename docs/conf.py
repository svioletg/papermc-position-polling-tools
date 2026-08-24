# noqa: D100, INP001
import re
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

import libcst as cst

from positionpolling.const import PACKAGE_ROOT

if TYPE_CHECKING:
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
    'geometry': ('https://py-geometry-utils.readthedocs.io/en/stable/', None),
    'PIL': ('https://pillow.readthedocs.io/en/stable/', None),
    'python': ('https://docs.python.org/3', None),
    'maybetype': ('https://py-maybetype.readthedocs.io/en/latest/', None),
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
.. |requires-ffmpeg| replace:: Requires FFmpeg; :class:`FileNotFoundError` will be raised if it is not found.
"""

class FFmpegFunctionFinder(cst.CSTVisitor):
    """Node visitor which saves functions that have ``|requires-ffmpeg|`` in their docstrings."""

    METADATA_DEPENDENCIES: ClassVar = (cst.metadata.QualifiedNameProvider,)

    package_root: Path
    current_path: Path | None = None

    def __init__(self, package_name: str | Path) -> None:
        if not (package_name := Path(package_name)).is_absolute():
            raise ValueError(f'{self.__class__.__name__}.package_name must be an absolute path')

        self.package_root: Path = package_name
        self.current_path: Path | None = None
        self.functions: dict[Path, list[str]] = {}

    @classmethod
    def from_files(cls, package_name: str | Path, paths: str | Path | Iterable[str | Path]) -> dict[Path, list[str]]:
        """Searches file contents of ``paths`` for functions whose docstrings contain ``|requires-ffmpeg|``.

        Returns a dictionary mapping the source path to a list of qualified names, all starting with ``package_name``.
        """
        if isinstance(paths, str | Path):
            paths = (paths,)

        visitor = cls(package_name)

        for fp in paths:
            fp = fp if isinstance(fp, Path) else Path(fp)  # noqa: PLW2901
            wrapper = cst.MetadataWrapper(cst.parse_module(fp.read_text('utf-8')))
            visitor.current_path = fp
            wrapper.visit(visitor)

        return visitor.functions

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:  # noqa: D102, N802
        if not self.current_path:
            raise ValueError(f'{self.__class__.__name__}.current_path cannot be None while visiting')

        if (docstring := node.get_docstring()) and ('|requires-ffmpeg|' in docstring):
            module_name: str = '.'.join(self.current_path.relative_to(self.package_root.parent).parts) \
                .replace('.py', '')
            name: str = f'{module_name}.{
                next(iter(cast('set[cst.metadata.QualifiedName]',
                self.get_metadata(cst.metadata.QualifiedNameProvider, node)))).name
            }'

            self.functions.setdefault(self.current_path, []).append(name)

ffmpeg_functions: dict[Path, list[str]] = FFmpegFunctionFinder.from_files(
    PACKAGE_ROOT,
    PACKAGE_ROOT.rglob('*.py'),
)

def source_read(_app: 'Sphinx', docname: str, content: list[str]) -> None:  # noqa: D103
    if docname == 'requires-ffmpeg':
        ffmpeg_list: str = '\n'.join(
            f'* :func:`{fn}`' for _, fns in ffmpeg_functions.items() for fn in fns
        )
        content[0] = content[0].replace('.. function-list-here', ffmpeg_list)

def autodoc_skip_member(  # noqa: D103
        _app: 'Sphinx',
        _obj_type: str,
        name: str,
        obj: object,
        skip: bool,  # noqa: FBT001
        _options: 'Options',
    ) -> bool:
    if name.startswith('__'):
        return not bool(re.search(r'^\s*.. include$', obj.__doc__ or '', flags=re.MULTILINE))

    return skip

def setup(app: 'Sphinx') -> None:  # noqa: D103
    app.connect('source-read', source_read)
    app.connect('autodoc-skip-member', autodoc_skip_member)
