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
    def __init__(self, rtl_dir, tests_dir, src_output_dir = ".", header_output_dir = None, view = ModuleView.logical):
        self.src_output_dir = src_output_dir
        self.tests_dir = os.path.abspath(tests_dir)
        self.rtl_dir = os.path.abspath(rtl_dir)
        self.header_output_dir = os.path.abspath(uno(header_output_dir, os.path.join(src_output_dir, "include")))
        self.view = view
        self.visited = {}
        if not path.exists(self.tests_dir):
            os.mkdir(self.tests_dir)

    def get_instance_file(self,module):

        instance_files = [path.join(self.rtl_dir,module.name+".v")]

        queue = []

        for temp in itervalues(module.instances):
            queue.append(temp.model)
        
        while len(queue)!=0:
            curr = queue.pop(0)
            curr_file = path.join(self.rtl_dir,curr.name+".v")
            if curr_file not in instance_files:
                instance_files.append(path.join(self.rtl_dir,curr.name+".v"))
            
            for temp in itervalues(curr.instances):
                queue.append(temp.model)
        
            # instance_files+= self.get_instance_file(temp.model)
        
        return instance_files


    def get_heirarchy(self,module):
        heirarchy = []

        # This function must be made recursive
        # Send only the primitive heirarchy
        for instance in itervalues(module.instances):
            temp = self.get_heirarchy(instance.model)
            for x in temp:
                x.insert(0,str(module.name))
                heirarchy.append(x)
        
        # print(heirarchy)
        if len(heirarchy)==0:
            heirarchy.insert(0,[str(module.name)])
        
        return heirarchy
    
    def get_primitives(self,module):
        queue = []
        primitives = []

        # queue.append((module,[str(module.name)]))
        for instance in itervalues(module.instances):
            queue.append((instance,[str(instance.name)]))
        
        while len(queue)!=0 :
            curr_module, heirarchy = queue.pop(0)
            if curr_module.model.module_class.is_primitive:
                primitives.append((curr_module,heirarchy))
                continue

            for instance in itervalues(curr_module.model.instances):
                queue.append((instance,heirarchy+[str(instance.name)]))
        
        return primitives

    def _process_module(self, module):
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        # This if condition checks if the module is a primitive
        # if module.module_class.is_primitive :
        #     if not path.exists(path.join(self.tests_dir,"test_" + module.name)):
        #         os.mkdir(path.join(self.tests_dir,"test_" + module.name))

        print(module.name)
        # print(f)
        # print(path.join(f,"Makefile"))
        # print(path.join(f,"test.py"))

        setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))
        
        # print(module.verilog_file)

        primitives = self.get_primitives(module)
        # for a,b in primitives:
        #     print(a,b)
        # print()
        if len(primitives)!=0:
            # print(module)

            # print(primitives)

            test_dir = path.join(self.tests_dir,"test_" + module.name)

            if not path.exists(test_dir):
                os.mkdir(test_dir)

            # print(module)
            instance_files = ' '.join(self.get_instance_file(module))

            for primitive,heirarchy in primitives:
                # print(primitive)
                # print(heirarchy)
                primitive_test_dir = path.join(test_dir,"test_" + '_'.join(heirarchy))
                if not path.exists(primitive_test_dir):
                    os.mkdir(primitive_test_dir)                
                # print(getattr(primitive, "test_python_template", "test_base.tmpl.py"))
                # Add instances_files for makefile
                # print(instance_files)
                setattr(primitive,"files",instance_files)
                self.renderer.add_makefile(primitive, path.join(primitive_test_dir,"Makefile"), "test_base.tmpl")
                
                # Add heirarchy for python test files
                setattr(primitive,"test_hierarchy",'.'.join(heirarchy)+'.')
                setattr(primitive,"top_level",module.name)
                # print(primitive.test_hierarchy)
                # print(getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
                # print(getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
                # print(primitive.files)
                # print(primitive.test_hierarchy)
                # print(primitive.top_level)
                # print(primitive_test_dir)
                # print()
                self.renderer.add_python_test(primitive, path.join(primitive_test_dir,"test.py"), getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
                
                self.renderer.add_python_test(primitive, path.join(primitive_test_dir,"config.py"), "config.py")
            # print()
        # for instance in itervalues(module.instances):
        #     if instance.model.module_class.is_primitive:
        #         print(instance.name)
        #         if 'lut' in instance.name:
        #             primitives = self.get_primitives(module)
        #             print(primitives)
        #             if not path.exists(path.join(self.tests_dir,"test_" + module.name)):
        #                 os.mkdir(path.join(self.tests_dir,"test_" + module.name))

        #             # print(self.get_heirarchy(module))
        #             instance_files = self.get_instance_file(module)
        #             setattr(module,"files",' '.join(instance_files))
                    
        #             setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))

        #             self.renderer.add_makefile(module, path.join(f,"Makefile"), "test_base.tmpl")
        #             self.renderer.add_python_test(instance, path.join(f,"test.py"), "test_instance_lut.tmpl.py")
        #             self.renderer.add_python_test(module, path.join(f,"config.py"), "config.py")
       
        #         # print(instance.model.module_name)


        # print()

        for instance in itervalues(module.instances):
            self._process_module(instance.model)


    @property
    def key(self):
        return "test.cocotb"

    @property
    def dependences(self):
        if self.view.is_logical:
            return ("translation", )
        else:
            return ("translation", "materialization")

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context, renderer=None):
        top = context.system_top
        self.renderer=renderer
        if top is None:
            raise PRGAInternalError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._process_module(top)
