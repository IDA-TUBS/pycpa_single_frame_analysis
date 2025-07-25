"""
| Copyright (C) 2025 Philip Axer, Jonas Diemer, Johannes Schlatow, Jonas Peeck
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Diemer
         - Philip Axer
         - Johannes Schlatow
         - Jonas Peeck

Description
-----------

Local analysis functions (schedulers)
"""
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import itertools
import math
import logging
import copy

import pandas as pd

from . import analysis
from . import options
from . import model
from . import propagation

logger = logging.getLogger("pycpa")

EPSILON = 1e-9

# priority orderings
prio_high_wins_equal_fifo = lambda a, b : a >= b
prio_low_wins_equal_fifo = lambda a, b : a <= b
prio_high_wins_equal_domination = lambda a, b : a > b
prio_low_wins_equal_domination = lambda a, b : a < b

# new imports...
try:
    from time import process_time as timefunc
except:
    from time import clock as timefunc



class RoundRobinScheduler(analysis.Scheduler):
    """ Round-Robin Scheduler

    task.scheduling_parameter is the respective slot size
    """

    def b_plus(self, task, q, details=None, **kwargs):
        w = q * task.wcet
        # print "q=",q
        while True:
            s = 0
            for ti in task.get_resource_interferers():
                # print "sum+=min(",q,",",ti.in_event_model.eta_plus(w)
                # s += min(q, ti.eta_plus(w))
                if hasattr(task, "scheduling_parameter") and task.scheduling_parameter is not None:
                    s += min(int(math.ceil(float(q) * task.wcet / task.scheduling_parameter)) * ti.scheduling_parameter,
                         ti.in_event_model.eta_plus(w) * ti.wcet)
                else:
                    # Assume cooperative round robin
                    s += ti.wcet * min(q, ti.in_event_model.eta_plus(w))

            # print "w=",q,"+",sum, ", eta_plus(w)=", task.in_event_model.eta_plus(q+sum)
            w_new = q * task.wcet + s

            if w == w_new:
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)

                    for ti in task.get_resource_interferers():
                        if hasattr(task, "scheduling_parameter") and task.scheduling_parameter is not None:
                            if int(math.ceil(float(q) * task.wcet / task.scheduling_parameter)) * ti.scheduling_parameter < ti.in_event_model.eta_plus(w) * ti.wcet:
                                details[str(ti)] = '%d*%d' % \
                                    (int(math.ceil(float(q) * task.wcet / task.scheduling_parameter)),
                                     ti.scheduling_parameter)
                            else:
                                details[str(ti)] = '%d*%d' % (ti.in_event_model.eta_plus(w), ti.wcet)
                        else:
                            details[str(ti)] = "%d*min(%d,%d)=%d*%d" % \
                                (ti.wcet, q, ti.in_event_model.eta_plus(w),
                                 ti.wcet, min(q, ti.in_event_model.eta_plus(w)))
                return w
            w = w_new


class SPNPScheduler(analysis.Scheduler):
    """ Static-Priority-Non-Preemptive Scheduler

    Priority is stored in task.scheduling_parameter,
    by default numerically lower numbers have a higher priority

    Policy for equal priority is FCFS (i.e. max. interference).
    """

    def __init__(self, priority_cmp=prio_low_wins_equal_fifo, ctx_switch_overhead=0, cycle_time=EPSILON):
        """
        :param priority_cmp: function to evaluate priority comparison of the form foo(a,b). if foo(a,b) == True, then "a" is more important than "b"
        :param cycle_time: time granularity of the scheduler, see [Bate1998]_ E.q. 4.14
        :param ctx_switch_overhead: context switching overhead (or interframe space for transmission lines)
        """
        analysis.Scheduler.__init__(self)

        # # time granularity of the scheduler
        self.cycle_time = cycle_time

        # # Context-switch overhead
        self.ctx_switch_overhead = ctx_switch_overhead

        # # priority ordering
        self.priority_cmp = priority_cmp

    def _blocker(self, task):
        # find maximum lower priority blocker
        b = 0
        for ti in task.get_resource_interferers():
            if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter) == False:
                b = max(b, ti.wcet)
        return b

    def spnp_busy_period(self, task, w):
        """ Calculated the busy period of the current task
        """
        b = self._blocker(task) + self.ctx_switch_overhead
        w = max(b, w)

        while True:
            w_new = b
            for ti in task.get_resource_interferers() | set([task]):
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter) or (ti == task):
                    w_new += (ti.wcet + self.ctx_switch_overhead) * ti.in_event_model.eta_plus(w)

            if w == w_new:
                break

            w = w_new

        return w

    def stopping_condition(self, task, q, w):
        """ Check if we have looked far enough
            compute the time the resource is busy processing q activations of task
            and activations of all higher priority tasks during that time
            Returns True if stopping-condition is satisfied, False otherwise
        """

        # if there are no new activations when the current busy period has been completed, we terminate
        if task.in_event_model.delta_min(q + 1) >= self.spnp_busy_period(task, w):
            return True
        return False


    def b_plus(self, task, q, details=None, **kwargs):
        """ Return the maximum time required to process q activations
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        b = self._blocker(task) + self.ctx_switch_overhead

        w = (q - 1) * (task.wcet + self.ctx_switch_overhead) + b

        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = 0
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    s += (ti.wcet + self.ctx_switch_overhead) * ti.in_event_model.eta_plus(w + self.cycle_time)
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))

            w_new = (q - 1) * (task.wcet + self.ctx_switch_overhead) + b + s
            # print ("w_new: ", w_new)
            if w == w_new:

                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    details['blocker'] = str(b)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w + self.cycle_time)) + '*'\
                                + str(ti.wcet) + '=' + str((ti.wcet + self.ctx_switch_overhead) * ti.in_event_model.eta_plus(w + self.cycle_time))
                w += task.wcet
                assert(w >= q * task.wcet)
                return w
            w = w_new


class SPPScheduler(analysis.Scheduler):
    """ Static-Priority-Preemptive Scheduler

    Priority is stored in task.scheduling_parameter,
    by default numerically lower numbers have a higher priority

    Policy for equal priority is FCFS (i.e. max. interference).
    """


    def __init__(self, priority_cmp=prio_low_wins_equal_fifo):
        analysis.Scheduler.__init__(self)

        # # priority ordering
        self.priority_cmp = priority_cmp

    def b_plus(self, task, q, details=None, **kwargs):
        """ This corresponds to Theorem 1 in [Lehoczky1990]_ or Equation 2.3 in [Richter2005]_. """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet

        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = 0
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    s += ti.wcet * ti.in_event_model.eta_plus(w)
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))

            w_new = q * task.wcet + s
            # print ("w_new: ", w_new)
            if w == w_new:
                assert(w >= q * task.wcet)
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w)) + '*'\
                                + str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w))
                return w

            w = w_new





######################################################
######################################################
######################################################
######################################################

class SyncSPPScheduler(SPNPScheduler): 
    """ Logical Execution Time Scheduler
    This scheduler respects the scheduling w.r.t. the activation times in a sporadic schedule.
    For sporadically activated Event Chains, an event propagation is possible
    """

    def __init__(self,_hyperperiod , _spnp=False):
        super().__init__()
        self.hyperperiod = _hyperperiod
        self.spnp = _spnp

        # Synchronous schedules ({scheduling_parameter: sync_schedule, ...}
        self.sync_schedules = dict()
        self.load_schedules = dict()

    def is_sync_task(self,task):
        return isinstance(task.in_event_model, model.SyncEventModel) or \
               isinstance(task.in_event_model, model.SyncSampleEventModel) or \
               isinstance(task.in_event_model, propagation.SyncPropagationEventModel)

    def compute_bcrt(self, task, task_results=None):

        # First decide if to use the sporadic task analysis
        if not isinstance(task.in_event_model, model.SyncEventModel) and \
           not isinstance(task.in_event_model, model.SyncSampleEventModel) and \
           not isinstance(task.in_event_model, propagation.SyncPropagationEventModel):
            return super().compute_bcrt(task, task_results)

        # BCRT = BCET
        bcrt = task.bcet
        if task_results:
            task_results[task].bcrt = bcrt
        return bcrt


    def compute_max_backlog(self, task, task_results, output_delay=0):
        """ Compute the maximum backlog
        """

        # First decide if to use the sporadic analysis
        if not isinstance(task.in_event_model, model.SyncEventModel) and \
           not isinstance(task.in_event_model, model.SyncSampleEventModel) and \
           not isinstance(task.in_event_model, propagation.SyncPropagationEventModel):
            return super().compute_max_backlog(task, task_results,output_delay)

        # TODO change this for sync calculation! Note: also for network packets! General formalization
        return 1


    # TODO to be implemented
    def stopping_condition_sync(self, task, n, wcrt):
        """ Stop if the jitter of the outgoing event exeeds the hyperperiod 
            or if w exeeds the hyperperiod  (indicator for non-scheduleability) """

        if task.in_event_model.delta_plus(n) - task.in_event_model.delta_min(n) >= self.hyperperiod:
            return True

        if wcrt >= self.hyperperiod:
            return True

        return False




    def compute_wcrt(self, task, task_results=None):
        """ Compute the worst-case response time of a synchronous task for all n-events and for each n-th acitvation individually.
            Call the sporadic method if the event model is sporadic
        """
        
        print("compute_wcrt for task {} on resource {}".format(task.name,task.resource.name))

        # If not a synchronous task, then use classic sporadic wcrt analysis
        if not self.is_sync_task(task):
            return super().compute_wcrt(task, task_results)

        # ---> Synchronous WCRT computation method 
        max_iterations = options.get_opt('max_iterations')
        logger.debug('compute wcrt of %s' % (task.name))

        # --- Initialize values ---
        wcrt = 0 
        
        # # n value corresponding to the wcrt
        n_wcrt = 0
        start = timefunc()
        b_wcrt = dict()
        # Empty the busy times lsit
        task_results[task].busy_times = []

        # TODO implement more asserts

        # Iterate through all n activations
        for n in range(0,task.in_event_model.get_activations_per_hyperperiod()):
            elapsed = timefunc() -start
            if elapsed > options.get_opt('timeout'):
                raise TimeoutException("Timeout reached in compute_wcrt at n=%d" % (n))
            
            logger.debug('iteration for n=%d' %(n))

            # w: maximum busy times for the n-th activation within the hyperperiod
            # synchronous busy time is the latest time in the schedule, where the task can terminate. This should be increasing!
            # synchronous wcrt
            w_abs_end = self.b_plus_sy(task, n,details=b_wcrt, task_results=task_results)
            assert w_abs_end >= 0
            
            _wcrt_candidate = w_abs_end - task.in_event_model.deltaplus_func(n)
            assert _wcrt_candidate >= 0

       


            if task_results:
                logger.debug('setting results %d', w_abs_end)
                # Add n-th value to tasks busy times (Propagated function)
                task_results[task].busy_times.append(w_abs_end) # Definition: Ab delta_plus Wert

            if  _wcrt_candidate > wcrt:
                wcrt  = _wcrt_candidate
                n_wcrt = n

            # Check stop condition
            if self.stopping_condition_sync(task, n, wcrt) == True:
                break

        if task_results:
            task_results[task].q_wcrt = n_wcrt
            task_results[task].wcrt = wcrt
            task_results[task].b_wcrt = b_wcrt

        # --------------- Print out the current busy times -------------
        #print("------------------------------------------------------------")
        #print("--- Busy times of synchronous task " + str(task.name) + " ---")
        for i in range(0,len(task_results[task].busy_times)):
            if i < 10:
                print("n: " + str(i) + ": " + str(task_results[task].busy_times[i]) + " - " + str(task.in_event_model.deltaplus_func(i))) # TODO den startzeitstempel mit rein (delta +)....
            #if i  > 0: #len(task_results[task].busy_times) - 1:
            #    assert task_results[task].busy_times[i-1] < task_results[task].busy_times[i]


        assert wcrt >= task.wcet
        return wcrt






    def b_plus_sy(self, task,n, details=None,debug=False,**kwargs):     

        #return self.caluclate_busy_window(task,n,debug=False) #raus!
        # First get the load schedule:
        # Only calculate one schedule!
        sy_schedule = self.calculate_sy_schedule(task.resource, task.scheduling_parameter, debug = debug)
        load_schedule = self.calculate_load_schedule(task.resource, task.scheduling_parameter)

        dplus_startin_point_value = task.in_event_model.deltaplus_func(n)

        row_index = self.get_load_block_from_schedule_by_ts(load_schedule,dplus_startin_point_value)
        
        assert not row_index == None
        

        row = load_schedule.loc[row_index]

        
        # Get the maximum busy window of the task
        task_dict = row["dplus_tasks"]
        
        assert task in task_dict
        response_time = task_dict[task]
            

        assert not response_time == None
        assert response_time >= 0

            
        return dplus_startin_point_value + response_time ### TODO auskommentieren um code unten schnell zu prüfen






    def get_resource_interferers_and_itself(self, task):
        """ returns the set of tasks sharing the same Resource as Task ti
            excluding ti itself
        """
        if task.resource is None:
            return []
        interfering_tasks = copy.copy(task.resource.tasks)
        return interfering_tasks


    


    # --- Helper functions ---
    # Calculate mixed bet let starting at certain point in hp
    # n: related to the delta reference time of the task
    def calculate_mixed_busy_window(self, sy_schedule, starting_point, task, delta_reference_time, n, debug = False):
  
   
        # Sanity checks
        assert not sy_schedule == None
        
        if not (task.in_event_model.deltaplus_func(n) %self.hyperperiod) == (delta_reference_time % self.hyperperiod):
            #print("assertion")
            #print(n)
            #print(task.name)
            #print(task.in_event_model.deltaplus_func(n) )
            #print(delta_reference_time)
            #print(task.in_event_model.deltaplus_func(n) %self.hyperperiod)
            #print(delta_reference_time % self.hyperperiod)
            #self.print_schedule_sorted(sy_schedule,debug=True) #, limit = 100)
           # print(self.get_block_from_schedule_by_ts(schedule,delta_reference_time))
            pass
        
        #assert task.in_event_model.deltaplus_func(n) %self.hyperperiod == delta_reference_time % self.hyperperiod # TODO rein!??! work here
        assert abs(task.in_event_model.deltaplus_func(n) %self.hyperperiod) - (delta_reference_time % self.hyperperiod) < 0.1
        
        
        
        assert starting_point <= delta_reference_time
            
            
        # ---> Calculate the same priority load <---
        
        # Get initial load from schedule
        starting_point_schedule_load = self.get_schedule_value_at(sy_schedule,starting_point)
        
        
        arriving_sync_load = 0
        
        # Sum up the synchronous load
        for ti in self.get_resource_interferers_and_itself(task):
            
            if not self.is_sync_task(ti):
                continue
                
            arriving_sync_load = arriving_sync_load + ti.wcet * (ti.in_event_model.eta_min_sy(delta_reference_time) - ti.in_event_model.eta_min_sy(starting_point))
            
        # Substract own load
        own_load_FIFO_reduction = (task.in_event_model.eta_min_sy(task.in_event_model.deltaplus_func(n)) - task.in_event_model.eta_min_sy(task.in_event_model.deltamin_func(n))) * task.wcet
        

        # also substract the own load once due to SPNP scheduling
        sync_load = starting_point_schedule_load - task.wcet + arriving_sync_load - own_load_FIFO_reduction
        
        if sync_load < 0:
            #print("ASSERTION!")
            #print("starting_point: " + str(starting_point))
            #print("starting_point_schedule_load: " + str(starting_point_schedule_load))
            #print("arriving_sync_load: " + str(arriving_sync_load))
            #print("own_load_FIFO_reduction: " + str(own_load_FIFO_reduction))
            #print("delta_reference_time: " + str(delta_reference_time))
            #print("n:" + str(n))
            #print(task)
            #self.print_schedule_sorted(sy_schedule,debug=True) #, limit = 100)
            #print(sy_schedule)
            #print()
            pass
        
 
        #print(sync_load)
        if sync_load < 0 and abs(sync_load) < 0.1:
            sync_load = 0
        assert sync_load  >= 0
        #sync_load += task.wcet
        
        assert sync_load >= 0 

       # Lower priority Load
        #lp_blocker = 0
        #if self.spnp:
        #    for ti in task.get_resource_interferers():
        ##        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter) == False:
        #             lp_blocker = max(lp_blocker, ti.wcet)

        
        # Sporadic load and busy window
        
        w = sync_load
        
        while True:
            
            sp = 0
            

            for ti in self.get_resource_interferers_and_itself(task): # FIFO for task itself!
            
                # Synchronous load: Sum up the load until the delta_reference_time
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                                
                    if not self.is_sync_task(ti):
                        sp += ti.wcet * ti.in_event_model.eta_plus(w + 1) # XXX scheduling granularity

                    
            # TODO cycletime
            
            w_new = sync_load + sp
            
            assert w_new >= w
            if w_new == w:
                return w
                
            w = w_new



######################################################################################################################################
######################################################################################################################################
######################################################### work here ##################################################################
######################################################################################################################################
######################################################################################################################################



    # TODO numpy command?
    def get_block_from_schedule_by_ts(self, schedule, ts):
        _ret = [block for block in schedule if block[0] == ts]
        assert len(_ret) <= 1
        # Retrun None, if there is no corresponding block to ts
        if len(_ret) == 0:
            return None
        # Return the block otherwise (assumptions there is always only one block)
        assert len(_ret) == 1
        return _ret[0]
 


    # TODO intermedierende blöcke (die jetzt ja nicht mehr direkt im schedule mit drin sind, durch einbeziehung von prae und post lock der umliegenden blöcke kompensieren
    def get_schedule_value_at(self, schedule, _ts):

        assert len(schedule) >= 2
        
        ts = _ts%self.hyperperiod

        # Return if there is a block at _ts which contains the requested value
        matched_block = self.get_block_from_schedule_by_ts(schedule,ts)
        if not matched_block == None:
            return matched_block[4]

        # XXX This part of the code is never reached by the current implementation

        # Otherwise get preceeding and successing blocks (prae/post)
        _prae = None
        _post = None
        for block in schedule:
            # prae part
            if _prae == None:
                _prae = block
            elif _prae[0] > ts and block[0] < ts:
                _prae = block
            elif _prae[0] < ts and block[0] > _prae[0] and block[0] < ts:
                _prae = block
            elif _prae[0] > ts and block[0] > _prae[0]:
                _prae = block

            # post part
            if _post == None:
                _post = block
            elif _post[0] < ts and block[0] > ts:
                _post = block
            elif _post[0] > ts and block[0] < _post[0] and block[0] > ts:
                _post = block
            elif _post[0] < ts and block[0] < _post[0]:
                _post = block

        # Do the math including modolo
        # Block value (0-4): [ts, prae_locked, post_locked, load_arrival_at_ts, current_load]
        distance = (_post[0]-_prae[0])%self.hyperperiod
        ts_distance = (ts-_prae[0])%self.hyperperiod
        m = (_post[1]-_prae[4])/distance
        return _prae[4] + m*ts_distance # m is either 0 or negative value






    def return_raw_block_at(self, tasks, ts, _n):
        ''' This method returns a raw block containing the unchangeable parameters prae and post locked load and load arrival at ts '''
        # Return: [ts, prae_locked, post_locked, load_arrival_at_ts, current_load]

        prae_locked = 0
        post_locked = 0
        arrival = 0
        d_plus_tasks = dict()
        d_plus_min_n_task_value = dict()
        
        for ti in tasks:
            for n in range(0,ti.in_event_model.get_activations_per_hyperperiod()):

                d_min  =  ti.in_event_model.deltamin_func(n)%self.hyperperiod
                d_plus =  ti.in_event_model.deltaplus_func(n)%self.hyperperiod
                    
                # Post
                if (ts >= d_min and ts < d_plus):
                    post_locked += ti.wcet
                elif ts < d_min and ts < d_plus and d_min > d_plus:
                    post_locked += ti.wcet
                elif ts >= d_min and ts > d_plus and d_min > d_plus:
                    post_locked += ti.wcet

                # Prae
                if (ts > d_min and ts <= d_plus):
                    prae_locked += ti.wcet
                elif ts < d_min and ts <= d_plus and d_min > d_plus:
                    prae_locked += ti.wcet
                elif ts > d_min and ts > d_plus and d_min > d_plus:
                    prae_locked += ti.wcet

                # Arrival
                if d_min == ts:
                    arrival += ti.wcet
                    
               # d_plus tasks
                if d_plus == ts:
                
                    if ti in d_plus_min_n_task_value:
                        d_plus_min_n_task_value[ti].append(n)
                    else:
                        d_plus_min_n_task_value[ti] = [n]
                        
                        
                        
                    #d_plus_min_n_task_value[ti] = [_n]
                    d_plus_tasks[ti] = None
                    
                    
        # Only current_load is set to 0, as it depends from the schedule
        #load_schedule = pd.DataFrame(columns= ["timestamp" , "prae_locked" , "post_locked" , "load_arrival_at_ts" , "current_load", "time_mixed", "time_mixed_load_value", "dplus_tasks","n"])
        _raw_block = [ts, prae_locked, post_locked, arrival, 0, 0 , 0,d_plus_tasks, d_plus_min_n_task_value] # TODO nicht benötigte parameter raus

        return _raw_block




    def get_load_block_from_schedule_by_ts(self, schedule, ts):
    
        value = schedule[schedule['timestamp'] == (ts%self.hyperperiod)].index 
        
        if len(value) == 0:
            return None
         
        return value[0]
        

    def calculate_load_schedule(self, resource, scheduling_parameter):
        
        """ Calculate or updates the schedule
        """
        if not scheduling_parameter in self.load_schedules:
            self.load_schedules[scheduling_parameter] = None
        return self.load_schedules[scheduling_parameter]

        # TODO work here



    def get_next_value(self, sy_schedule, current_ts):
    
    
        # first get the minimum:
        minimum_value = sy_schedule[0][0]
        one_above_value = None
        
        
        
        for i in range(0,len(sy_schedule)):
        
            if sy_schedule[i][0] < minimum_value:
                minimum_value = sy_schedule[i][0]
                
            if one_above_value == None:
                if sy_schedule[i][0] > current_ts:
                    one_above_value = sy_schedule[i][0]
            else:
                if sy_schedule[i][0] > current_ts and sy_schedule[i][0] < one_above_value:
                    one_above_value = sy_schedule[i][0]
        
        
        
        if one_above_value == None:
            return minimum_value
        return one_above_value
        
        
        
        
    
        
        
        
        
                
        



    # Calculate the schedule 
    # TODO switch to numpy matrix representation
    def calculate_sy_schedule(self, resource, scheduling_parameter, debug = False):

        if scheduling_parameter in self.sync_schedules:
            if not self.sync_schedules[scheduling_parameter] == None:
                return self.sync_schedules[scheduling_parameter]

    #    print("calculate_sy_schedule() for resource" + str(resource) + " with priority " + str(scheduling_parameter))
        
        sy_schedule = []

        # First generate blocks for all dmin (activations)
        interfering_tasks = [ti for ti in resource.tasks if self.priority_cmp(ti.scheduling_parameter, scheduling_parameter) and self.is_sync_task(ti)]

        assert len(interfering_tasks) > 0
        
        # Then generate two blocks per task activation n: one for d_min(n) and one for d_plus(n)
        for ti in interfering_tasks:
            for n in range(0,ti.in_event_model.get_activations_per_hyperperiod()):
                d_min  =  ti.in_event_model.deltamin_func(n)  % self.hyperperiod
                d_plus =  ti.in_event_model.deltaplus_func(n) % self.hyperperiod
                
                d_min_block = self.get_block_from_schedule_by_ts(sy_schedule, d_min)
                if d_min_block == None:
                    d_min_block = self.return_raw_block_at(interfering_tasks,d_min,n)
                    sy_schedule.append(d_min_block)

                d_plus_block = self.get_block_from_schedule_by_ts(sy_schedule, d_plus)
                if d_plus_block == None:
                    d_plus_block = self.return_raw_block_at(interfering_tasks,d_plus,n)
                    sy_schedule.append(d_plus_block)
                else:
                    d_plus_block[7][ti] = None
                    d_plus_block[8][ti].append(n)
                        

                #if debug:
                 #   print("dplus: " + str(d_plus) + "; n: " + str(n))
                 #   print("row  : " + str(_block)) 
                    

        # Next, iterate over the schedule until it converges
        # Start at fist activation
        start_ts = 0


        current_block = sy_schedule[0]
        current_ts = current_block[0]

        # Init current load and hyperperiod iteration counter (break condition)
        current_block[4] = current_block[3]
        hyperperiod_iteration  = 0
        
        inter_blocks = list()
        delete_blocks = list()
       # print(str(len(sy_schedule)) + " blocks generated")
        
        i = 0
        while True:
            i = i + 1
            
            if i%1000==0:
                print("(" + str(i) + "/" + str(len(sy_schedule)) + ")")
            
            # TODO get the next value!!!!
            next_ts = self.get_next_value(sy_schedule,current_ts)

            # Get the corresponding block
            next_block = self.get_block_from_schedule_by_ts(sy_schedule, next_ts)
                
            # Then calculate the time behaviour until the next block time and add it to the next block
            # First get the time difference between the blocks
            time_diff = (next_ts - current_ts)%self.hyperperiod

            # Next calculate the processing of unlocked current_block load
            unlocked_load = current_block[4] - current_block[2] # current_load - post lock
            rest_unlocked = unlocked_load - time_diff # load which cannot be processed until the next block

            # Store the current value of the load value at the next block for the break condition
            temp_next_block_load = next_block[4]

            # Update load at next block
            if rest_unlocked < 0:
                next_block[4] = current_block[2] + next_block[3]
            else:
                next_block[4] = current_block[4] - time_diff + next_block[3]




            if current_ts > next_ts:
                hyperperiod_iteration = hyperperiod_iteration + 1

            if hyperperiod_iteration == 3:
                break
                


            current_block = next_block
            current_ts = next_ts
            
        # Add the sy_schedule to the dict
        self.sync_schedules[scheduling_parameter] = sy_schedule
        
        
        
        # ---------- replace this above with new code -----------------
        # -------------------------------------------------------------
        # Convert the schedule to pandas 
        load_schedule = pd.DataFrame(columns= ["timestamp" , "prae_locked" , "post_locked" , "load_arrival_at_ts" , "current_load", "time_mixed", "time_mixed_load_value", "dplus_tasks","n"])
        
        current_line = 0
        for i in range(0,len(sy_schedule)):
            
            current_block = sy_schedule[i]
            
            load_schedule.loc[current_line] = current_block
            
            
            current_line = current_line + 1
            
        load_schedule = load_schedule.sort_values(by=['timestamp'], ascending=True)
        load_schedule = load_schedule.reset_index(drop=True)
         
      #  print("new load_schedule for resource: " + str(resource))
        self.load_schedules[scheduling_parameter] = load_schedule
        
       
        # TODO iterate only over the first and the last schedule value
        # TODO oder hier ggf alle werte die in frage kommen...
        # TODO das hier nicht mehr machen wenn das load schedule schon besteht!
        interfering_tasks = [ti for ti in resource.tasks if self.priority_cmp(ti.scheduling_parameter, scheduling_parameter) and self.is_sync_task(ti)]
        
        t_count = 1
        
        for ti in interfering_tasks:
        
            #print(ti.name)
           # print("Task number: " + str(t_count) + "/" + str(len(interfering_tasks)))
            t_count += 1
         
            
            # Calculate all values: O(n2) complexity...
            for n in range(0, int(ti.in_event_model.get_activations_per_hyperperiod())):
        
                n_delta_plus = ti.in_event_model.deltaplus_func(n)
                n_index_in_schedule = self.get_load_block_from_schedule_by_ts(load_schedule, n_delta_plus)
                self.calculate_range_values(load_schedule, n_index_in_schedule, sy_schedule)
         
                
         
                if n%60 == 0:
                    print("n: " + str(n))
        
            
        
       # print("SY SCHEDULE")
        self.print_schedule_sorted(sy_schedule,debug=True,limit=200)
        for index, row in load_schedule.iterrows():
        
            for task in row['dplus_tasks']:
                busy_value = row['dplus_tasks'][task]
                if busy_value == None:
                    #self.print_load_schedule(load_schedule, debug = False)
                    #print("Index: " + str(index))
                    #print(row)
                    pass
                assert not busy_value == None
                  
                if busy_value < 0:
                    #print(busy_value)
                    #print(row)
                    pass
                assert busy_value >= 0
                
                
        
        return sy_schedule



    # Calculates the critical instant starting from this block
    def calculate_range_values(self, load_schedule, delta_plus_block_index, sy_schedule): 
        # delta_plus_block_index: The index to start the critical instant from
        
        counter = 0
        
        # Get the data from the block
        row = load_schedule.loc[delta_plus_block_index]
        delta_plus_starting_time = row["timestamp"]
        load_schedule_value = row["current_load"]
            
            
        comp_diff = 0
        iterate = 0
        while True:
        
            #print(iterate)
            iterate += 1
            # Iterate over the next delta values
            comp_index = (delta_plus_block_index + comp_diff)%len(load_schedule)
            comp_row = load_schedule.loc[comp_index]
                
            # Only evaluate blocks with delta plus nodes
            if len(comp_row['dplus_tasks']) == 0:
                comp_diff = comp_diff + 1
                continue
                
                
            comp_delta_plus_starting_time = comp_row["timestamp"]
            time_difference = (comp_delta_plus_starting_time - delta_plus_starting_time)% self.hyperperiod
            

            
            
            dplus_tasks = comp_row['dplus_tasks']
            
            
            
            breaking_condition = False
            for key in dplus_tasks:
                task = key    
                
                assert not task == None
                
                # Now calculate the complete mixed busy window for that comparision block and check if it is the most critical
            
                # First substract own load interferers
                w = load_schedule_value
                counter+=1
                n = comp_row['n'][task][0]
                
                # TODO bei mehreren task werten: schaue welcher n wert matched!
                n_list = comp_row['n'][task]
                store_n = None
                for _n_val in n_list:
                    temp_time = task.in_event_model.deltaplus_func(_n_val)
                    if temp_time %self.hyperperiod == (delta_plus_starting_time + time_difference) % self.hyperperiod:
                        store_n = _n_val
                    elif abs(temp_time %self.hyperperiod - ( (delta_plus_starting_time + time_difference) % self.hyperperiod)) < 0.1:
                        store_n = _n_val
                        
               # if store_n == None:
               #     print(n_list)
               #     print(temp_time)
               #     print(task.in_event_model.deltaplus_func(_n_val))
               #     print((delta_plus_starting_time + time_difference) % self.hyperperiod)
                        
                assert not store_n == None
                
                new_w = self.calculate_mixed_busy_window(sy_schedule, delta_plus_starting_time, task, delta_plus_starting_time + time_difference, store_n)  #n)
                
                response_time = new_w - time_difference + task.wcet
                
                if response_time <= 0:
                    breaking_condition = True
                    break
                    
                if dplus_tasks[task] == None:
                    if response_time >= 0:
                        dplus_tasks[task] = response_time
                else:
                    if dplus_tasks[task] < response_time:
                        dplus_tasks[task] = response_time
                        
                        
                        
                        
            if breaking_condition:
                break
                

            comp_diff = comp_diff + 1
        
    def check_load_schedule(self, load_schedule):
        # TODO replace the load schedule and stick to numpy
        for index, row in load_schedule.iterrows():
        
            if len(row['dplus_tasks']) > 1:
            
            
            
                for task in row['dplus_tasks']:
                    value = row['dplus_tasks'][task]
                    
                    assert not value == None
                    assert value > 0
                    
        
    def print_load_schedule(self, load_schedule, debug = True):
    
        return
    
        print("--- print load schedule ---")
    
        for index, row in load_schedule.iterrows():
        
            if index > 20 and debug:
                continue
        
            print(str(index) + "  " + str(row['timestamp']) + "  " + str(row['prae_locked']) + "  " + str(row['post_locked']) + "   " + str(row['load_arrival_at_ts']) + "    " + str(row['current_load']) + "    " + str(row['dplus_tasks']) + "  " + str(row['n']))


    def sort_schedule(self,sy_schedule):
    
        # TODO do this with numpy
    
        sorted_schedule = None
    
        return sorted_schedule

    # TODO implement one highly configurable print method
    def print_schedule_sorted(self, sy_schedule, interferers=None, debug = False, limit = None):
        if not debug:
            return

        #print("-----------------------------------------")

        if not interferers == None:
            scheduling_parameter = max(ti.scheduling_parameter for ti in interferers)
            print("Print schedule for scheduling parameter " + str(scheduling_parameter))

        start_ts = -1

        print_count = 0

        while(1):
            current_ts = self.hyperperiod
            current_el = None
            for el in sy_schedule:
                if el[0] < current_ts and el[0] > start_ts:
                    current_ts = el[0]
                    current_el = el

            start_ts = current_ts
            print_count+=1;
            
            

            if not limit == None:
                if print_count == limit:
                    break

            if current_el == None:
                break

        print("-----------------------------------------")

        #[[ts,prae_locked,post_locked,load_arrival_at_ts,current_load,native/inter],[...],...] 

    # TODO implement one deep sanity check method
    def check_schedule_sanity(self,sy_schedule):

        start_ts = -1
        previous_el = None
        first_el = None
        sane_schedule = True

        while(1):

            current_ts = self.hyperperiod
            current_el = None
            for el in sy_schedule:
                if el[0] < current_ts and el[0] > start_ts:
                    current_ts = el[0]
                    current_el = el

            start_ts = current_ts
  
            # Store the first element
            if first_el == None:
                first_el = current_el
            if current_el == None:
                break

            # Check sanity here
            if not previous_el == None:

                # Check time difference here
                time_diff = current_el[0] - previous_el[0]
                assert time_diff > 0
   
                start_load = previous_el[4]
                end_load =   current_el[4]

                if start_load - end_load > time_diff and False:
                    sane_schedule = False
                    print("Sanity condition violated for two subsequent blocks in the schedule")
                    #print(previous_el)
                    #print(current_el)
                    break
                
            previous_el = current_el

            if current_el == None:
                break

        # TODO Sanity check between last and first element



        if not sane_schedule:
            self.print_schedule_sorted(sy_schedule, debug=True)

            assert sane_schedule



# ========================================================================================
# ========================================================================================
# ========================================================================================
# ========================================================================================
# ========================================================================================


               


class SPPSchedulerActivationOffsets(SPPScheduler):
    """ Static-Priority-Preemptive Scheduler which considers activation offsets assuming
        all tasks are activated synchronously with the given offsets/phases (phi).

        Assumptions:
            * implicit or constrained deadlines

        We exclude/shift interferers whose phase is larger than the task under analysis iff the interferers period is
        equal or smaller.
    """


    def __init__(self, priority_cmp=prio_low_wins_equal_fifo):
        SPPScheduler.__init__(self, priority_cmp)

    def b_plus(self, task, q, details=None, **kwargs):
        """ This corresponds to Theorem 1 in [Lehoczky1990]_ or Equation 2.3 in [Richter2005]_. """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet

        while True:
            s = 0
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    if hasattr(ti.in_event_model, 'P') and hasattr(task.in_event_model, 'P') and \
                        ti.in_event_model.P <= task.in_event_model.P and \
                        task.in_event_model.P % ti.in_event_model.P == 0:
                            diff = task.in_event_model.phi - ti.in_event_model.phi
                    else:
                        diff = ti.in_event_model.J

                    s += ti.wcet * ti.in_event_model.eta_plus(w + diff)

            w_new = q * task.wcet + s
            if w == w_new:
                assert(w >= q * task.wcet)
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            if hasattr(ti.in_event_model, 'P') and hasattr(task.in_event_model, 'P') and \
                                ti.in_event_model.P <= task.in_event_model.P and \
                                task.in_event_model.P % ti.in_event_model.P == 0:
                                    diff = task.in_event_model.phi - ti.in_event_model.phi
                            else:
                                diff = ti.in_event_model.J

                            details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w+diff)) + '*'\
                                + str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w+diff))
                return w

            if q > 1:
                logger.warning("Using SPPSchedulerActivationOffset() with deadline > period (task %s)." % (task))

            w = w_new

class CorrelatedDeltaMin(model.EventModel):
    """ Computes the correlated event model :math:`\delta^-_j` from Lemma 2 in [Rox2010]_.
    """
    def __init__(self, em, m, offset):
        model.EventModel.__init__(self, 'tmp')

        self.em = em
        self.m = m
        self.offset = offset

    def deltamin_func(self, n):
        if n <= self.m:
            return self.em.deltamin_func(n)
        elif n == self.m + 1:
            return max(self.em.deltamin_func(n), self.offset)
        else:
            return max(self.em.deltamin_func(n), self.offset + self.em.deltamin_func(n - self.m))

    def deltaplus_func(self, n):
        return self.em.deltaplus_func(n)

class SPPSchedulerCorrelatedRox(SPPScheduler):
    """ SPP scheduler with dmin correlation.
        Computes the approximate response time bound as presented in [Rox2010]_.
    """

    def get_dependent_tasks(self, task):
        return task.get_resource_interferers()

    def b_plus_idle(self, task, q, details=None, task_results=None):
        """ Implements Case 2 in [Rox2010]_.
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet
        while True:
            details.clear()
            details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)

            idle_intrf = 0
            idle_details = dict()

            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)

                    idle_intrf += ti.wcet * ti.in_event_model.eta_plus(w-ti.in_event_model.correlated_dmin(task))
                    idle_details[str(ti)+':eta*WCET'] = str(ti.in_event_model.eta_plus(w-ti.in_event_model.correlated_dmin(task))) + '*' +\
                            str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w-ti.in_event_model.correlated_dmin(task)))

            w_new = q * task.wcet + idle_intrf
            for d in idle_details.keys():
                details[d] = idle_details[d]

            if w == w_new:
                break
            w = w_new

        assert(w >= q * task.wcet)
        return w

    def b_plus_busy(self, task, q, details=None, task_results=None):
        """ Implements Case 1 in [Rox2010]_.
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet
        while True:
            details.clear()
            details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)

            busy_intrf = 0
            busy_details = dict()

            interferers = set()
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    interferers.add(ti)

            for ti in interferers:

                # ti starts busy window -> iterate candidates of task's first arrival
                qmax = len(task_results[ti].busy_times)
                for q in range(1, qmax):
                    intrf = 0
                    intrf_details = dict()
                    a0 = ti.in_event_model.delta_min(q) + task.in_event_model.correlated_dmin(ti)

                    for tj in interferers:
                        if tj is ti:
                            mj = q
                        else:
                            mj = tj.in_event_model.eta_plus(a0 - task.in_event_model.correlated_dmin(ti))

                        em = CorrelatedDeltaMin(tj.in_event_model, mj, a0 + tj.in_event_model.correlated_dmin(task))
                        intrf += tj.wcet * em.eta_plus(w + a0)
                        intrf_details[str(tj)+':eta*WCET'] = str(em.eta_plus(w+a0)) + '+' + str(tj.wcet) +\
                                '=' + str(tj.wcet * em.eta_plus(w + a0))

                    intrf -= a0
                    intrf_details[str(ti)+':offset'] = str(a0)

                    if intrf > busy_intrf:
                        busy_intrf = intrf
                        busy_details = intrf_details

            w_new = q * task.wcet + busy_intrf
            for d in busy_details.keys():
                details[d] = busy_details[d]

            if w == w_new:
                break
            w = w_new

        assert(w >= q * task.wcet)
        return w

    def b_plus(self, task, q, details=None, task_results=None):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        idle_details     = dict()
        idle_intrf = self.b_plus_idle(task, q, idle_details, task_results)

        busy_details     = dict()
        busy_intrf = self.b_plus_busy(task, q, busy_details, task_results)

        if idle_intrf > busy_intrf:
            w = idle_intrf
            if details is not None:
                for d in idle_details.keys():
                    details[d] = idle_details[d]
        else:
            w = busy_intrf
            if details is not None:
                for d in busy_details.keys():
                    details[d] = busy_details[d]

        return w

class SPPSchedulerCorrelatedRoxExact(SPPScheduler):
    """ SPP scheduler with dmin correlation based on [Rox2010]_.
        This is the exact version which performs an extensive search of busy window candidates.
    """

    def calculate_w(self, task, sequence, details=None):
        w = 0
        q_cur = 0
        a0 = 0
        for ti, a in sequence:
            w += ti.wcet

            if details is not None:
                details[str(ti)+':'+str(a)] = str(ti.wcet)

            if ti is task:
                q_cur += 1
                if q_cur == 1:
                    a0 = a

        return w, a0, q_cur

    def find_candidates_recursive(self, task, q, interferers, sequence):

        w, a0, q_cur = self.calculate_w(task, sequence)

        if q > q_cur:
            interferers.add(task)
        elif task in interferers:
            interferers.remove(task)

        worst_sequence = sequence
        if q > q_cur:
            worst_rt = 0
        else:
            worst_rt = w - a0

        # place further activations and find maximum w
        for ti in interferers:
            w_new = 0
            new_sequence = list(sequence)
            if len(new_sequence):
                last_t, last_a = new_sequence[-1]
                d_i = last_a + ti.in_event_model.correlated_dmin(last_t)
                dmin = last_a

                k = 0
                for (tj, a) in new_sequence:
                    if tj is ti:
                        if k == 0:
                            first_a = a

                        dmin = first_a + ti.in_event_model.delta_min(2 + k)
                        k += 1

                next_a = max(dmin, d_i)
                if next_a <= w:
                    new_sequence.append( (ti, next_a) )
                    new_sequence = self.find_candidates_recursive(task, q, set(interferers), new_sequence)
            else:
                new_sequence.append((ti, 0))
                new_sequence = self.find_candidates_recursive(task, q, set(interferers), new_sequence)

            w_new, a0, q_cur = self.calculate_w(task, new_sequence)
            if w_new - a0 >= worst_rt and q == q_cur:
                worst_rt = w_new - a0
                worst_sequence = new_sequence

        return worst_sequence

    def b_plus_exact(self, task, q, details=None, task_results=None):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        interferers = set()
        for ti in task.get_resource_interferers():
            assert(ti.scheduling_parameter != None)
            assert(ti.resource == task.resource)
            if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                interferers.add(ti)

        sequence = self.find_candidates_recursive(task, q, interferers, list())
        w, a0, q_cur = self.calculate_w(task, sequence, details)

        assert(q == q_cur)
        return w - a0

    def b_plus(self, task, q, details=None, task_results=None):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        busy_details     = dict()
        busy_intrf = self.b_plus_exact(task, q, busy_details, task_results)

        w = busy_intrf
        if details is not None:
            for d in busy_details.keys():
                details[d] = busy_details[d]

#        classic_details  = dict()
#        classic_intrf = SPPScheduler.b_plus(self, task, q, classic_details)
#        if classic_intrf < w:
#            w = classic_intrf
#            if details is not None:
#                for d in classic_details.keys():
#                    details[d] = classic_details[d]

        assert(w >= q * task.wcet)
        return w


class SPPSchedulerRoundRobin(SPPScheduler):
    """ SPP scheduler with non-preemptive round-robin policy for equal priorities
    """

    def b_plus(self, task, q, details=None, **kwargs):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet
        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = 0
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if ti.scheduling_parameter == task.scheduling_parameter:  # equal priority -> round robin
                    # assume cooperative round-robin
                    s += ti.wcet * min(q, ti.in_event_model.eta_plus(w))
                elif self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # lower priority number -> block
                    s += ti.wcet * ti.in_event_model.eta_plus(w)
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))


            w_new = q * task.wcet + s
            # print ("w_new: ", w_new)
            if w == w_new:
                break
            w = w_new

        assert(w >= q * task.wcet)
        return w


class TDMAScheduler(analysis.Scheduler):
    """ TDMA scheduler
        task.scheduling_parameter is the slot size of the respective task
    """

    def b_plus(self, task, q, details=None, **kwargs):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        t_tdma = task.scheduling_parameter
        for tj in task.get_resource_interferers():
            t_tdma += tj.scheduling_parameter

        w = q * task.wcet + math.ceil(float(q * task.wcet) / task.scheduling_parameter) * (t_tdma - task.scheduling_parameter)
        w = int(w)

        assert(w >= q * task.wcet)

        if details is not None:
            details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
            for tj in task.get_resource_interferers():
                details["%s.TDMASlot" % (tj)] = str(tj.scheduling_parameter)
            details['I_TDMA'] = '%d*%d=%d' % (math.ceil(float(q * task.wcet) / task.scheduling_parameter),
                                      t_tdma - task.scheduling_parameter,
                                      math.ceil(float(q * task.wcet) / task.scheduling_parameter) * (t_tdma - task.scheduling_parameter))
        return w

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
