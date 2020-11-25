# -*- encoding: ascii -*-

from ..util import Object
from ..renderer.renderer import FileRenderer

from abc import abstractmethod

__all__ = []

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Main Entry --------------------------------------
# ----------------------------------------------------------------------------
class AbstractConfigCircuitryEntry(Object):
    """Abstract base class for configuration circuitry entry point."""

    @classmethod
    @abstractmethod
    def new_context(cls):
        """Create a new context.

        Returns:
            `Context`:
        """
        raise NotImplementedError

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        """Create a new file renderer.

        Args:
            additional_template_search_paths (:obj:`Sequence` [:obj:`str` ]): Additional paths where the renderer
                should search for template files

        Returns:
            `FileRenderer`:
        """
        return FileRenderer(*additional_template_search_paths)
