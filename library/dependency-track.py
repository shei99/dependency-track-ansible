#!/usr/bin/python

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = r'''
---
module: dependency-track

short_description: This is a module for configuring dependency track.

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description: This is a module for configuring dependency track.

options:
    url:
        description: The location of the dependency track apiserver (e. g. http://deptrack.example.com)
        required: true
        type: string
        
    apiKey:
        description: The api key which has the permissions to manipulate the state of the apiserver
        required: true
        type: str
        
    oidcGroups:
        description: The oidc group, that should be created
        required: false
        type: list
        default: []
    
    state:
        description: The state of the resources (absent, present)
        required: false
        type: string
        default: present
    
    teams:
        description: The team, that should be created
        required: false
        type: list
        
        elements: dict
        subelements:
            name:
                description: The team name
                required: false
                type: str
            oidcGroups:
                description: The oidc group, that should be associated with the team
                required: false
                type: list
            ldapGroup:
                description: The ldap group, that should be associated with the team
                required: false
                type: list
            permissions:
                description: The permissions which the team should get
                required: false
                type: list
            portfolioAccessControl:
                description: The configuration of the portfolio access control
                required: false
                type: dict
                
                verifyParents:
                    description: Verify that projects are children of the parent with the name of the group
                    required: false
                    type: boolean
                    
                projects:
                    description: The list of the projects the group should have access to
                    required: false
                    type: list
                    
            
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
# extends_documentation_fragment:
#     - my_namespace.my_collection.my_doc_fragment_name

author:
    - Michael Scheef (@shei99)
'''

EXAMPLES = r'''
# Pass in a message
- name: Test with a message
  my_namespace.my_collection.my_test:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_namespace.my_collection.my_test:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_namespace.my_collection.my_test:
    name: fail me
'''

RETURN = r'''
# These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: The original name param that was passed in.
    type: str
    returned: always
    sample: 'hello world'
message:
    description: The output message that the test module generates.
    type: str
    returned: always
    sample: 'goodbye'
'''

from ansible.module_utils.basic import AnsibleModule
import requests
from collections import defaultdict


DICT_KEY_CHILDREN = 'children'
DICT_KEY_ID = 'id'


def run_module():
    # define available arguments/parameters a user can pass to the module

    verify_portfolio_access_control = dict(
        enabled=dict(type='bool', default=False, choices=[True, False]),
        rootProject=dict(type='str', default='')
    )

    portfolio_access_control = dict(
        verify=dict(type='dict', default={}, options=verify_portfolio_access_control),
        projects=dict(type='list', default=[]),
    )

    teams_spec = dict(
        name=dict(type='str'),
        oidcGroups=dict(type='list', default=[]),
        ldapGroups=dict(type='list', default=[]),
        permissions=dict(type='list', default=[],
                         choices=['ACCESS_MANAGEMENT', 'BOM_UPLOAD', 'POLICY_MANAGEMENT', 'POLICY_VIOLATION_ANALYSIS',
                                  'PORTFOLIO_MANAGEMENT', 'PROJECT_CREATION_UPLOAD', 'SYSTEM_CONFIGURATION',
                                  'VIEW_PORTFOLIO', 'VIEW_VULNERABILITY', 'VULNERABILITY_MANAGEMENT']),
        portfolioAccessControl=dict(type='dict', default={}, options=portfolio_access_control)
    )

    module_args = dict(
        url=dict(type='str', required=True),
        apiKey=dict(type='str', required=True),
        oidcGroups=dict(type='list', default=[]),
        state=dict(type='str', default='present', choices=['absent', 'present']),
        teams=dict(type='list', default=[], elements='dict', options=teams_spec)
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        original_message='',
        message=''
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    url = module.params['url']
    api_key = module.params['apiKey']
    oidc_groups = module.params['oidcGroups']
    teams = module.params['teams']
    state = module.params['state']

    if state == 'present':
        # Create oidc group
        changed = create_oidc_groups(url, api_key, oidc_groups)
        result['changed'] = result['changed'] or changed

        # Create team
        changed = create_teams(url, api_key, teams)
        result['changed'] = result['changed'] or changed

        manage_group_mappings(url, api_key, teams)
    else:
        # Delete oidc group
        changed = delete_oidc_groups(url, api_key, oidc_groups)
        result['changed'] = result['changed'] or changed

        # Delete team
        changed = delete_teams(url, api_key, teams)
        result['changed'] = result['changed'] or changed


    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    # result['original_message'] = module.params['name']
    # result['message'] = 'goodbye'

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    # if module.params['name'] == 'fail me':
    #     module.fail_json(msg='You requested this to fail', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def create_oidc_groups(url: str, api_key: str, oidc_groups: list) -> bool:
    headers = {'X-API-Key': api_key}
    changed = False
    for group in oidc_groups:
        payload = {'name': group}
        resp = requests.put(f"{url}/api/v1/oidc/group", json=payload, headers=headers)
        if resp.status_code == 201:
            changed = True
    return changed


def delete_oidc_groups(url: str, api_key: str, oidc_groups: list) -> bool:
    headers = {'X-API-Key': api_key}
    existing_oidc_groups = get_existing_oidc_groups(url, api_key)
    changed = False
    for group in oidc_groups:
        if group not in existing_oidc_groups.keys():
            continue
        payload = {'name': group}
        resp = requests.delete(f"{url}/api/v1/oidc/group/{existing_oidc_groups[group]}", json=payload, headers=headers)
        if resp.status_code == 200:
            changed = True
    return changed


# TODO validate that there was no parallel collision
def create_teams(url: str, api_key: str, teams: list):
    existing_teams = list(get_existing_teams(url, api_key).keys())
    headers = {'X-API-Key': api_key}
    changed = False
    for team in teams:
        team_name = team['name']
        if team_name in existing_teams:
            continue
        payload = {'name': team_name}
        resp = requests.put(f"{url}/api/v1/team", json=payload, headers=headers)
        if resp.status_code == 201:
            changed = True
            existing_teams.append(team_name)
            raise Exception(resp.json())
    return changed


def delete_teams(url: str, api_key: str, teams: list):
    existing_teams = get_existing_teams(url, api_key)
    headers = {'X-API-Key': api_key}
    changed = False
    for team in teams:
        team_name = team['name']
        if team_name not in existing_teams.keys():
            continue
        payload = {'uuid': existing_teams[team_name]}
        resp = requests.delete(f"{url}/api/v1/team", json=payload, headers=headers)
        if resp.status_code == 200:
            changed = True
    return changed


def manage_group_mappings(url: str, api_key: str, teams: dict):
    existing_teams = get_existing_teams(url, api_key)
    changed = False
    existing_project_tree = get_project_tree(url, api_key)
    for team in teams:
        group_change = manage_oidc_groups(url, api_key, existing_teams[team['name']], team['oidcGroups'])
        permission_change = manage_permissions(url, api_key, existing_teams[team['name']], team['permissions'])
        activate_portfolio_access_control(url, api_key)
        portfolio_access_control_change = manage_portfolio_access_control(url, api_key, existing_project_tree, existing_teams[team['name']], team['portfolioAccessControl'])
        changed = changed or group_change or permission_change or portfolio_access_control_change
    return changed


def manage_oidc_groups(url: str, api_key: str, team_uuid: str, team_oidc_groups: list) -> bool:
    existing_oidc_groups = get_existing_oidc_groups(url, api_key)
    url = f"{url}/api/v1/oidc/mapping"
    headers = {'X-API-Key': api_key}
    changed = False
    for existing_group_name, existing_group_uuid in existing_oidc_groups.items():
        if existing_group_name in team_oidc_groups:
            payload = {'group': existing_group_uuid, 'team': team_uuid}
            resp = requests.put(url, json=payload, headers=headers)
            if resp.status_code == 200:
                changed = True
        else:
            resp = requests.delete(f"{url}/{existing_group_uuid}", headers=headers)
            if resp.status_code == 200:
                changed = True
    return changed


def manage_permissions(url, api_key, team_uuid, team_permissions: list) -> bool:
    permissions = ['ACCESS_MANAGEMENT', 'BOM_UPLOAD', 'POLICY_MANAGEMENT', 'POLICY_VIOLATION_ANALYSIS',
                   'PORTFOLIO_MANAGEMENT', 'PROJECT_CREATION_UPLOAD', 'SYSTEM_CONFIGURATION', 'VIEW_PORTFOLIO',
                   'VIEW_VULNERABILITY', 'VULNERABILITY_MANAGEMENT']
    headers = {'X-API-Key': api_key}
    changed = False
    for permission in permissions:
        if permission not in team_permissions:
            continue
        resp = requests.post(f"{url}/api/v1/permission/{permission}/team/{team_uuid}", headers=headers)
        if resp.status_code == 200:
            changed = True
    return changed


def manage_portfolio_access_control(url: str, api_key: str, existing_project_tree: dir, team_uuid: str, team_portfolio_access_control: dict) -> bool:
    projects = team_portfolio_access_control['projects']
    if team_portfolio_access_control['verify']['enabled']:
        projects = filter_project_list(existing_project_tree, team_portfolio_access_control['verify']['rootProject'], team_portfolio_access_control['projects'])

    return update_portfolio_access_control(url, api_key, existing_project_tree, team_uuid, team_portfolio_access_control['verify'], projects)


def update_portfolio_access_control(url: str, api_key: str, existing_project_tree: dir, team_uuid: str, team_portfolio_access_control_verify: dict, projects: list) -> bool:
    headers = {'X-API-Key': api_key}
    changed = False

    for key in existing_project_tree.keys():
        if key in projects:
            payload = {'team': team_uuid, 'project': existing_project_tree[key][DICT_KEY_ID]}
            resp = requests.put(f"{url}/api/v1/acl/mapping", json=payload, headers=headers)
            if resp.status_code == 200:
                changed = True
        else:
            print("delete", team_uuid, existing_project_tree[key][DICT_KEY_ID])
            resp = requests.delete(f"{url}/api/v1/acl/mapping/team/{team_uuid}/project/{existing_project_tree[key][DICT_KEY_ID]}", headers=headers)
            if resp.status_code == 200:
                changed = True
        child_changed = update_portfolio_access_control(url, api_key, existing_project_tree[key][DICT_KEY_CHILDREN], team_uuid, team_portfolio_access_control_verify, projects)
        changed = changed or child_changed
    return changed


def filter_project_list(existing_project_tree: dict, team_name: str, projects: list) -> list:
    return [project for project in projects if access_to_project_allowed(existing_project_tree, team_name, project)]


def activate_portfolio_access_control(url, api_key):
    headers = {'X-API-Key': api_key}
    payload = [{"groupName": "access-management", "propertyName": "acl.enabled", "propertyValue": "true"}]
    resp = requests.post(f"{url}/api/v1/configProperty/aggregate", json=payload, headers=headers)
    return resp.status_code == 200


def get_existing_teams(url: str, api_key: str) -> dict:
    url = f"{url}/api/v1/team"
    headers = {'X-API-Key': api_key}
    resp = requests.get(url, headers=headers)

    name_to_id_mapping = {}
    for team in resp.json():
        name_to_id_mapping[team['name']] = team['uuid']
    return name_to_id_mapping


def get_existing_oidc_groups(url: str, api_key: str):
    url = f"{url}/api/v1/oidc/group"
    headers = {'X-API-Key': api_key}
    resp = requests.get(url, headers=headers)

    name_to_id_mapping = {}
    for group in resp.json():
        name_to_id_mapping[group['name']] = group['uuid']
    return name_to_id_mapping


def get_existing_project(url: str, api_key: str):
    url = f"{url}/api/v1/project"
    headers = {'X-API-Key': api_key}
    resp = requests.get(url, headers=headers)

    name_to_id_mapping = {}
    for project in resp.json():
        name_to_id_mapping[project['name']] = project['uuid']
    return name_to_id_mapping


def tree():
    return defaultdict(tree)


def access_to_project_allowed(project_tree: dict, team_name: str, project_name: str) -> bool:
    if team_name not in project_tree.keys():
        # raise Exception(json.dumps(project_tree))
        return False

    if team_name == project_name:
        return True

    return verify_access_control_in_project_tree(project_tree[team_name][DICT_KEY_CHILDREN], project_name)


def verify_access_control_in_project_tree(project_tree: dict, project_name: str) -> bool:
    access_allowed = False
    for key in project_tree.keys():
        if project_name == key:
            access_allowed = True
        else:
            child_access_allowed = verify_access_control_in_project_tree(project_tree[key][DICT_KEY_CHILDREN], project_name)
            access_allowed = access_allowed or child_access_allowed
    return access_allowed


def get_project_tree(url: str, api_key: str) -> dict:
    project_root_url = f"{url}/api/v1/project?onlyRoot=true"
    headers = {'X-API-Key': api_key}
    resp = requests.get(project_root_url, headers=headers)

    project_tree = tree()
    for project in resp.json():
        project_tree[project['name']][DICT_KEY_ID] = project['uuid']
        if 'children' not in project.keys():
            continue
        for child in project['children']:
            project_tree[project['name']][DICT_KEY_CHILDREN][child['name']][DICT_KEY_ID] = child['uuid']

    return add_children_to_project_tree(url, api_key, project_tree)


def add_children_to_project_tree(url: str, api_key: str, project_tree: dict) -> dict:
    for k in project_tree.keys():
        if not isinstance(project_tree[k], dict):
            continue
        if DICT_KEY_CHILDREN in project_tree[k].keys():
            add_children_to_project_tree(url, api_key, project_tree[k][DICT_KEY_CHILDREN])
        if DICT_KEY_ID in project_tree[k].keys():
            children = get_children_of_project(url, api_key, project_tree[k][DICT_KEY_ID])
            for name, uuid in children.items():
                project_tree[k][DICT_KEY_CHILDREN][name][DICT_KEY_ID] = uuid
            add_children_to_project_tree(url, api_key, project_tree[k][DICT_KEY_CHILDREN])
    return project_tree


def get_children_of_project(url: str, api_key: str, project_id: str) -> dict:
    url = f"{url}/api/v1/project/{project_id}"
    headers = {'X-API-Key': api_key}
    resp = requests.get(url, headers=headers)

    project = resp.json()
    if 'children' not in project.keys():
        return {}

    name_to_id_mapping = {}
    for child in project['children']:
        name_to_id_mapping[child['name']] = child['uuid']
    return name_to_id_mapping


def main():
    run_module()


if __name__ == '__main__':
    main()
