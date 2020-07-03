# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView
from ..util import Object, uno
from ..exception import PRGAInternalError
from collections import OrderedDict
import os
from os import path

__all__ = ['Tester']

# ----------------------------------------------------------------------------
# -- Tester Pass ------------------------------------------------------
# ----------------------------------------------------------------------------
class Tester(Object, AbstractPass):
    """Collecting Verilog rendering tasks.
    
    Args:
        renderer (`FileRenderer`): File generation tasks are added to the specified renderer
        src_output_dir (:obj:`str`): Verilog source files are generated in the specified directory. Default value is
            the current working directory.
        header_output_dir (:obj:`str`): Verilog header files are generated in the specified directory. Default value
            is "{src_output_dir}/include"
        view (`ModuleView`): Generate Verilog source files with the specified view. Currently No use in tester pass
    """

    __slots__ = ['renderer', 'src_output_dir', 'header_output_dir', 'view', 'visited']
    def __init__(self, renderer, rtl_dir, tests_dir, src_output_dir = ".", header_output_dir = None, view = ModuleView.logical):
        self.renderer = renderer
        self.src_output_dir = src_output_dir
        self.tests_dir = os.path.abspath(tests_dir)
        self.rtl_dir = os.path.abspath(rtl_dir)
        self.header_output_dir = os.path.abspath(uno(header_output_dir, os.path.join(src_output_dir, "include")))
        self.view = view
        self.visited = {}
        print(self.rtl_dir)
        if not path.exists(self.tests_dir):
            os.mkdir(self.tests_dir)

    def get_instance_file(self,module):

        instance_files = []

        for temp in itervalues(module.instances):
            instance_files.append(path.join(self.rtl_dir,temp.model.name+".v"))
            instance_files+= self.get_instance_file(temp.model)
        
        return instance_files

    def _process_module(self, module):
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        # This if condition checks if the module is a primitive
        if module.module_class == 0 :
            if not path.exists(path.join(self.tests_dir,"test_" + module.name)):
                os.mkdir(path.join(self.tests_dir,"test_" + module.name))

            # print(module.name)
            # print(f)
            # print(path.join(f,"Makefile"))
            # print(path.join(f,"test.py"))
            setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))
            # print(module.verilog_file)
            self.renderer.add_makefile(module, path.join(f,"Makefile"), getattr(module, "test_makefile_template", "test_base.tmpl"))
            self.renderer.add_python_test(module, path.join(f,"test.py"), getattr(module, "test_python_template", "test_base.tmpl.py"))
            self.renderer.add_python_test(module, path.join(f,"config.py"), "config.py")
       
        for instance in itervalues(module.instances):
            if instance.model.module_class.is_primitive:
                # print(instance)
                # print(instance.name)

                # for x in itervalues(instance.pins):
                #     print(x)
                #     try:
                #         # if x.is_source:
                #         print(NetUtils.get_source(x))
                #     except:
                #         print("Doesnt have a source")
                #     print()


                if 'lut' in instance.name:                    
                    if not path.exists(path.join(self.tests_dir,"test_" + module.name)):
                        os.mkdir(path.join(self.tests_dir,"test_" + module.name))

                    instance_files = self.get_instance_file(module)
                    setattr(module,"files",' '.join(instance_files))
                    
                    setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))

                    self.renderer.add_makefile(module, path.join(f,"Makefile"), "test_base.tmpl")
                    self.renderer.add_python_test(instance, path.join(f,"test.py"), "test_instance_lut.tmpl.py")
                    self.renderer.add_python_test(module, path.join(f,"config.py"), "config.py")
       
                # print(instance.model.module_name)

            self._process_module(instance.model)


    @property
    def key(self):
        return "rtl.verilog"

    @property
    def dependences(self):
        if self.view.is_logical:
            return ("translation", )
        else:
            return ("translation", "materialization")

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context):
        top = context.system_top
        if top is None:
            raise PRGAInternalError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._process_module(top)
