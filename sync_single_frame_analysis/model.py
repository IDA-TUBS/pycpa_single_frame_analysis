"""
| Copyright (C) 2020-2025 Jonas Peeck
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Peeck

Description
-----------

Synchronous Event Models

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import math
import logging
import copy
import warnings

from pycpa import model
from pycpa import options
from pycpa import util

INFINITY = float('inf')

logger = logging.getLogger(__name__)


def _warn_float(value, reason=""):
    """ Prints a warning with reason if value is float.
    """
    if type(value) == float:
        warnings.warn("You are using floats, " +
                      "this may yield non-pessimistic results (" +
                      reason + ")", UserWarning)





class SampleEventModel(model.EventModel):

    def __init__(self, sample_period, burst_size_nbr , d_min, jitter = 0, **kwargs):

        self.name = "SampleEventModel"

        model.EventModel.__init__(self, self.name, kwargs)

        self.sample_period = sample_period
        self.burst_size_nbr = burst_size_nbr 
        self.dmin = d_min
        self.J = jitter 

        #self.__description__ = "SampleEventModel"

    def deltaplus_func(self, n):
        if n < 2:
            return 0
        return self.sample_period*math.floor((n-1)/self.burst_size_nbr)+((n-1)%self.burst_size_nbr)*self.dmin + self.J

    def deltamin_func(self,n):
        if n < 2:
            return 0

        if self.burst_size_nbr == 0 or self.sample_period >= INFINITY:
            return 0
        if n == INFINITY:
            return INFINITY

        return max((n-1) * self.dmin, self.sample_period*math.floor((n-1)/self.burst_size_nbr)+((n-1)%self.burst_size_nbr)*self.dmin - self.J)


    def load(self, accuracy=1000):
        """ Returns the asymptotic load,
        i.e. the avg. number of events per time
        """
        # print "load = ", float(self.eta_plus(accuracy)),"/",accuracy
        # return float(self.eta_plus(accuracy)) / accuracy
    
        return float(accuracy) / ( float( (float(accuracy)/(self.burst_size_nbr)) * self.sample_period))
  



class SyncEventModel (model.EventModel):
    """ The event model for the logical execution time programming model.
        It is based on a Period, Jitter and offset parametrization.
    """

    def __init__(self, hyperperiod, P=0, J=0, phi=0, name='sync_em', **kwargs):
        """ Period and offset place the activation into the hyperperiod.
            The Jitter, adds uncertaintiy.
        """
        model.EventModel.__init__(self, name, **kwargs)

        self.set_model(hyperperiod, P,J,phi)

    def set_model(self, hyperperiod, P=0, J=0, phi=0):

        _warn_float(P, "Period")
        _warn_float(J, "Jitter")
        _warn_float(phi, "Offset")

        self.P=P
        self.J=J
        self.phi= phi  % self.P
        self.hyperperiod = hyperperiod

        self.activations_per_hyperperiod = int(self.hyperperiod/self.P)

        assert self.hyperperiod%self.P == 0, "Invalid Period of synchronous task. Not harmonized with the hyperperiod"
        assert self.J%2 == 0
        self.__description__ = "HP={} P={} J={} phi={}".format(hyperperiod,P,J,phi)

    def load(self, accuracy=1000):
        """ Returns the asymptotic load,
        i.e. the avg. number of events per time
        """
        return float(accuracy) / float((float(accuracy)/self.activations_per_hyperperiod)*float(self.hyperperiod))

    def get_activations_per_hyperperiod(self):
        return self.activations_per_hyperperiod

    def deltamin_func(self,n):
        return self.P * n + self.phi - (self.J/2)

    def deltaplus_func(self,n):
        return self.P * n + self.phi + (self.J/2)

    def eta_min_sy(self,t):        
        return len([n for n in range(0,self.activations_per_hyperperiod) if (self.deltamin_func(n) % self.hyperperiod) <= (t%self.hyperperiod)]) \
               + self.activations_per_hyperperiod*int(t/self.hyperperiod)
    def eta_plus_sy(self,t):
        return len([n for n in range(0,self.activations_per_hyperperiod) if (self.deltaplus_func(n) % self.hyperperiod) <= (t%self.hyperperiod)]) \
               + self.activations_per_hyperperiod*int(t/self.hyperperiod)

class SyncSampleEventModel(model.EventModel):
    """ Sample Event Model vor synchronous transmissions """
    def __init__(self, hyperperiod, P=0, Pf=0, B=0, J=0, phi=0, name='sync_sem', **kwargs):
        model.EventModel.__init__(self,name,**kwargs)
        self.set_model(hyperperiod,P, Pf,B,J,phi)

    def set_model(self, hyperperiod,P=0,Pf=0,B=0,J=0,phi=0):

        _warn_float(P, "Period")
        _warn_float(J, "Jitter")
        _warn_float(phi, "Offset")
        _warn_float(B, "NumberOfFragments")
        _warn_float(Pf, "fragment_period")

        self.P=P
        self.J=J
        self.phi= phi  % self.P
        self.B=B
        self.Pf=Pf
        self.hyperperiod = hyperperiod

        self.activations_per_hyperperiod = int(self.hyperperiod/self.P)*B

        assert self.J%2 == 0
        assert self.hyperperiod%self.P == 0, "Invalid Period of synchronous task. Not harmonized with the hyperperiod"
        self.__description__ = "HP={} P={} J={} phi={} B={} Pf={}".format(hyperperiod,P,J,phi,B,Pf)

    def load(self, accuracy=1000):
        """ Returns the asymptotic load,
        i.e. the avg. number of events per time
        """
        return float(accuracy) / float((float(accuracy)/self.activations_per_hyperperiod)*float(self.hyperperiod))

    def get_activations_per_hyperperiod(self):
        return self.activations_per_hyperperiod

    def deltamin_func(self,n,debug = False):
        return self.P * int(n/self.B) + n%self.B * self.Pf + self.phi
        

    def deltaplus_func(self,n, debug = False):
        return self.P * int(n/self.B) + n%self.B * self.Pf + self.phi + self.J

    def eta_min_sy(self,t):
        return len([n for n in range(0,self.activations_per_hyperperiod) if (self.deltamin_func(n) % self.hyperperiod) <= (t%self.hyperperiod)]) \
               + self.activations_per_hyperperiod*int(t/self.hyperperiod)

    def eta_plus_sy(self,t):
        return len([n for n in range(0,self.activations_per_hyperperiod) if (self.deltaplus_func(n) % self.hyperperiod) <= (t%self.hyperperiod)]) \
               + self.activations_per_hyperperiod*int(t/self.hyperperiod)



class SyncTaskChain(object):

    def __init__(self, name, tasks=None):

        # # Name of task chain
        self.name = name

        from . import propagation
        assert not tasks == None
        assert len(tasks) > 0
        assert isinstance(tasks[0].in_event_model, SyncEventModel) or isinstance(tasks[0].in_event_model, propagation.SyncPropagationEventModel)

        # # List of tasks in Path (must be in correct order)
        if tasks is not None:
            self.tasks = tasks
        else:
            self.tasks = list()

    def calculate_chain_wcrt(self,task_results):
        
        hyperperiod = self.tasks[0].resource.scheduler.hyperperiod
        period = self.tasks[0].in_event_model.P
        max_chain_wcrt = 0
        n_val = 0
        for n in range(0,int(hyperperiod/period)):
            sum_n = 0
           
            # Add initial value
            sum_n = self.tasks[0].in_event_model.deltaplus_func(n) - self.tasks[0].in_event_model.deltamin_func(n)

            for t in self.tasks:
                sum_n += task_results[t].busy_times[n] - t.in_event_model.deltaplus_func(n)  
            if sum_n > max_chain_wcrt:
                max_chain_wcrt = sum_n
                n_val = n

        return max_chain_wcrt, n_val


