import sys
from os.path import abspath, dirname
from os import environ

sys.path.insert(0, dirname(dirname(dirname(abspath(dirname(__file__))))))
from util import var_loader, kubeconfig, constants
from models.release import BaremetalRelease
from tasks.install.openshift import AbstractOpenshiftInstaller

import json

from airflow.operators.bash_operator import BashOperator
from airflow.models import Variable
from kubernetes.client import models as k8s

# Defines Tasks for installation of Openshift Clusters
class BaremetalWebfuseInstaller(AbstractOpenshiftInstaller):
    def __init__(self, dag, release: BaremetalRelease):       
        self.baremetal_install_secrets = Variable.get(
            f"baremetal_openshift_install_config", deserialize_json=True)
        super().__init__(dag, release)

    def get_deploy_app_task(self):
        return self._get_task()        

    # Create Airflow Task for Install/Cleanup steps
    def _get_task(self, trigger_rule="all_success"):
        bash_script = f"{constants.root_dag_dir}/scripts/install/baremetal_deploy_webfuse.sh"

        # Merge all variables, prioritizing Airflow Secrets over git based vars
        config = {
            **self.vars,
            **self.baremetal_install_secrets,
            **{ "es_server": var_loader.get_elastic_url() }
        }
        
        config['version'] = config['openshift_release']
        config['build'] = self.release.build
        
        # Required Environment Variables for Install script
        env = {
            "SSHKEY_TOKEN": config['sshkey_token'],
            "ORCHESTRATION_HOST": config['provisioner_hostname'],
            "ORCHESTRATION_USER": config['provisioner_user'],
            "WEBFUSE_SKIPTAGS": config['webfuse_skiptags'],
            "WEBFUSE_PLAYBOOK": config['webfuse_playbook'],
            **self._insert_kube_env()
        }


        # Dump all vars to json file for Ansible to pick up
        with open(f"/tmp/{self.release_name}-task.json", 'w') as json_file:
            json.dump(config, json_file, sort_keys=True, indent=4)

        return BashOperator(
            task_id="deploy-webfuse",
            depends_on_past=False,
            bash_command=f"{bash_script} -p {self.release.platform} -v {self.release.version} -j /tmp/{self.release_name}-task.json -o deploy_app ",
            retries=3,
            dag=self.dag,
            trigger_rule=trigger_rule,
            executor_config=self.exec_config,
            env=env
        )

    # This Helper Injects Airflow environment variables into the task execution runtime
    # This allows the task to interface with the Kubernetes cluster Airflow is hosted on.
    def _insert_kube_env(self):
        return {key: value for (key, value) in environ.items() if "KUBERNETES" in key}
