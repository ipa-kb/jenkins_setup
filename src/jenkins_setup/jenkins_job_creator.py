#!/usr/bin/env python

import datetime
import socket
import pkg_resources
import yaml
import re


class JenkinsJob(object):
    """
    Jenkins job creation class
    """
    def __init__(self, jenkins_instance, pipeline_instance):
        """
        Sets up Jenkins job object
        """

        self.jenkins_instance = jenkins_instance
        self.pipe_inst = pipeline_instance

        self.job_config_params = pkg_resources.resource_string('jenkins_setup', 'templates/job_config_params.yaml')
        self.job_config_params = yaml.load(self.job_config_params)
        self.job_config = pkg_resources.resource_string('jenkins_setup', 'templates/job_config.xml')

        self.params = {}

        self.job_name = None
        self.job_type = None
        self.poll = None
        self.repo_list = None

    def schedule_job(self):
        """
        Creates new or reconfigure existent job

        @return: return message, ``str``
        """
        if self.jenkins_instance.job_exists(self.job_name):
            try:
                self.jenkins_instance.reconfig_job(self.job_name, self.job_config)
                return "Reconfigured job %s" % self.job_name
            except Exception as ex:
                print ex
                return 'Reconfiguration of %s failed: %s' % (self.job_name, ex)
        else:
            try:
                self.jenkins_instance.create_job(self.job_name, self.job_config)
                return "Created job %s" % self.job_name
            except Exception as ex:
                print ex
                return 'Creation of %s failed: %s' % (self.job_name, ex)

    def create_job(self):
        """
        Sets job specific parameter, sets up the job config and creates job
        on Jenkins instance
        """

        self._set_common_params()

        self._set_job_type_params()

        self._replace_placeholder()
        print self.schedule_job()

        return self.job_name

    def delete_job(self):
        """
        Deletes the job defined by the job name

        @return: return message, ``str``
        """

        if self.jenkins_instance.job_exists(self.job_name):
            try:
                self.jenkins_instance.delete_job(self.job_name)
                print "Deleted job %s" % self.job_name
            except Exception as ex:
                print "Deletion of job %s failed: %s" % (self.job_name, ex)
                return ''
            return self.job_name
        else:
            print "Did not delete job %s, because not job did not exist" % self.job_name
            return ''

    def _set_common_params(self):
        """
        Sets all parameters which have to be defined for every job type
        """

        self.params['USERNAME'] = self.pipe_inst.user_name
        #self.params['JOB_TYPE_NAME'] = self.job_type
        self.params['SCRIPT'] = self.job_type
        self.params['NODE_LABEL'] = self.job_type
        self.params['TIME'] = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M')
        self.params['HOSTNAME'] = socket.gethostname()
        self.params['PROJECT'] = 'matrix-project'
        self.params['TRIGGER'] = self.job_config_params['triggers']['none']
        self.params['SHELL'] = ''
        self.params['VCS'] = self.job_config_params['vcs']['none']
        self.params['MATRIX'] = ''
        self.params['PARAMETERS'] = ''
        self.params['POSTBUILD_TRIGGER'] = ''
        self.params['JOIN_TRIGGER'] = ''
        self.params['PIPELINE_TRIGGER'] = ''
        self.params['GROOVY_POSTBUILD'] = ''
        self.params['PARAMETERIZED_TRIGGER'] = ''
        self.params['JUNIT_TESTRESULTS'] = ''
        self.params['MAILER'] = ''
        self.params['POSTBUILD_TASK'] = ''
        self._set_authorization_matrix_param('build')

    ###########################################################################
    # helper methods - parameter generation
    ###########################################################################
    def _replace_placeholder(self):
        """
        Replaces placeholder in template with parameters
        """

        for key, value in self.params.iteritems():
            if "@(%s)" % key not in self.job_config:
                raise KeyError("Parameter %s could not be replaced, because it is not existent" % key)
            self.job_config = self.job_config.replace("@(%s)" % key, value)
        not_replaced_keys = re.findall('@\(([A-Z0-9_]+)\)', self.job_config)
        if not_replaced_keys != []:
            raise KeyError("The keys %s were not replaced, because the parameters where missing" % (str(not_replaced_keys)))

    def _generate_job_name(self, job_type, suffix=''):
        '''
        Returns a job_name string generated from a job_type plus suffix

        :param job_type: short job type name, ``str``
        :param suffix: will be added to the end of the name, ``str``
        '''

        if suffix != '':
            return '__'.join([self.pipe_inst.user_name, job_type, suffix])
        else:
            return '__'.join([self.pipe_inst.user_name, job_type])

    def _generate_job_list(self, job_type_list):
        '''
        returns a list of job_names generated from a list of job_types
        '''

        if type(job_type_list) != list:
            raise TypeError("Input type is not type 'list'")
        return [self._generate_job_name(job_type) for job_type in job_type_list]

    def _generate_job_list_string(self, job_type_list):
        '''
        returns a string of comma separated job_names generated from a list of job_types
        '''

        return ', '.join(self._generate_job_list(job_type_list))

    def _generate_matrix_filter(self, config, negation=False):
        """
        Returns a groovy combination filter

        :param config: couples of names and values which have to be met, ``dict``
        :param negation: negates the resulting filter, ``bool``
        :returns: matrix config, ``str``
        """

        filter = '%s' % ' || '.join(['(%s)' % ' &amp;&amp; '.join(['%s=="%s"' % (key, value)
                                                                   for key, value in i.iteritems()])
                                     for i in config])
        if negation:
            filter = '!(%s)' % filter

        return filter

    def _generate_matrix_axis(self, axis_name, value_list):
        """
        Returns matrix axis config for given list of values

        :param axis_name: name of axis, ``str``
        :param value_list: list with value, ``list``
        :returns: axis config, ``str``
        """

        if axis_name == '':
            raise Exception('No proper name given')
        if value_list == []:
            raise Exception('No values given')
        axis = self.job_config_params['matrix']['axis'].replace('@(NAME)', axis_name)
        values = ' '.join([self.job_config_params['matrix']['value'].replace('@(VALUE)', value) for value in sorted(value_list)])
        axis = axis.replace('@(VALUES)', values)

        return axis

    def _set_matrix_param(self, name_value_dict_list, filter=None):
        """
        Returns matrix config for given dictionary containing names and values

        @param name_value_dict_list: matrix parameter config
        @type  name_value_dict_list: list
        @param filter: combination filter
        @type  filter: str
        """

        axes = ''
        if name_value_dict_list == []:
            return ''
        for name_value_dict in sorted(name_value_dict_list):
            axes += ' '.join([self._generate_matrix_axis(axis_name, axis_values)
                              for axis_name, axis_values in name_value_dict.iteritems()])
        if axes == '':
            return ''

        matrix = self.job_config_params['matrix']['basic']
        matrix = matrix.replace('@(NODE)', self.job_type)
        matrix = matrix.replace('@(AXES)', axes)
        if filter:
            matrix += ' ' + self.job_config_params['matrix']['filter'].replace('@(FILTER)', filter)
        elif filter == '':
            matrix += ' ' + self.job_config_params['matrix']['filter'].replace('@(FILTER)', 'repository=="NO_ENTRY"')

        self.params['MATRIX'] = matrix

    def _get_matrix_entries(self):
        """
        Gets all repository, ros_distro, ubuntu_distro and arch entries of
        pipeline configuration

        @return type: list of dicts
        """
        dict_list = []
        dict_list.append({'repository': self.pipe_inst.repositories.keys()})
        ros_distros = []
        ubuntu_distros = []
        archs = []
        for repo_name, repo_data, in self.pipe_inst.repositories.iteritems():
            for ros_distro in repo_data.ros_distro:
                if ros_distro not in ros_distros:
                    ros_distros.append(ros_distro)
            if repo_data.prio_ubuntu_distro not in ubuntu_distros:
                ubuntu_distros.append(repo_data.prio_ubuntu_distro)
            if repo_data.prio_arch not in archs:
                archs.append(repo_data.prio_arch)
            for ubuntu_distro, repo_archs in repo_data.regular_matrix.iteritems():
                if ubuntu_distro not in ubuntu_distros:
                    ubuntu_distros.append(ubuntu_distro)
                for arch in repo_archs:
                    if arch not in archs:
                        archs.append(arch)

        dict_list.append({'ros_distro': ros_distros})
        dict_list.append({'ubuntu_distro': ubuntu_distros})
        dict_list.append({'arch': archs})

        return dict_list

    def _set_jointrigger_param(self, job_type_list, unstable_behavior=False, parameterized_trigger=None):
        """
        Sets config for jointrigger plugin

        @param job_type_list: job types (short) to join
        @type  job_type_list: list
        @param unstable_behavior: execute join project even if upstream projects
        where unstable
        @type  unstable_behavior: bool
        @param parameterized_trigger: parameterized trigger configuration
        @type  parameterized_trigger: str
        """

        if job_type_list == [] and not parameterized_trigger:
            raise Exception("Neither jobs trigger nor parameterized trigger configuration given")
        elif type(unstable_behavior) != bool:
            raise Exception("Behavior argument for unstable job result has to be a boolean")

        jointrigger = self.job_config_params['jointrigger'].replace('@(JOIN_PROJECTS)',
                                                                    self._generate_job_list_string(job_type_list))
        if unstable_behavior:
            jointrigger = jointrigger.replace('@(JOIN_UNSTABLE)', 'true')
        else:
            jointrigger = jointrigger.replace('@(JOIN_UNSTABLE)', 'false')

        if parameterized_trigger:
            if parameterized_trigger == '':
                raise Exception("Parameterized trigger configuration string is empty")
            jointrigger = jointrigger.replace('@(PARAMETERIZED_TRIGGER)', parameterized_trigger)
        else:
            jointrigger = jointrigger.replace('@(PARAMETERIZED_TRIGGER)', '')

        self.params['JOIN_TRIGGER'] = jointrigger

    def _set_postbuildtrigger_param(self, job_type_list, threshold_name):
        """
        Sets config for postbuildtrigger plugin

        :param job_type_list: list with job types (short) to trigger, ``list``
        :param threshold_name: when to trigger projects, ``str``
        """

        if job_type_list == []:
            return ''
        elif threshold_name == '':
            raise Exception('No treshold for postbuildtrigger given')
        elif threshold_name not in ['SUCCESS', 'UNSTABLE', 'FAILURE']:  # TODO check tresholds
            raise Exception("Threshold argument invalid")

        postbuildtrigger = self.job_config_params['postbuildtrigger'].replace('@(CHILD_PROJECTS)',
                                                                              self._generate_job_list_string(job_type_list))
        self.params['POSTBUILD_TRIGGER'] = postbuildtrigger.replace('@(THRESHOLD)', threshold_name)

    def _set_pipelinetrigger_param(self, job_type_list):
        """
        Sets config for pipelinetrigger plugin

        :param job_type_list: list with job types (short) to trigger, ``list``
        """

        if job_type_list == []:
            return ''
        self.params['PIPELINE_TRIGGER'] = self.job_config_params['pipelinetrigger'].replace('@(PIPELINETRIGGER_PROJECT)',
                                                                                            self._generate_job_list_string(job_type_list))

    def _set_groovypostbuild_param(self, script_type, project_list, behavior):
        """
        Sets config for groovypostbuild plugin

        :param script_type: enable, join_enable, disable, ``str``
        :param project_list: list with names of projects, ``list``
        :param behavior: when to execute script (0, 1, 2), ``int``
        """

        if project_list == []:
            raise Exception('No project is given')
        if behavior > 2 or behavior < 0 or type(behavior) != int:
            raise Exception('Invalid behavior number given')
        script = self.job_config_params['groovypostbuild']['script'][script_type].replace('@(PROJECT_LIST)',
                                                                                          str(self._generate_job_list(project_list)))
        self.params['GROOVY_POSTBUILD'] = self.job_config_params['groovypostbuild']['basic'].replace('@(GROOVYPB_SCRIPT)', script).replace('@(GROOVYPB_BEHAVIOR)', str(behavior))

    def _get_single_parameterizedtrigger(self, job_type_list, condition='SUCCESS', predefined_param='', subset_filter='', no_param=False):
        """
        Gets config for one parameterized trigger

        :param job_type_list: list with job types (short) to trigger, ``list``
        :param condition: when to trigger, ``str``
        :param predefined_param: parameter to pass to downstream project, ``str``
        :param subset_filter: combination filter for matrix projects, ``str``
        :param no_param: trigger build without parameters, ``bool``
        """

        matrix_subset = ''
        if subset_filter != '':
            matrix_subset = self.job_config_params['parameterizedtrigger']['matrix_subset']
            matrix_subset = matrix_subset.replace('@(FILTER)', subset_filter)

        predef_param = ''
        if predefined_param != '':
            predef_param = self.job_config_params['parameterizedtrigger']['predef_param']
            predef_param = predef_param.replace('@(PARAMETER)', predefined_param)

        param_trigger = self.job_config_params['parameterizedtrigger']['trigger']
        param_trigger = param_trigger.replace('@(CONFIGS)', predef_param + matrix_subset)
        param_trigger = param_trigger.replace('@(PROJECTLIST)', self._generate_job_list_string(job_type_list))
        param_trigger = param_trigger.replace('@(CONDITION)', condition)

        if no_param:
            param_trigger = param_trigger.replace('@(NOPARAM)', 'true')
        else:
            param_trigger = param_trigger.replace('@(NOPARAM)', 'false')

        return param_trigger

    def _get_parameterizedtrigger_param(self, trigger_list):
        """
        Gets config for parameterized trigger plugin

        @param trigger_list: strings of trigger config
        @type  trigger_list: list
        """

        if trigger_list == []:
            raise Exception("No trigger config given")
        param_trigger = self.job_config_params['parameterizedtrigger']['basic']
        param_trigger = param_trigger.replace('@(TRIGGERS)', ' '.join(trigger_list))

        return param_trigger

    def _set_parameterizedtrigger_param(self, trigger_list):
        """
        Sets config for parameterized trigger plugin

        @param trigger_list: strings of trigger config
        @type  trigger_list: list
        """

        self.params['PARAMETERIZED_TRIGGER'] = self._get_parameterizedtrigger_param(trigger_list)

    def _set_mailer_param(self, job_name):
        """
        Sets config for mailer

        @param job_name: name of job to be shown in email subject
        @type  job_name: string
        """

        mailer = self.job_config_params['emailext']
        mailer = mailer.replace('@(EMAIL)', self.pipe_inst.email)
        mailer = mailer.replace('@(JOBNAME)', job_name)
        if self.pipe_inst.committer_email_enabled:
            mailer = mailer.replace('@(EMAIL_TO_COMMITTER)', 'true')
        else:
            mailer = mailer.replace('@(EMAIL_TO_COMMITTER)', 'false')

        self.params['MAILER'] = mailer

    def _set_authorization_matrix_param(self, permission):
        """
        Sets config for authorization matrix plugin

        @param permission: [read|build]
        @type  permission: string
        """

        authorization = self.job_config_params['authorizationmatrix'][permission]
        authorization = authorization.replace('@(USERNAME)', self.pipe_inst.user_name)

        self.params['AUTHORIZATIONMATRIX'] = authorization

    def _set_junit_testresults_param(self):
        """
        Sets config for junit test result report
        """

        self.params['JUNIT_TESTRESULTS'] = self.job_config_params['junit_testresults']

    def _set_trigger_param(self, trigger_type):
        """
        Sets config for trigger parameter

        @param trigger_type: name of trigger type
        @type  trigger_type: str
        """

        self.params['TRIGGER'] = self.job_config_params['triggers'][trigger_type]

        if trigger_type == 'resulttrigger':
            pass  # TODO
        if trigger_type == 'vcs':
            self._set_vcs_param()

    def _set_vcs_param(self):
        """
        Sets config for vcs parameter
        """

        if self.poll != self.repo_list[0]:
            vcs_config = self.job_config_params['vcs'][self.pipe_inst.repositories[self.repo_list[0]].dependencies[self.poll].type]
            vcs_config = vcs_config.replace('@(URI)', self.pipe_inst.repositories[self.repo_list[0]].dependencies[self.poll].url)
            if self.pipe_inst.repositories[self.repo_list[0]].dependencies[self.poll].type != 'svn':
                vcs_config = vcs_config.replace('@(BRANCH)', self.pipe_inst.repositories[self.repo_list[0]].dependencies[self.poll].version)
        else:
            vcs_config = self.job_config_params['vcs'][self.pipe_inst.repositories[self.repo_list[0]].type]
            vcs_config = vcs_config.replace('@(URI)', self.pipe_inst.repositories[self.repo_list[0]].url)
            if self.pipe_inst.repositories[self.repo_list[0]].type != 'svn':
                vcs_config = vcs_config.replace('@(BRANCH)', self.pipe_inst.repositories[self.repo_list[0]].version)

        self.params['VCS'] = vcs_config

    def _set_shell_param(self, shell_script):
        """
        Sets config for execute shell parameter

        @param shell_script: shell commands to execute
        @type  shell_script: str
        """

        if shell_script == '':
            raise Exception("No shell script is given")

        shell_config = self.job_config_params['execute_shell']

        shell_config = shell_config.replace('@(COMMAND)', shell_script)

        self.params['SHELL'] = shell_config

    def _get_shell_script(self, script_type=None):
        """
        Gets and sets up execute shell script template
        """

        shell_temp = pkg_resources.resource_string('jenkins_setup', 'templates/execute_shell.yaml')
        shell_temp = yaml.load(shell_temp)
        if script_type:
            shell_script = shell_temp[script_type]
        else:
            shell_script = shell_temp[self.job_type]
        shell_script = shell_script.replace('@(SERVERNAME)', self.pipe_inst.server_name)
        shell_script = shell_script.replace('@(STORAGE)', self.tarball_location)
        shell_script = shell_script.replace('@(USERNAME)', self.pipe_inst.user_name)
        shell_script = shell_script.replace('@(JOB_TYPE_NAME)', self.job_type)
        shell_script = shell_script.replace('@(PIPELINEREPOSOWNER)', self.pipe_inst.pipeline_repos_owner)
        shell_script = shell_script.replace('@(CONFIG_FOLDER)', self.pipe_inst.config_folder)

        return shell_script

    def _get_prio_subset_filter(self):
        """
        Gets subset filter for priority build
        """

        subset_filter_input = []
        for repo in self.repo_list:
            for rosdistro in self.pipe_inst.repositories[repo].ros_distro:
                subset_filter_input_entry = {}
                subset_filter_input_entry['repository'] = repo
                subset_filter_input_entry['ros_distro'] = rosdistro
                subset_filter_input_entry['ubuntu_distro'] = self.pipe_inst.repositories[repo].prio_ubuntu_distro
                subset_filter_input_entry['arch'] = self.pipe_inst.repositories[repo].prio_arch
                subset_filter_input.append(subset_filter_input_entry)

        return subset_filter_input


class PipeStarterGeneralJob(JenkinsJob):
    """
    Object representation of a general Pipe Starter Job
    """
    def __init__(self, jenkins_instance, pipeline_config, repo_list):
        """
        :param jenkins_instance: object of Jenkins server
        :param pipeline_config: config dict, ``dict``
        :param repo_list: list of names of repository to trigger after change, ``list``
        """

        super(PipeStarterGeneralJob, self).__init__(jenkins_instance, pipeline_config)

        self.job_type = 'pipe_starter'
        self.job_name = self._generate_job_name(self.job_type, suffix='general')

        self.repo_list = repo_list

    def _set_job_type_params(self):
        """
        Sets pipe starter specific job configuration parameters
        """

        self.params['NODE_LABEL'] = 'master'
        self.params['PROJECT'] = 'project'

        # set parameterized trigger
        prio_triggers = []
        for repo in self.repo_list:
            prio_triggers.append(self._get_single_parameterizedtrigger(['prio_build'],
                                                                       subset_filter=self._generate_matrix_filter(self._get_prio_subset_filter()),
                                                                       predefined_param='POLL=manually triggered' + '\nREPOSITORY=%s' % repo + '\nREPOSITORY_FILTER=repository=="%s"' % repo))
        self._set_parameterizedtrigger_param(prio_triggers)


class PipeStarterJob(PipeStarterGeneralJob):
    """
    Object representation of Pipe Starter Job
    """
    def __init__(self, jenkins_instance, pipeline_config, repo_list, poll):
        """
        :param jenkins_instance: object of Jenkins server
        :param pipeline_config: config dict, ``dict``
        :param repo_list: list of names of repository to trigger after change, ``list``
        :param poll: name of repository to monitor for changes, ``str``
        """

        super(PipeStarterJob, self).__init__(jenkins_instance, pipeline_config, repo_list)

        self.job_type = 'pipe_starter'
        self.job_name = self._generate_job_name(self.job_type, suffix=poll)

        self.repo_list = repo_list
        self.poll = repo_list[0]
        if poll != repo_list[0]:
            self.poll = poll
            if poll in self.pipe_inst.repositories.keys():
                self.repo_list.append(poll)

    def _set_job_type_params(self):
        """
        Sets pipe starter job specific job configuration parameters
        """

        super(PipeStarterJob, self)._set_job_type_params()

        self._set_trigger_param('vcs')

        # generate parameterized triggers
        prio_triggers = []
        for repo in self.repo_list:
            prio_triggers.append(self._get_single_parameterizedtrigger(['prio_build'], subset_filter='(repository=="%s")' % repo,
                                                                       predefined_param='POLL=' + self.poll + '\nREPOSITORY=%s' % repo))
        self._set_parameterizedtrigger_param(prio_triggers)


class BuildJob(JenkinsJob):
    """
    Class for build jobs
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location):
        """
        Creates a build job instance

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(BuildJob, self).__init__(jenkins_instance, pipeline_config)

        self.tarball_location = tarball_location

    def _set_job_type_params(self, matrix_filter=None):
        """
        Sets build job specific job configuration parameters
        """

        self.params['NODE_LABEL'] = 'master'
        self.params['POSTBUILD_TASK'] = self.job_config_params['postbuildtask']

        # set matrix
        if not matrix_filter:
            matrix_filter = self._generate_matrix_filter(self._get_prio_subset_filter())
        matrix_entries_dict_list = self._get_matrix_entries()
        self._set_matrix_param(matrix_entries_dict_list, matrix_filter)


class PriorityBuildJob(BuildJob):
    """
    Class for priority build jobs
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a priority build job instance

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(PriorityBuildJob, self).__init__(jenkins_instance, pipeline_config, tarball_location)

        self.repo_list = execute_repo_list

        self.job_type = 'prio_build'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets priority build job specific job configuration parameters
        """

        super(PriorityBuildJob, self)._set_job_type_params()

        # email
        self._set_mailer_param('Priority Build')

        # set execute shell
        shell_script = self._get_shell_script()
        self._set_shell_param(shell_script)

        # set pipeline trigger
        self._set_pipelinetrigger_param(['hardware_build_trigger', 'nongraphics_test', 'graphics_test'])

        # set parameterized triggers
        parameterized_triggers = []
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['regular_build'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['downstream_build'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['prio_nongraphics_test'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['prio_graphics_test'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        self._set_parameterizedtrigger_param(parameterized_triggers)


class RegularBuildJob(BuildJob):
    """
    Class for regular build jobs
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location):
        """
        Creates a regular  build job instance

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(RegularBuildJob, self).__init__(jenkins_instance, pipeline_config, tarball_location)

        self.job_type = 'regular_build'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets regular build job specific job configuration parameters
        """

        matrix_filter = self._generate_matrix_filter(self._get_regular_subset_filter())

        super(RegularBuildJob, self)._set_job_type_params(matrix_filter)

        # email
        self._set_mailer_param('Regular Build')

        # set execute shell
        shell_script = self._get_shell_script()
        self._set_shell_param(shell_script)

        # set pipeline trigger
        self._set_pipelinetrigger_param(['nongraphics_test', 'graphics_test'])

        # set parameterized triggers
        parameterized_triggers = []
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['regular_nongraphics_test'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['regular_graphics_test'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        self._set_parameterizedtrigger_param(parameterized_triggers)

    def _get_regular_subset_filter(self):
        """
        Gets subset filter for regular build
        """

        subset_filter_input = []
        for repo in self.pipe_inst.repositories.keys():
            for rosdistro in self.pipe_inst.repositories[repo].ros_distro:
                for ubuntu_distro, repo_archs in self.pipe_inst.repositories[repo].regular_matrix.iteritems():
                    for repo_arch in repo_archs:
                        subset_filter_input_entry = {}
                        subset_filter_input_entry['repository'] = repo
                        subset_filter_input_entry['ros_distro'] = rosdistro
                        subset_filter_input_entry['ubuntu_distro'] = ubuntu_distro
                        subset_filter_input_entry['arch'] = repo_arch
                        subset_filter_input.append(subset_filter_input_entry)

        return subset_filter_input


class DownstreamBuildJob(BuildJob):
    """
    Class for downstream build job
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a downstream build job instance

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        @param repo_list: repositories this job will build
        @type  repo_list: list
        """

        super(DownstreamBuildJob, self).__init__(jenkins_instance, pipeline_config, tarball_location)

        self.repo_list = execute_repo_list

        self.job_type = 'downstream_build'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets downstream build job specific job configuration parameters
        """

        super(DownstreamBuildJob, self)._set_job_type_params()

        # email
        self._set_mailer_param('Downstream Build')

        # set execute shell
        shell_script = self._get_shell_script()
        self._set_shell_param(shell_script)

        # set parameterized triggers
        self._set_parameterizedtrigger_param([self._get_single_parameterizedtrigger(['downstream_test'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY')])


class TestJob(JenkinsJob):
    """
    Class for test jobs
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a test job instance

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        @param repo_list: repositories this job will build
        @type  repo_list: list
        """

        super(TestJob, self).__init__(jenkins_instance, pipeline_config)

        self.tarball_location = tarball_location

        self.repo_list = execute_repo_list

        self.job_type = 'test'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self, matrix_filter=None):
        """
        Sets test job specific job configuration parameters
        """

        self.params['NODE_LABEL'] = 'master'
        self.params['POSTBUILD_TASK'] = self.job_config_params['postbuildtask']

        # junit test result location
        self._set_junit_testresults_param()

        # set matrix
        if not matrix_filter:
            matrix_filter = self._generate_matrix_filter(self._get_test_subset_filter())
        matrix_entries_dict_list = self._get_matrix_entries()
        self._set_matrix_param(matrix_entries_dict_list, matrix_filter)

        # set pipeline trigger
        self._set_pipelinetrigger_param(['release'])

    def _get_test_subset_filter(self):
        """
        Gets the subset filter of the given test job (non/graphics_test)

        @param test_type: test job type to calculate subset filter for
        @type  test_type: string

        @return type: list of dicts of subset filter entries
        """

        subset_filter_input = []
        for repo in self.pipe_inst.repositories.keys():
            if '_'.join(self.job_type.split('_')[1:]) in self.pipe_inst.repositories[repo].jobs:
                if self.job_type.split('_')[0] == 'prio':
                    for rosdistro in self.pipe_inst.repositories[repo].ros_distro:
                        subset_filter_input_entry = {}
                        subset_filter_input_entry['repository'] = repo
                        subset_filter_input_entry['ros_distro'] = rosdistro
                        subset_filter_input_entry['ubuntu_distro'] = self.pipe_inst.repositories[repo].prio_ubuntu_distro
                        subset_filter_input_entry['arch'] = self.pipe_inst.repositories[repo].prio_arch
                        subset_filter_input.append(subset_filter_input_entry)

                elif self.job_type.split('_')[0] == 'regular':
                    for rosdistro in self.pipe_inst.repositories[repo].ros_distro:
                        for ubuntu_distro, repo_archs in self.pipe_inst.repositories[repo].regular_matrix.iteritems():
                            for repo_arch in repo_archs:
                                subset_filter_input_entry = {}
                                subset_filter_input_entry['repository'] = repo
                                subset_filter_input_entry['ros_distro'] = rosdistro
                                subset_filter_input_entry['ubuntu_distro'] = ubuntu_distro
                                subset_filter_input_entry['arch'] = repo_arch
                                subset_filter_input.append(subset_filter_input_entry)

                else:
                    raise Exception("Unknown build job type: %s" % self.job_type.split('_')[0])

        return subset_filter_input


class PriorityNongraphicsTestJob(TestJob):
    """
    Class for priority nongraphics test job
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a nongraphics test job instance for the priority builds

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(PriorityNongraphicsTestJob, self).__init__(jenkins_instance, pipeline_config, tarball_location, execute_repo_list)

        self.job_type = 'prio_nongraphics_test'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets nongraphics test job specific job configuration parameters
        """

        super(PriorityNongraphicsTestJob, self)._set_job_type_params()

        # email
        self._set_mailer_param('Priority Non-Graphics Test')

        # set execute shell
        shell_script = self._get_shell_script('nongraphics_test')
        self._set_shell_param(shell_script)


class RegularNongraphicsTestJob(TestJob):
    """
    Class for regular nongraphics test job
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a nongraphics test job instance for the regular builds

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(RegularNongraphicsTestJob, self).__init__(jenkins_instance, pipeline_config, tarball_location, execute_repo_list)

        self.job_type = 'regular_nongraphics_test'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets nongraphics test job specific job configuration parameters
        """

        super(RegularNongraphicsTestJob, self)._set_job_type_params()

        # email
        self._set_mailer_param('Regular Non-Graphics Test')

        # set execute shell
        shell_script = self._get_shell_script('nongraphics_test')
        self._set_shell_param(shell_script)


class PriorityGraphicsTestJob(TestJob):
    """
    Class for priority graphics test job
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a graphics test job instance for the priority builds

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(PriorityGraphicsTestJob, self).__init__(jenkins_instance, pipeline_config, tarball_location, execute_repo_list)

        self.job_type = 'prio_graphics_test'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets graphics test job specific job configuration parameters
        """

        super(PriorityGraphicsTestJob, self)._set_job_type_params()

        # email
        self._set_mailer_param('Priority Graphics Test')

        # set execute shell
        shell_script = self._get_shell_script('graphics_test')
        self._set_shell_param(shell_script)


class RegularGraphicsTestJob(TestJob):
    """
    Class for regular graphics test job
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a graphics test job instance for the regular builds

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(RegularGraphicsTestJob, self).__init__(jenkins_instance, pipeline_config, tarball_location, execute_repo_list)

        self.job_type = 'regular_graphics_test'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets graphics test job specific job configuration parameters
        """

        super(RegularGraphicsTestJob, self)._set_job_type_params()

        # email
        self._set_mailer_param('Regular Graphics Test')

        # set execute shell
        shell_script = self._get_shell_script('graphics_test')
        self._set_shell_param(shell_script)


class DownstreamTestJob(TestJob):
    """
    Class for downstream test job
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location, execute_repo_list):
        """
        Creates a downstream test job instance

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        @param repo_list: repositories this job will build
        @type  repo_list: list
        """

        super(DownstreamTestJob, self).__init__(jenkins_instance, pipeline_config, tarball_location)

        self.repo_list = execute_repo_list

        self.job_type = 'downstream_test'
        self.job_name = self.generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Set downstream test job specific job configuration parameters
        """

        matrix_filter = self._generate_matrix_filter(self._get_prio_subset_filter())

        super(DownstreamTestJob, self)._set_job_type_params(matrix_filter)

        # email
        self._set_mailer_param('Downstream Test')

        # set execute shell
        shell_script = self._get_shell_script()
        self._set_shell_param(shell_script)


class HardwareBuildTrigger(JenkinsJob):
    """
    """
    def __init__(self, jenkins_instance, pipeline_config):
        super(HardwareBuildJob, self).__init__(jenkins_instance, pipeline_config)

        self.job_type = 'hardware_build_trigger'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets hardware build trigger job specific job configuration parameters
        """

        self.params['PROJECT'] = 'project'

        # set parameterized triggers
        parameterized_triggers = []
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['hardware_build'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        self._set_parameterizedtrigger_param(parameterized_triggers)


class HardwareBuildJob(JenkinsJob):
    """
    Class for hardware build jobs
    """
    def __init__(self, jenkins_instance, pipeline_config):
        """
        Creates a hardware build job

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(HardwareBuildJob, self).__init__(jenkins_instance, pipeline_config)

        self.job_type = 'hardware_build'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets hardware build job specific job configuration parameters
        """

        # email
        self._set_mailer_param('Hardware Build')

        # set execute shell
        shell_script = self.get_shell_script()
        self.set_shell_param(shell_script)

        # set pipeline trigger
        self.set_pipelinetrigger_param(['hardware_test_trigger'])

        # authorization matrix
        self._set_authorization_matrix_param('read')


class HardwareTestTrigger(JenkinsJob):
    """
    """
    def __init__(self, jenkins_instance, pipeline_config):
        super(HardwareTestJob, self).__init__(jenkins_instance, pipeline_config)

        self.job_type = 'hardware_test_trigger'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets hardware test trigger job specific job configuration parameters
        """

        self.params['PROJECT'] = 'project'

        # set parameterized triggers
        parameterized_triggers = []
        parameterized_triggers.append(self._get_single_parameterizedtrigger(['hardware_test'], subset_filter='(repository=="$REPOSITORY")', predefined_param='REPOSITORY=$REPOSITORY'))
        self._set_parameterizedtrigger_param(parameterized_triggers)


class HardwareTestJob(JenkinsJob):
    """
    Class for hardware test jobs
    """
    def __init__(self, jenkins_instance, pipeline_config):
        """
        Creates a hardware test job

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(HardwareTestJob, self).__init__(jenkins_instance, pipeline_config)

        self.job_type = 'hardware_test'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets hardware job specific job configuration parameters
        """

        self.params['PROJECT'] = 'project'  # TODO 'matrix-project'

        # junit test result location
        self.set_junit_testresults_param()

        # email
        self._set_mailer_param('Hardware Test')

        # set execute shell
        shell_script = self.get_shell_script()
        self.set_shell_param(shell_script)

        # set pipeline trigger
        self._set_pipelinetrigger_param(['release'])

        # authorization matrix
        self._set_authorization_matrix_param('read')

    def _get_hardware_matrix_entries(self):
        """
        Gets all repository to build and all robots to build on

        @return type: list of dicts
        """

        dict_list = []
        dict_list.append({'repository': self.repo_list})
        # TODO


class ReleaseJob(JenkinsJob):
    """
    Class for release jobs
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location):
        """
        Creates a release job

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(ReleaseJob, self).__init__(jenkins_instance, pipeline_config)

        self.job_type = 'release'
        self.job_name = self._generate_job_name(self.job_type)

    def _set_job_type_params(self):
        """
        Sets release job specific job configuration parameters
        """

        self.params['PROJECT'] = 'project'

        self.params['NODE_LABEL'] = 'release'

        # email
        self._set_mailer_param('Release')


class CleanUpJob(JenkinsJob):
    """
    Class for clean up jobs
    """
    def __init__(self, jenkins_instance, pipeline_config, tarball_location):
        """
        Creates a clean up job

        @param jenkins_instance: Jenkins instance
        @type  jenkins_instance: jenkins.Jenkins
        @param pipeline_config: pipeline configuration
        @type  pipeline_config: dict
        """

        super(CleanUpJob, self).__init__(jenkins_instance, pipeline_config)

    def _set_job_type_params(self):
        """
        Sets clean up job specific job configuration parameters
        """

        self.params['PROJECT'] = 'project'

        self.params['NODE_LABEL'] = 'clean_up'

# TODO classes: test jobs, hardware jobs, release
