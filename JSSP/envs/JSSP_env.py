import itertools
import random
import gym
import matplotlib
import matplotlib.backends.backend_agg as agg
import numpy as np
import pygame
import pylab
import matplotlib.pyplot as plt
from pygame.locals import *


class JSSPEnv(gym.Env):
    def __init__(self, instance_path, future_data_allowed_for_render=True):

        """
        env_data: n+1 rows
        first row has two entries: n and m representing n jobs and m machiens
        then each row represents the information for each job
        """

        # initial values for variables used for instance
        self.job_operation_status = 0
        self.job_machine_allocation = 1
        # variable that represents the most operation an action can have
        # used for creating observation space
        self.max_operation_count = 0
        # job_total is total # of jobs
        # machine_total is total # of machines
        # job operation map stores the description of the JSP
        self.job_total, self.machine_total, self.job_operation_map = 0, 0, {}
        self.initialize(instance_path)
        # current state of the environment
        self.state = {
            self.job_machine_allocation: np.negative(np.ones(self.job_total)),
            self.job_operation_status: np.zeros(self.job_total),
        }
        # job_finish_time represents finishing time of current job's operation
        self.job_finish_time = np.zeros(self.job_total)
        # legal_allocation_list stores the list of actions at the current state
        self.legal_allocation_list = []
        # legal_allocation_map stores all allocation list, state pairs
        self.legal_allocation_map = {}
        self.generate_legal_allocation_list()
        self.initialize_action_space()
        self.initialize_obs_space()
        # time step of current state
        self.time = 0
        # used for rendering
        self.jobs_history = [[] for _ in range(self.job_total)]
        # used for plotting
        self.colors = self.generate_colors()
        self.future_data_allowed_for_render = future_data_allowed_for_render

    def generate_colors(self):
        colors_dict = ['red', 'blue', 'yellow', 'orange', 'green', 'palegoldenrod', 'purple', 'pink', 'Thistle', 'Magenta', 'SlateBlue', 'RoyalBlue', 'Cyan', 'Aqua', 'floralwhite', 'ghostwhite', 'goldenrod', 'mediumslateblue', 'navajowhite', 'navy', 'sandybrown', 'moccasin']
        if self.machine_total <= 22:
            return colors_dict[:self.machine_total]
        else:
            colors = [tuple([random.random() for _ in range(3)]) for _ in range(self.machine_total)]
            while len(colors) != len(set(colors)):
                colors = [tuple([random.random() for _ in range(3)]) for _ in range(self.machine_total)]
            return colors

    def initialize(self, instance_path):
        """
            populate job_operation_map using the instance file input
            :param instance_path: a string representing file path
        """
        # input instance description for environment initialization
        instance_path = instance_path
        try:
            file_handle = open(instance_path, 'r')
        except OSError:
            print("Could not open/read file:", instance_path)

        lines_list = file_handle.readlines()
        # first line consists of # of jobs in total, # of machines in total
        self.job_total, self.machine_total = [int(x) for x in lines_list[0].split()]
        # read through each job description
        for job_index in range(len(lines_list) - 1):
            job_description = np.array([int(val) for val in lines_list[job_index + 1].split()])
            self.job_operation_map[job_index] = {}
            self.max_operation_count = max(self.max_operation_count, job_description[0])
            # initialize job_operation_map
            # ex. job_operation_map[0][1][2] = time it takes for 3rd machine to execute 2nd operation of 1st job
            # time = -1 iff the machine is not capable of executing the operation based on instance description
            for operation_index in range(job_description[0]):
                self.job_operation_map[job_index][operation_index] = np.negative(np.ones(self.machine_total))
            # populate job_description_map
            self.populate_job_description_map(job_description, job_index)
        file_handle.close()

    def populate_job_description_map(self, job_description, job_index):
        """
            populate the corresponding fields in job_description_map
            :param job_description: a string representing job description
            :param job_index: an integer representing current job index being populated
        """
        # read job description from left to right
        description_pivot = 1
        operation_index = 0
        # operation_index
        while description_pivot < len(job_description):
            # operation_description length = 2 * # of machines capable of executing current operation at the pivot
            operation_description_end = 2 * job_description[description_pivot] + description_pivot
            # read the current description of operation
            description_pivot += 1
            while description_pivot <= operation_description_end:
                # Following the format of operation description:
                # machine index , time it takes for the current operation
                machine_index = job_description[description_pivot]
                operation_duration = job_description[description_pivot + 1]
                self.job_operation_map[job_index][operation_index][machine_index - 1] = operation_duration
                description_pivot += 2
            operation_index += 1

    def update_time(self):
        self.time += 1

    def initialize_action_space(self):
        """
        action: index of an allocation in the legal_allocation_list
                last element is always wait action
        legal_allocation_list: list of legal allocations at current state
            ex. legal_allocation_list = [[0,-1], [-1, 1], [0, 1], [-1, -1]]
                action = 2:
                job 1 -> machine 1
                job2 -> machine 2
        """
        legal_allocation_list_len = len(self.legal_allocation_list)
        self.action_space = gym.spaces.Discrete(legal_allocation_list_len)

    def initialize_obs_space(self):
        """
            observation: tuple of self.state
            self.state: dictionary of two entries:
                        "job_machine_allocation" : array of integers representing ith job's allocation
                                    -1 represents an empty allocation
                                    -2 represents a finished job
                        "job_operation_status" : array of integers representing ith job's current operation status
                        ex.
                        observation = (-1,0,1,0,0,1)
                        self.state = {
                                        job_machine_allocation: [-1,0,1]
                                        job_operation_status: [0,0,1]
                                    }
                        job 1 (operation 1) -> None
                        job 2 (operation 1) -> machine 1
                        job 3 (operation 2) -> machine 2

        """
        lower_bound_obs_space_allocation = np.full(self.job_total, -2)
        upper_bound_obs_space_allocation = np.full(self.job_total, self.machine_total - 1)
        lower_bound_obs_space_operation = np.full(self.job_total, 0)
        upper_bound_obs_space_operation = np.full(self.job_total, self.max_operation_count - 1)
        lower_bound_obs_finish_time = np.full(self.job_total, 0)
        upper_bound_obs_finish_time = np.full(self.job_total, 100)
        lower_bound_temp = np.append(lower_bound_obs_space_allocation, lower_bound_obs_space_operation)
        upper_bound_temp = np.append(upper_bound_obs_space_allocation, upper_bound_obs_space_operation)
        # lower_bound = np.append(lower_bound_temp, lower_bound_obs_finish_time)
        # upper_bound = np.append(upper_bound_temp, upper_bound_obs_finish_time)
        self.observation_space = gym.spaces.Box(low=lower_bound_temp, high=upper_bound_temp, dtype=np.int)

    def get_obs(self):
        """
        :return: observation from the current state consisting of 2 arrays
                "job_machine_allocation" : array of integers representing ith job's allocation
                                    -1 represents an empty allocation
                                    -2 represents a finished job
                "job_operation_status" : array of integers representing ith job's current operation status


                ex. {
                        job_machine_allocation: [-1,0,1]
                        job_operation_status: [0,0,1]

                    }
                    job_finish_time = [-1, 10, 18]

                    job 1 (operation 1) -> job finished
                    job 2 (operation 1) -> machine 1, finish at timestep 10
                    job 3 (operation 2) -> machine 2, finish at timestep 18

        """
        observation_temp = np.append(self.state[self.job_machine_allocation],
                                     self.state[self.job_operation_status])
        # job_left_time = np.array([finish_time - self.time if finish_time > 0
        #                           else finish_time for finish_time in self.job_finish_time])
        # observation = tuple(np.append(observation_temp, job_left_time))

        return tuple(observation_temp)

    def get_legal_allocations(self):
        """
        returns next available legal allocations
        legal allocations requires:
        1. machine operation pair is legal
        2. job is not allocated
        3. machine is not allocated
        :return: list of list of numbers
        ex. {
                0: [0, 1]
                1: []
                2: [0, 2]
        }
        at current state, jobs 1, 3 are free
        for 1st job, machines 1, 2 are legal
        for 2nd job, no machines are free
        for 3rd job, machines 1, 3 are legal
        """
        legal_allocations = []
        job_index = 0
        for current_operation in self.state[self.job_operation_status]:
            job_machine_allocation = self.state[self.job_machine_allocation]
            # legal actions requires:
            # 1. machine operation pair is legal
            # 2. job is not allocated or finished
            # 3. machine is not allocated
            if current_operation == -1:
                free_legal_machines = []
            else:
                job_operation_machine_time = self.job_operation_map[job_index][current_operation]
                legal_machines = np.array([i for i in range(self.machine_total)
                                           if job_operation_machine_time[i] >= 0])
                free_legal_machines = [i for i in legal_machines
                                       if job_machine_allocation[job_index] == -1
                                       if i not in job_machine_allocation]
            free_legal_machines.append(-1)
            legal_allocations.append(free_legal_machines)
            job_index += 1

        return legal_allocations

    def generate_legal_allocation_list(self):
        """
        generates legal_action_allocation_list:
        legal actions requires:
        1. machine operation pair is present in the FJSSP instance
        2. job is not assigned or finished
        3. machine is not assigned
        4. no duplicate job or machine assignments
        5. if all jobs are idle, wait is not allowed
        we check the first 3 conditions in get_legal_allocations
        """
        current_obs = self.get_obs()
        if current_obs in self.legal_allocation_map:
            self.legal_allocation_list = self.legal_allocation_map[current_obs]
            return
        legal_allocations = self.get_legal_allocations()
        allocation_list = list(itertools.product(*legal_allocations))
        legal_allocations_list = []
        for allocation in allocation_list:
            # 4. check for duplicate job allocation
            duplicate_check_list = [machine for machine in allocation if machine != -1]
            if len(np.unique(duplicate_check_list)) == len(duplicate_check_list):
                legal_allocations_list.append(np.array(allocation))
        # 5. check if no job is working
        all_job_idle = np.all(self.state[self.job_machine_allocation] < 0)
        if all_job_idle:
            legal_allocations_list.pop()
        self.legal_allocation_list = legal_allocations_list
        self.legal_allocation_map[self.get_obs()] = legal_allocations_list

    def update_state(self, allocation):
        """
        update the state of the environment based on the given allocation
        1. update state[job_machine_allocation] and job_finish_time given by allocation
        2. update timestep and check for completed jobs
        :param allocation: an array of integers representing allocation
                index is job number, value is machine number
                ex. [1, -1]
                1st job -> 2nd machine
                2nd job -> None
        """
        # 1. update allocation given by allocation
        for job in range(self.job_total):
            current_operation = self.state[self.job_operation_status][job]
            machine = allocation[job]
            if machine >= 0:
                # update the state job_machine_allocation
                self.state[self.job_machine_allocation][job] = machine
                # update the finish time and job_operation_status
                current_operation_duration = self.job_operation_map[job][current_operation][machine]
                self.job_finish_time[job] = self.time + current_operation_duration
                # update the scheduling history
                job_history = self.jobs_history[job]
                job_history.append([machine, self.time, self.job_finish_time[job]])
                self.jobs_history[job] = job_history
        # timestep increases by 1
        self.update_time()
        # 2. check for completed jobs
        for job in range(self.job_total):
            # if job is not finished nor empty
            if self.state[self.job_machine_allocation][job] >= 0:
                if 0 <= self.job_finish_time[job] <= self.time:
                    # change job allocation to empty
                    self.state[self.job_machine_allocation][job] = -1
                    # update the operation status of the job
                    current_operation = self.state[self.job_operation_status][job]
                    next_operation = current_operation + 1
                    # if job is not finished
                    if next_operation in self.job_operation_map[job]:
                        self.state[self.job_operation_status][job] = next_operation
                    # if job is finished
                    else:
                        self.state[self.job_machine_allocation][job] = -2
                        self.job_finish_time[job] = -1

    def generate_reward(self, action):
        """
        function used to generate reward of current state_action pair
        :param action: index of an allocation in the legal_allocation_list
        :return: R(S,A) reward of current state_action pair
        """
        return -1

    def step(self, action):
        """
            1. update the state
            2. check if all jobs are finished, if yes, return done = TRUE
                when a job is finished
                the corresponding entry in state[job_machine_allocation] = -2
            3. update legal_allocation_list and action space accordingly
            4. If there are no other legal actions other than wait
            fastforward to the next state with legal actions other than wait
            5. initialize action space
        :param action: index of an allocation in the legal_allocation_list
                last element is always wait action
                we design list this way because Q table tie breaks from left to right
        :return:
            observation: current state
                ex. {
                        job_machine_allocation: [-1,0]
                        job_operation_status: [0,0]

                    }
            reward: -1 for any time step passed
            done: boolean stating whether all jobs are finished

        """
        reward = 0
        while True:
            reward += self.generate_reward(action)
            allocation = self.legal_allocation_list[action]
            # 1. update the state
            self.update_state(allocation)
            done = np.all(self.state[self.job_machine_allocation] == -2)
            # 2. check if finished
            if done:
                return self.get_obs(), reward, done, {}
            # 3. update legal allocation list
            self.generate_legal_allocation_list()
            # 4. if next state has legal action other than wait
            valid = len(self.legal_allocation_list) > 1
            if valid:
                # 6. re-initialize action space
                self.initialize_action_space()
                return self.get_obs(), reward, done, {}
            # new action entering loop is wait
            action = -1

    def reset(self):
        self.state = {
            self.job_machine_allocation: np.negative(np.ones(self.job_total)),
            self.job_operation_status: np.zeros(self.job_total),
        }
        self.job_finish_time = np.zeros(self.job_total)
        self.legal_allocation_list = []
        self.generate_legal_allocation_list()
        self.initialize_action_space()
        self.initialize_obs_space()
        self.time = 0
        self.jobs_history = [[] for _ in range(self.job_total)]
        return self.get_obs()

    def render(self, mode="human"):

        matplotlib.use("Agg")
        used_machines = []
        fig = pylab.figure(figsize=[6, 4], dpi=100, )
        ax = fig.gca()
        ax.clear()

        for job in range(self.job_total):
            job_history = self.jobs_history[job]
            for operation_history in job_history:
                [machine, start_time, end_time] = operation_history
                if not self.future_data_allowed_for_render:
                    end_time = np.min(end_time, self.time)
                if machine not in used_machines:
                    used_machines.append(machine)
                ax.barh(job, width=end_time - start_time, height=0.8, left=start_time, color=self.colors[machine],
                        edgecolor='black')

        used_machines.sort()
        colors = dict([('machine' + str(machine + 1), self.colors[machine]) for machine in used_machines])
        labels = list(colors.keys())
        handles = [plt.Rectangle((0, 0), 1, 1, color=colors[label]) for label in labels]
        ax.set_yticks(np.arange(self.job_total), ['job' + str(i) for i in range(1, self.job_total + 1)])
        # Shrink current axis by 20%
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

        # Put a legend to the right of the current axis
        ax.legend(handles, labels, loc='center left', bbox_to_anchor=(1, 0.5))

        canvas = agg.FigureCanvasAgg(fig)
        canvas.draw()
        renderer = canvas.get_renderer()
        raw_data = renderer.tostring_rgb()

        pygame.init()

        window = pygame.display.set_mode((600, 400), DOUBLEBUF)
        screen = pygame.display.get_surface()

        size = canvas.get_width_height()

        surf = pygame.image.fromstring(raw_data, size, "RGB")
        screen.blit(surf, (0, 0))
        pygame.event.pump()
        pygame.display.flip()

    def close(self):
        pygame.quit()