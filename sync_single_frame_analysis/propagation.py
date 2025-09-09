"""
| Copyright (C) 2020-2025 Jonas Peeck
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Peeck

Description
-----------

Synchronous propagation extension

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from pycpa import options
from pycpa import model
from . import model as sync_model




def default_propagation_method():
    method = options.get_opt('propagation')

    if method == 'jitter_offset':
        return JitterOffsetPropagationEventModel
    elif method == 'busy_window':
        return BusyWindowPropagationEventModel
    elif  method == 'jitter_dmin' or method == 'jitter':
        return JitterPropagationEventModel
    elif method == 'jitter_bmin':
        return JitterBminPropagationEventModel
    elif method == 'optimal':
        return OptimalPropagationEventModel
    else:
        raise NotImplementedError



class SyncPropagationEventModel(model.EventModel):

    def __init__(self, task, task_results, nonrecursive=True):

        # Instrument super constructor
        name = task.in_event_model.__description__ + "_++"
        model.EventModel.__init__(self,name,task.in_event_model.container)
                
        assert isinstance(task.in_event_model,sync_model.SyncSampleEventModel) or isinstance(task.in_event_model,SyncPropagationEventModel)

        # Add general parameters
        self.hyperperiod = task.in_event_model.hyperperiod
        self.P = task.in_event_model.P
        self.B = task.in_event_model.B
        self.phi = task.in_event_model.phi
        self.task = task

        # Calculate propagation based on previous results
        self.busy_times = task_results[task].busy_times
        self.delta_min_base  = list()
        self.delta_plus_base = list()

        # Derive the number of activations from previous task
        self.activations_per_hyperperiod = task.in_event_model.activations_per_hyperperiod

        if len(self.busy_times) == 0:
            for n in range(0,int(self.hyperperiod/self.P)*self.B):
                self.delta_min_base.append(task.in_event_model.deltamin_func(n) + task.bcet)
                self.delta_plus_base.append(task.in_event_model.deltaplus_func(n) + task.wcet)
        else:
            assert len(self.busy_times) == int(self.hyperperiod/self.P)*self.B
            for n in range(0,int(self.hyperperiod/self.P)*self.B):
                self.delta_min_base.append(task.in_event_model.deltamin_func(n) + task.bcet)
                self.delta_plus_base.append(self.busy_times[n])

                assert task.in_event_model.deltamin_func(n) + task.bcet <=  self.busy_times[n]

                

        self.__description__ = "Prop: HP={} P={}".format(self.hyperperiod,self.P)

    def get_activations_per_hyperperiod(self):
        return self.activations_per_hyperperiod

    def deltamin_func(self,n):
        _n = self.activations_per_hyperperiod
        return (self.delta_min_base[n%_n]) + int(n/_n) * self.hyperperiod

    def deltaplus_func(self,n):
        _n = self.activations_per_hyperperiod
        return (self.delta_plus_base[n%_n]) + int(n/_n) * self.hyperperiod

    def eta_min_sy(self,t):        
        return len([n for n in range(0,self.activations_per_hyperperiod) if (self.deltamin_func(n) % self.hyperperiod) <= (t%self.hyperperiod)]) \
               + self.activations_per_hyperperiod*int(t/self.hyperperiod)
    def eta_plus_sy(self,t):
        return len([n for n in range(0,self.activations_per_hyperperiod) if (self.deltaplus_func(n) % self.hyperperiod) <= (t%self.hyperperiod)]) \
               + self.activations_per_hyperperiod*int(t/self.hyperperiod)


    def load(self, accuracy=1000):
        """ Returns the asymptotic load,
        i.e. the avg. number of events per time
        """
        return float(accuracy) / float((float(accuracy)/self.activations_per_hyperperiod)*float(self.hyperperiod))














