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
from prga.compatible import *
from itertools import chain
from prga.netlist.net.util import NetUtils

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

        instance_files = [(module,path.join(self.rtl_dir,module.name+".v"))]
        queue = []

        for temp in itervalues(module.instances):
            queue.append(temp.model)
        
        while len(queue)!=0:
            curr = queue.pop(0)
            curr_file = path.join(self.rtl_dir,curr.name+".v")
            if (curr,curr_file) not in instance_files:
                instance_files.append((curr,curr_file))
            for temp in itervalues(curr.instances):
                queue.append(temp.model)

        return instance_files
    
    def get_primitives(self,module):
        queue = []
        primitives = []

        for instance in itervalues(module.instances):
            try:
                queue.append([instance,[str(instance.name)],instance.cfg_bitoffset])
            except:
                queue.append([instance,[str(instance.name)],0])
        
        while len(queue)!=0:
            curr_module, heirarchy,offset = queue.pop(0)

            if curr_module.model.module_class.is_primitive:
                for k,v in iteritems(curr_module.pins):
                    setattr(v,'test_heirarchy','_'.join(heirarchy))
 
                primitives.append([curr_module,heirarchy,offset])

            for instance in itervalues(curr_module.model.instances):
                try:
                    queue.append([instance,heirarchy+[str(instance.name)],offset+instance.cfg_bitcount])
                except:
                    queue.append([instance,heirarchy+[str(instance.name)],offset])
          
        return primitives

    def _process_module(self, module):
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        print(module.name)
        clocks = []
        for x in iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and ipin.model.is_clock):
            if module._allow_multisource:
                source = NetUtils.get_multisource(x)
                if source not in clocks:
                    clocks.append(source) 
            else:
                source = NetUtils.get_source(x)
                if source not in clocks:
                    clocks.append(source)
       
        setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))
        setattr(module,"clocks",clocks)
        
        primitives = self.get_primitives(module)
        setattr(module,"primitives",primitives)
        
        instance_files = []

        instances_data  = self.get_instance_file(module)
        # print(instances_data)
        for instance_model,location in instances_data:
            # instance_files.append(location)
            d = os.path.dirname(path.join(f,instance_model.name+".v"))
            if d:
                makedirs(d)
            os.system('cp '+location+' '+path.join(f,instance_model.name+".v"))
            verilog_file = './'+instance_model.name+'.v '
            if verilog_file not in instance_files:
                instance_files.append('./'+instance_model.name+'.v')

        setattr(module,"files",' '.join(instance_files))
        setattr(module,"top_level",module.name)
        
        self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "module.tmpl.py")
        self.renderer.add_top_level_makefile(module, path.join(f,"Makefile"), "test_base.tmpl")
        self.renderer.add_top_level_python_test(module, path.join(f,"config.py"), "config.py")
        print()

        for instance in itervalues(module.instances):
            self._process_module(instance.model)


    @property
    def key(self):
        return "test.cocotb"

    @property
    def dependences(self):
        if self.view.is_logical:
            return ("translation", "rtl.verilog")
        else:
            return ("translation", "materialization","rtl.verilog")

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
