#!/usr/bin/env python
# -*- coding: utf-8 -*-

# (c) 2017, Dell EMC Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '0.1'}

DOCUMENTATION = """
module: idrac
version_added: "2.3"
short_description: Manage Dell EMC hardware through iDRAC Redfish APIs
options:
  category:
    required: true
    default: None
    description:
      - Action category to execute on server
  command:
    required: true
    default: None
    description:
      - Command to execute on server
  idracip:
    required: true
    default: None
    description:
      - iDRAC IP address
  idracuser:
    required: false
    default: root
    description:
      - iDRAC user name used for authentication
  idracpswd:
    required: false
    default: calvin
    description:
      - iDRAC user passwore used for authentication
  userid:
    required: false
    default: None
    description:
      - ID of iDRAC user to add/delete/modify
  username:
    required: false
    default: None
    description:
      - name of iDRAC user to add/delete/modify
  userpswd:
    required: false
    default: None
    description:
      - password of iDRAC user to add/delete/modify
  userrole:
    required: false
    default: None
    description:
      - role of iDRAC user to add/delete/modify

author: "jose.delarosa@dell.com"
"""

import os
import requests
import json
import re
from datetime import datetime
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from ansible.module_utils.basic import AnsibleModule

system_uri   = "/Systems/System.Embedded.1" 
chassis_uri  = "/Chassis/System.Embedded.1" 
manager_uri  = "/Managers/iDRAC.Embedded.1"
eventsvc_uri = "/EventService"
session_uri  = "/Sessions"
tasksvc_uri  = "/TaskService"

def manage_storage(command, IDRAC_INFO, root_uri):
    storageuri = root_uri + system_uri + "/Storage/Controllers/"

    # Get a list of all storage controllers and build respective URIs
    controller_list={}
    list_of_uris=[]
    i = send_get_request(IDRAC_INFO, storageuri)

    for controller in i["Members"]:
        for controller_name in controller.items():
            list_of_uris.append(storageuri + controller_name[1].split("/")[-1])

    # for each controller, get name and status
    for storuri in list_of_uris:
        data = send_get_request(IDRAC_INFO, storuri)
        # Only interested in PERC and PCIe? What about SATA?
        if "PERC" in data['Name'] or "PCIe" in data['Name']:
            # Execute based on what we want
            if command == "GetStorageInfo":
                # Returns a list of all controllers along with status
                controller_list[data['Name']] = data['Status']['Health']
            elif command == "ListDevices":
                # Returns a list of all controllers along with devices. Messy, clean up.
                controller_list[data['Name']] = data['Devices']
            else:
                controller_list['Invalid'] = "Invalid Option"
                break

    # Returning a list of all controllers along with status
    result = json.dumps(controller_list)
    return result

def manage_power(command, IDRAC_INFO, root_uri):
    headers = {'content-type': 'application/json'}
    reseturi = root_uri + system_uri + "/Actions/ComputerSystem.Reset"
    idracreseturi = root_uri + manager_uri + "/Actions/Manager.Reset"

    if command == "PowerState":
        power = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = power[u'PowerState']
    elif command == "PowerOn":
        payload = {'ResetType': 'On'}
        result = send_post_request(IDRAC_INFO, reseturi, payload, headers)
    elif command == "PowerOff":
        payload = {'ResetType': 'ForceOff'}
        result = send_post_request(IDRAC_INFO, reseturi, payload, headers)
    elif command == "GracefulRestart":
        payload = {'ResetType': 'GracefulRestart'}
        result = send_post_request(IDRAC_INFO, reseturi, payload, headers)
    elif command == "GracefulShutdown":
        payload = {'ResetType': 'GracefulShutdown'}
        result = send_post_request(IDRAC_INFO, reseturi, payload, headers)
    elif command == "IdracGracefulRestart":
        payload = {'ResetType': 'GracefulRestart'}
        result = send_post_request(IDRAC_INFO, idracreseturi, payload, headers)
    else:
        result = "Invalid Option."
    return result

def manage_users(command, IDRAC_INFO, USER_INFO, root_uri):
    headers = {'content-type': 'application/json'}
    uri = root_uri + manager_uri + "/Accounts/" + USER_INFO['userid']

    if command == "AddUser":
        plUserName = {'UserName': USER_INFO['username']}
        plPass     = {'Password': USER_INFO['userpswd']}
        plRoleID   = {'RoleId': USER_INFO['userrole']}
        for payload in plUserName,plPass,plRoleID:
            result = send_patch_request(IDRAC_INFO, uri, payload, headers)

    elif command == "UpdateUserPassword":
        payload = {'Password': USER_INFO['userpswd']}
        result = send_patch_request(IDRAC_INFO, uri, payload, headers)

    elif command == "UpdateUserRole":
        payload = {'RoleId': USER_INFO['userrole']}
        result = send_patch_request(IDRAC_INFO, uri, payload, headers)

    elif command == "DeleteUser":
        result = "Not yet implemented."

    else:
        result = "Invalid Option."
    return result

def get_system_logs(command, IDRAC_INFO, root_uri):
    if command == "GetSelog":
        result = send_get_request(IDRAC_INFO, root_uri + manager_uri + "/Logs/Sel")
    elif command == "GetLclog":
        result = send_get_request(IDRAC_INFO, root_uri + manager_uri + "/Logs/Lclog")
    else:
        result = "Invalid Option."
    return result

def get_system_information(command, IDRAC_INFO, root_uri):
    if command == "ServerStatus":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'Status'][u'Health']
    elif command == "ServerModel":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'Model']
    elif command == "BiosVersion":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'BiosVersion']
    elif command == "ServerManufacturer":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'Manufacturer']
    elif command == "ServerPartNumber":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'PartNumber']
    elif command == "SystemType":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'SystemType']
    elif command == "AssetTag":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'AssetTag']
    elif command == "MemoryGiB":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'MemorySummary'][u'TotalSystemMemoryGiB']
    elif command == "MemoryHealth":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'MemorySummary'][u'Status'][u'Health']
    elif command == "CPUModel":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'ProcessorSummary'][u'Model']
    elif command == "CPUHealth":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'ProcessorSummary'][u'Status'][u'Health']
    elif command == "CPUCount":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'ProcessorSummary'][u'Count']
    elif command == "ConsumedWatts":
        power = send_get_request(IDRAC_INFO, root_uri + chassis_uri + "/Power/PowerControl")
        result = power[u'PowerConsumedWatts']
    elif command == "PowerState":
        power = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = power[u'PowerState']
    elif command == "ServiceTag":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'SKU']
    elif command == "SerialNumber":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        result = system[u'SerialNumber']
    elif command == "IdracFirmwareVersion":
        system = send_get_request(IDRAC_INFO, root_uri + manager_uri)
        result = system[u'FirmwareVersion']
    elif command == "IdracHealth":
        system = send_get_request(IDRAC_INFO, root_uri + manager_uri)
        result = system[u'Status'][u'Health']
    elif command == "BootSourceOverrideMode":
        system = send_get_request(IDRAC_INFO, root_uri + system_uri)
        systemdict = system[u'Boot']
        if 'BootSourceOverrideMode' in systemdict.keys():
            result = system[u'Boot'][u'BootSourceOverrideMode']
        else:
            result = "14G only."
    else:
        result = "Invalid Command."

    return result

def send_get_request(idrac, uri):
    try:
        response = requests.get(uri, verify=False, auth=(idrac['user'], idrac['pswd']))
        systemData = response.json()
    except:
        raise
    return systemData

def send_post_request(idrac, uri, pyld, hdrs):
    try:
        response = requests.post(uri, data=json.dumps(pyld), headers=hdrs,
                           verify=False, auth=(idrac['user'], idrac['pswd']))
        statusCode = response.status_code
    except:
        raise
    return statusCode

def send_patch_request(idrac, uri, pyld, hdrs):
    try:
        response = requests.patch(uri, data=json.dumps(pyld), headers=hdrs,
                           verify=False, auth=(idrac['user'], idrac['pswd']))
        statusCode = response.status_code
    except:
        raise
    return statusCode

def main():
    module = AnsibleModule(
        argument_spec = dict(
            category = dict(required=True, type='str', default=None),
            command = dict(required=True, type='str', default=None),
            idracip = dict(required=True, type='str', default=None),
            idracuser = dict(required=False, type='str', default='root'),
            idracpswd = dict(required=False, type='str', default='calvin'),
            userid = dict(required=False, type='str', default=None),
            username = dict(required=False, type='str', default=None),
            userpswd = dict(required=False, type='str', default=None),
            userrole = dict(required=False, type='str', default=None),
        ),
        supports_check_mode=True
    )

    params = module.params
    category = params['category']
    command  = params['command']

    # Build initial URI
    root_uri = ''.join(["https://%s" % params['idracip'], "/redfish/v1"])

    # Disable insecure-certificate-warning message
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    IDRAC_INFO = { 'ip'   : params['idracip'],
                   'user' : params['idracuser'],
                   'pswd' : params['idracpswd']
                 } 
    USER_INFO = { 'userid'   : params['userid'],
                  'username' : params['username'],
                  'userpswd' : params['userpswd'],
                  'userrole' : params['userrole']
                 }

    # Execute based on what we want
    if category == "SysInfo":
        result = get_system_information(command, IDRAC_INFO, root_uri)
    elif category == "Logs":
        result = get_system_logs(command, IDRAC_INFO, root_uri)
    elif category == "Users":
        result = manage_users(command, IDRAC_INFO, USER_INFO, root_uri)
    elif category == "Power":
        result = manage_power(command, IDRAC_INFO, root_uri)
    elif category == "Storage":
        result = manage_storage(command, IDRAC_INFO, root_uri)
    else:
        result = "Invalid Category"

    module.exit_json(result=result)

if __name__ == '__main__':
    main()
