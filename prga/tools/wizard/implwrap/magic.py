# -*- encoding: ascii -*-

import os

def generate_implwrap_magic(summary, design, renderer, f):
    if ((templates_dir := os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))
            not in renderer.template_search_paths):
        renderer.template_search_paths.insert(0, templates_dir)

    renderer.add_generic(f, "magic.tmpl.v",
            design = design,
            summary = summary)
