"""
| Copyright (C) 2020-2025 Jonas Peeck
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Peeck

Description
-----------

Synchronous object analysis extension

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import time
import gc
import logging
import copy
import time
from collections import deque
import functools




try:
    from time import process_time as timefunc
except:
    from time import clock as timefunc

from . import model as sync_model
from . import propagation as sync_propagation
from . import schedulers as sync_schedulers
from pycpa import model
from pycpa import options
from pycpa import util
from pycpa import analysis

gc.enable()
logger = logging.getLogger(__name__)







def analyze_system(system, task_results=None, only_dependent_tasks=False,
                   progress_hook=None, analysis_order = None, **kwargs):
    """ Analyze all tasks until we find a fixed point

        system -- the system to analyze
        task_results -- if not None, all intermediate analysis
        results from a previous run are reused

        Returns a dictionary with results for each task.

        This based on the procedure described in Section 7.2 in [Richter2005]_.
    """
    if task_results is None:
        task_results = dict()
        for r in system.resources:
            for t in r.tasks:
                if not t.skip_analysis:
                    task_results[t] = analysis.TaskResult()
                    t.analysis_results = task_results[t]

    analysis_state = analysis.GlobalAnalysisState(system, task_results)

    analysis_state.analysisOrder = analysis_order

    iteration = 0
    start = timefunc()
    logger.debug("analysisOrder: %s" % (analysis_state.analysisOrder))
    round = 0
    object_round = 0
    
    start_time = time.time()
    last_time = time.time()
    
    last_resource = None
    while len(analysis_state.dirtyTasks) > 0:

        round+=1

        #for r in system.resources:
                
         #   if hasattr(r.scheduler, 'sync_schedules'):
        
          #      r.scheduler.sync_schedules[1] = None
           #     r.scheduler.load_schedules[1] = None

        if progress_hook is not None:
            progress_hook(analysis_state)

        logger.info("Analyzing, %d tasks left" %
                   (len(analysis_state.dirtyTasks)))

        # explicitly invoke garbage collection because there seem to be circluar references
        # TODO should be using weak references instead for model propagation
        gc_count = gc.collect()
        
        # Always prefer high priority sporadic control tasks
        control_is_dirty = False
        for check_task in analysis_state.analysisOrder:
            if "ControlStream" in check_task.name:
                if check_task in analysis_state.dirtyTasks:
                    control_is_dirty = True
                    
                    
                    
        for t in analysis_state.analysisOrder: # TODO break after each task and start from the beginning
        

            
            
        
            if t not in analysis_state.dirtyTasks:
                continue
                
                
            
            
            if "ADASStream" in t.name and control_is_dirty == True:
                continue
                
                
            if hasattr(r.scheduler, 'sync_schedules'):
            
                #t.resource.scheduler.sync_schedules[1] = None
                #t.resource.scheduler.load_schedules[1] = None
                    
                if last_resource == None:
                    t.resource.scheduler.sync_schedules[1] = None
                    t.resource.scheduler.load_schedules[1] = None
                else:
                    if not last_resource == t.resource:
                        t.resource.scheduler.sync_schedules[1] = None
                        t.resource.scheduler.load_schedules[1] = None
            
        
            if "ObjectStream" in t.name:
                object_round += 1
                print("----------------------- Analyzed ADAS task:" + str(object_round) + " -----------------------")
                #last_resource = t.resource
                #print("Time diff: " + str(time.time() - last_time))
                #print("absolute : " + str(time.time() - start_time))
                #last_time = time.time()
        
        
            # TODO new definition of analysis order w.r.t. adas streams
        
            # check if there is any control task, that is still dirty!
            # Then ignore dirty adas streams
            
            
            
        
        
            #print(analysis_state.analysisOrder)
            analysis_state.dirtyTasks.remove(t)

            # skip analysis for tasks w/ disable propagation
            if t.skip_analysis:
                continue

            if only_dependent_tasks and len(analysis_state.
                                            dependentTask[t]) == 0:
                continue  # skip analysis of tasks w/o dependents

            old_jitter = task_results[t].wcrt - task_results[t].bcrt
            old_busytimes = copy.copy(task_results[t].busy_times)
            analysis.analyze_task(t, task_results)
            
            #sanity check for BET Tasks
            # First decide if to use the BET task analysis
            if not isinstance(t.in_event_model, sync_model.SyncEventModel) and \
               not isinstance(t.in_event_model, sync_model.SyncSampleEventModel) and \
                not isinstance(t.in_event_model, sync_propagation.SyncPropagationEventModel):
                assert functools.reduce(lambda x, y: x and y,\
                               [b - a >= t.wcet for a,b \
                                in util.window(task_results[t].busy_times)]) == True, "Busy_times for task %s on resource %s: %s" % (t.name, t.resource.name, str(task_results[t].busy_times))

            new_jitter = task_results[t].wcrt - task_results[t].bcrt
            new_busytimes = task_results[t].busy_times

            # sanity check for let tasks
            if isinstance(t.in_event_model, model.SyncEventModel) or isinstance(t.in_event_model, model.SyncSampleEventModel) or isinstance(t.in_event_model, sync_propagation.SyncPropagationEventModel):
                assert new_jitter < t.resource.scheduler.hyperperiod , "Jitter exceeded hyperperiod" # TODO abbruchbedingung
                
                # Reset schedule here...

                
                #assert new_jitter > old_jitter , "New Jitter has to be greater equals the old Jitter"

            if new_jitter != old_jitter or old_busytimes != new_busytimes: # TODO für den sync ansatz: schauen ob sich die deltas verschoben haben.!
                # If jitter has changed, the input event models of all
                # dependent task(s) have also changed,
                # including their dependent tasks and so forth...
                # so mark them and all other tasks on their resource for
                # another analysis

                # propagate event model
                analysis._propagate(t, task_results)

                # mark all dependencies dirty
                analysis_state._mark_dependents_dirty(t)
                
                
                for dtask in analysis_state.dependentTask[t]:
                    if isinstance(dtask.in_event_model, model.SyncEventModel) or isinstance(dtask.in_event_model, model.SyncSampleEventModel) or isinstance(dtask.in_event_model, sync_propagation.SyncPropagationEventModel):
                        if dtask.scheduling_parameter in dtask.resource.scheduler.sync_schedules:
                            dtask.resource.scheduler.sync_schedules[dtask.scheduling_parameter] = None
                        if dtask.scheduling_parameter in dtask.resource.scheduler.load_schedules:
                            dtask.resource.scheduler.load_schedules[dtask.scheduling_parameter] = None
                
                
                break  # break the for loop to restart iteration

            elapsed = (timefunc() - start)
            logger.debug("iteration: %d, time: %.1f task: %s wcrt: %f dirty: %d"
                         % (iteration, elapsed, t.name,
                            task_results[t].wcrt,
                            len(analysis_state.dirtyTasks)))
            if elapsed > options.get_opt('timeout'):
                raise TimeoutException("Timeout reached after iteration %d" % iteration)
        
            iteration += 1
            break # Always break, XXX Checkme

        elapsed = timefunc() - start
        if elapsed > options.get_opt('timeout'):
            raise TimeoutException("Timeout reached after iteration %d" % iteration)

        # # check for constraint violations
        if options.get_opt("check_violations"):
            violations = analysis.check_violations(system.constraints, task_results)
            if violations == True:
                logger.error("Analysis stopped!")
                raise NotSchedulableException("Violation of constraints")
                break

    # print "Global iteration done after %d iterations" % (round)

    # # also print the violations if on-the-fly checking was turned off
    if not options.get_opt("check_violations"):
        analysis.check_violations(system.constraints, task_results)
    
    # a hook that allows to inspect the analysis_state object after the analysis run
    post_hook = kwargs.get('post_hook', None)
    if post_hook is not None:
        post_hook(analysis_state)

    return task_results
















