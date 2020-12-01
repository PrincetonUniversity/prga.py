# -*- encoding: ascii -*-

from ...util import Object

class AbstractBitstreamGenerator(Object):
    """Abstract base class for bitstream generators."""

    def generate_verif(self, summary, fasm, output):
        """Generate bitstream for verification purpose."""
        raise NotImplementedError("Cannot generate bitstream for verification purpose")

    def generate_raw(self, summary, fasm, output):
        """Generate raw bitstream."""
        raise NotImplementedError("Cannot generate raw bitstream")
